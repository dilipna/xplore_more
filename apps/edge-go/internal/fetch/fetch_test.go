package fetch

import (
	"compress/gzip"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"golang.org/x/time/rate"

	"github.com/dilipna/xploremore/apps/edge-go/internal/ssrf"
)

func testFetcher() *Fetcher {
	policy := ssrf.DefaultPolicy()
	policy.AllowLoopback = true
	opts := DefaultOptions()
	opts.PerHostRate = rate.Inf
	opts.MaxBytes = 1 << 16
	opts.Timeout = 3 * time.Second
	return New(policy, opts)
}

func TestGetClassifiesStatusCodes(t *testing.T) {
	cases := map[int]error{
		http.StatusOK:                  nil,
		http.StatusNotFound:            ErrPermanent,
		http.StatusGone:                ErrPermanent,
		http.StatusForbidden:           ErrPermanent,
		http.StatusTooManyRequests:     ErrTransient,
		http.StatusServiceUnavailable:  ErrTransient,
		http.StatusInternalServerError: ErrTransient,
	}
	for status, want := range cases {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/robots.txt" {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			w.WriteHeader(status)
			_, _ = w.Write([]byte("<html></html>"))
		}))
		_, err := testFetcher().Get(context.Background(), srv.URL+"/page")
		srv.Close()
		if want == nil && err != nil {
			t.Errorf("status %d: unexpected error %v", status, err)
		}
		if want != nil && !errors.Is(err, want) {
			t.Errorf("status %d: got %v, want %v", status, err, want)
		}
	}
}

func TestGetRejectsNonHTMLAndOversizedBodies(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/pdf":
			w.Header().Set("Content-Type", "application/pdf")
			_, _ = w.Write([]byte("%PDF"))
		case "/huge":
			w.Header().Set("Content-Type", "text/html")
			_, _ = w.Write([]byte(strings.Repeat("a", 1<<17)))
		case "/bomb":
			// ~130 KB of HTML compressed to a few hundred bytes: the limit must apply
			// after decompression.
			w.Header().Set("Content-Type", "text/html")
			w.Header().Set("Content-Encoding", "gzip")
			gz := gzip.NewWriter(w)
			_, _ = gz.Write([]byte(strings.Repeat("<p>x</p>", 1<<14)))
			_ = gz.Close()
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()
	f := testFetcher()
	for _, path := range []string{"/pdf", "/huge", "/bomb"} {
		if _, err := f.Get(context.Background(), srv.URL+path); !errors.Is(err, ErrPermanent) {
			t.Errorf("%s: got %v, want permanent", path, err)
		}
	}
}

func TestGetHonoursRobotsTxt(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/robots.txt" {
			_, _ = w.Write([]byte("User-agent: *\nDisallow: /private\n"))
			return
		}
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte("<html>ok</html>"))
	}))
	defer srv.Close()
	f := testFetcher()
	if _, err := f.Get(context.Background(), srv.URL+"/private/post"); !errors.Is(err, ErrPermanent) {
		t.Fatalf("disallowed path: got %v", err)
	}
	if _, err := f.Get(context.Background(), srv.URL+"/public/post"); err != nil {
		t.Fatalf("allowed path: %v", err)
	}
}

func TestBlockedDestinationIsPermanent(t *testing.T) {
	f := New(ssrf.DefaultPolicy(), DefaultOptions())
	_, err := f.Get(context.Background(), "http://127.0.0.1:80/")
	if !errors.Is(err, ErrPermanent) {
		t.Fatalf("got %v, want permanent", err)
	}
}

func TestPerHostRateLimitSpacesRequests(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte("<html></html>"))
	}))
	defer srv.Close()
	f := testFetcher()
	f.opts.PerHostRate = rate.Every(100 * time.Millisecond)
	f.opts.PerHostBurst = 1
	start := time.Now()
	for range 3 {
		if _, err := f.Get(context.Background(), srv.URL+"/p"); err != nil {
			t.Fatal(err)
		}
	}
	if elapsed := time.Since(start); elapsed < 180*time.Millisecond {
		t.Fatalf("3 requests took %v; limiter not applied", elapsed)
	}
}
