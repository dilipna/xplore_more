package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/fetch"
	"github.com/dilipna/xploremore/apps/edge-go/internal/textstore"
)

type stubFetcher struct {
	result *fetch.Result
	err    error
	calls  int
}

func (s *stubFetcher) Get(_ context.Context, _ string) (*fetch.Result, error) {
	s.calls++
	return s.result, s.err
}

type failingStore struct{}

func (failingStore) Put(context.Context, string, string, string, time.Time) (string, error) {
	return "", errors.New("gcs unavailable")
}

var articleHTML = []byte(`<html lang="en"><head><title>Kubernetes 1.40 released</title>
<link rel="canonical" href="https://kubernetes.io/blog/2026/09/01/k8s-1-40/"></head>
<body><article><p>The Kubernetes project released version 1.40 with improvements to
scheduling, dynamic resource allocation for accelerators, and in-place pod resizing now
generally available. The release includes dozens of enhancements graduating to stable,
and deprecates several legacy APIs that cluster operators should migrate away from.</p>
</article></body></html>`)

func discoveredFixture(t *testing.T) []byte {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "contracts", "fixtures", "article.discovered.v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func pushBody(t *testing.T, data []byte) io.Reader {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"message":         map[string]any{"data": data, "messageId": "m-1"},
		"subscription":    "projects/xm/subscriptions/article-discovered-ingestor",
		"deliveryAttempt": 1,
	})
	return bytes.NewReader(body)
}

func newHandler(f Fetcher, store textstore.Store, pub bus.Publisher) *Handler {
	return &Handler{
		Fetcher:        f,
		Store:          store,
		Publisher:      pub,
		ExtractedTopic: "article-extracted",
		Log:            slog.New(slog.NewTextHandler(io.Discard, nil)),
		Now:            func() time.Time { return time.Date(2026, 9, 13, 10, 0, 5, 0, time.UTC) },
		FetchTimeout:   5 * time.Second,
	}
}

func okResult(t *testing.T) *fetch.Result {
	u, _ := url.Parse("https://kubernetes.io/blog/2026/09/01/k8s-1-40/?utm_source=rss")
	return &fetch.Result{FinalURL: u, Body: articleHTML, ContentType: "text/html", Status: 200}
}

func serve(h http.Handler, body io.Reader) int {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/push", body))
	return rec.Code
}

func TestSuccessfulIngestPublishesContractValidEvent(t *testing.T) {
	pub := &bus.Memory{}
	h := newHandler(&stubFetcher{result: okResult(t)}, textstore.File{Dir: t.TempDir()}, pub)

	if code := serve(h, pushBody(t, discoveredFixture(t))); code != http.StatusNoContent {
		t.Fatalf("status %d", code)
	}
	msgs := pub.Snapshot()
	if len(msgs) != 1 || msgs[0].Topic != "article-extracted" || msgs[0].Attrs["type"] != events.TypeArticleExtracted {
		t.Fatalf("published %+v", msgs)
	}
	dec := json.NewDecoder(bytes.NewReader(msgs[0].Data))
	dec.DisallowUnknownFields()
	var env events.Envelope[events.ArticleExtracted]
	if err := dec.Decode(&env); err != nil {
		t.Fatal(err)
	}
	d := env.Data
	if d.CanonicalURL != "https://kubernetes.io/blog/2026/09/01/k8s-1-40" {
		t.Errorf("canonical %q", d.CanonicalURL)
	}
	if env.Subject != d.ArticleID || d.ArticleID != events.Sha256Hex(d.CanonicalURL) {
		t.Error("identity mismatch")
	}
	if env.IdempotencyKey != events.IdempotencyKey(env.Type, d.ArticleID, d.ContentHash) {
		t.Error("idempotency key mismatch")
	}
	if env.CausedBy == nil || *env.CausedBy != "0192f3a4-5b6c-7d8e-9f01-23456789abcd" {
		t.Error("lineage caused_by not set to discovery event id")
	}
	if !strings.HasPrefix(d.TextURI, "file://") || d.Lang != "en" || d.SourceID != "anthropic-news" || d.ContentOrigin != events.OriginPage {
		t.Errorf("payload %+v", d)
	}
	if h.Stats.Extracted.Load() != 1 {
		t.Error("extracted counter")
	}
}

func TestRetryPolicy(t *testing.T) {
	cases := []struct {
		name    string
		fetcher *stubFetcher
		store   textstore.Store
		pub     *bus.Memory
		want    int
	}{
		{"transient fetch error retries", &stubFetcher{err: fmt.Errorf("%w: timeout", fetch.ErrTransient)}, textstore.File{Dir: t.TempDir()}, &bus.Memory{}, http.StatusServiceUnavailable},
		{"permanent fetch error acks", &stubFetcher{err: fmt.Errorf("%w: 404", fetch.ErrPermanent)}, textstore.File{Dir: t.TempDir()}, &bus.Memory{}, http.StatusNoContent},
		{"store outage retries", &stubFetcher{result: okResult(t)}, failingStore{}, &bus.Memory{}, http.StatusServiceUnavailable},
		{"publish failure retries", &stubFetcher{result: okResult(t)}, textstore.File{Dir: t.TempDir()}, &bus.Memory{Err: errors.New("pubsub down")}, http.StatusServiceUnavailable},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := newHandler(tc.fetcher, tc.store, tc.pub)
			if code := serve(h, pushBody(t, discoveredFixture(t))); code != tc.want {
				t.Fatalf("status %d, want %d", code, tc.want)
			}
			if tc.want != http.StatusNoContent && len(tc.pub.Snapshot()) != 0 {
				t.Fatal("nothing may be published when the input will be retried")
			}
		})
	}
}

func TestThrottledFetchRetriesAndIsCountedSeparately(t *testing.T) {
	throttledErr := fmt.Errorf("%w: %w: slot in 18s, 20s left", fetch.ErrTransient, fetch.ErrThrottled)
	h := newHandler(&stubFetcher{err: throttledErr}, textstore.File{Dir: t.TempDir()}, &bus.Memory{})
	if code := serve(h, pushBody(t, discoveredFixture(t))); code != http.StatusServiceUnavailable {
		t.Fatalf("status %d, want 503", code)
	}
	plain := newHandler(&stubFetcher{err: fmt.Errorf("%w: timeout", fetch.ErrTransient)}, textstore.File{Dir: t.TempDir()}, &bus.Memory{})
	_ = serve(plain, pushBody(t, discoveredFixture(t)))

	if h.Stats.Retried.Load() != 1 || h.Stats.Throttled.Load() != 1 {
		t.Fatalf("throttled handler: retried=%d throttled=%d", h.Stats.Retried.Load(), h.Stats.Throttled.Load())
	}
	if plain.Stats.Retried.Load() != 1 || plain.Stats.Throttled.Load() != 0 {
		t.Fatalf("plain transient: retried=%d throttled=%d", plain.Stats.Retried.Load(), plain.Stats.Throttled.Load())
	}
}

func TestBlockedPageFallsBackToFeedContent(t *testing.T) {
	var env map[string]any
	_ = json.Unmarshal(discoveredFixture(t), &env)
	env["data"].(map[string]any)["feed_summary"] = "vLLM 0.20 adds disaggregated prefill, speculative decoding for MoE models, and a new KV cache offloading path."
	data, _ := json.Marshal(env)

	pub := &bus.Memory{}
	h := newHandler(&stubFetcher{err: fmt.Errorf("%w: status 403", fetch.ErrPermanent)}, textstore.File{Dir: t.TempDir()}, pub)
	if code := serve(h, pushBody(t, data)); code != http.StatusNoContent {
		t.Fatalf("status %d", code)
	}
	msgs := pub.Snapshot()
	if len(msgs) != 1 {
		t.Fatalf("expected feed-origin event, got %d messages", len(msgs))
	}
	var out events.Envelope[events.ArticleExtracted]
	_ = json.Unmarshal(msgs[0].Data, &out)
	if out.Data.ContentOrigin != events.OriginFeed || !strings.Contains(out.Data.Lede, "disaggregated prefill") {
		t.Fatalf("payload %+v", out.Data)
	}
	if out.Data.CanonicalURL != "https://anthropic.com/news/claude-example" {
		t.Fatalf("feed fallback must keep the discovered canonical URL, got %q", out.Data.CanonicalURL)
	}
}

func TestContractViolationsAreRejectedWithoutFetching(t *testing.T) {
	fixture := discoveredFixture(t)
	var generic map[string]any
	_ = json.Unmarshal(fixture, &generic)
	generic["data"].(map[string]any)["unexpected_field"] = 1
	withExtraField, _ := json.Marshal(generic)

	for name, data := range map[string][]byte{
		"not json":      []byte("<xml/>"),
		"unknown field": withExtraField,
		"wrong type":    bytes.Replace(fixture, []byte("xm.article.discovered.v1"), []byte("xm.story.updated.v1"), 1),
	} {
		t.Run(name, func(t *testing.T) {
			f := &stubFetcher{result: okResult(t)}
			h := newHandler(f, textstore.File{Dir: t.TempDir()}, &bus.Memory{})
			if code := serve(h, pushBody(t, data)); code != http.StatusNoContent {
				t.Fatalf("status %d", code)
			}
			if f.calls != 0 {
				t.Fatal("fetched a URL from an invalid event")
			}
		})
	}
}

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "contracts", "fixtures", name))
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestDiscussionIsNeverFetchedAndKeepsProvenance(t *testing.T) {
	f := &stubFetcher{result: okResult(t)}
	pub := &bus.Memory{}
	h := newHandler(f, textstore.File{Dir: t.TempDir()}, pub)
	if code := serve(h, pushBody(t, readFixture(t, "discussion.discovered.v1.json"))); code != http.StatusNoContent {
		t.Fatalf("status %d", code)
	}
	if f.calls != 0 {
		t.Fatal("a discussion must not trigger an HTML fetch")
	}
	msgs := pub.Snapshot()
	if len(msgs) != 1 {
		t.Fatalf("published %d", len(msgs))
	}
	dec := json.NewDecoder(bytes.NewReader(msgs[0].Data))
	dec.DisallowUnknownFields()
	var got events.Envelope[events.ArticleExtracted]
	if err := dec.Decode(&got); err != nil {
		t.Fatal(err)
	}
	var want events.Envelope[events.ArticleExtracted]
	_ = json.Unmarshal(readFixture(t, "discussion.extracted.v1.json"), &want)

	gotDisc, _ := json.Marshal(got.Data.Discussion)
	wantDisc, _ := json.Marshal(want.Data.Discussion)
	if got.Data.DocKind != events.KindDiscussion || !bytes.Equal(gotDisc, wantDisc) {
		t.Fatalf("provenance lost: kind %q discussion %s", got.Data.DocKind, gotDisc)
	}
	// The ingestor and the contract fixture agree on identity and content hashing.
	if got.Data.ContentHash != want.Data.ContentHash || got.IdempotencyKey != want.IdempotencyKey || got.Data.ContentOrigin != events.OriginFeed {
		t.Fatalf("got %+v\nwant %+v", got.Data, want.Data)
	}
}

func TestDiscussionKindMismatchIsRejected(t *testing.T) {
	var generic map[string]any
	_ = json.Unmarshal(readFixture(t, "discussion.discovered.v1.json"), &generic)
	generic["data"].(map[string]any)["discussion"] = nil
	data, _ := json.Marshal(generic)

	f := &stubFetcher{result: okResult(t)}
	pub := &bus.Memory{}
	h := newHandler(f, textstore.File{Dir: t.TempDir()}, pub)
	if code := serve(h, pushBody(t, data)); code != http.StatusNoContent {
		t.Fatalf("status %d", code)
	}
	if f.calls != 0 || len(pub.Snapshot()) != 0 || h.Stats.Rejected.Load() != 1 {
		t.Fatalf("mismatched event was processed: calls %d published %d", f.calls, len(pub.Snapshot()))
	}
}

func TestLegacyDiscoveredIsProcessedAsArticle(t *testing.T) {
	pub := &bus.Memory{}
	h := newHandler(&stubFetcher{result: okResult(t)}, textstore.File{Dir: t.TempDir()}, pub)
	if code := serve(h, pushBody(t, readFixture(t, filepath.Join("legacy", "article.discovered.v1.pre-doc-kind.json")))); code != http.StatusNoContent {
		t.Fatalf("status %d", code)
	}
	var out events.Envelope[events.ArticleExtracted]
	msgs := pub.Snapshot()
	if len(msgs) != 1 {
		t.Fatalf("published %d", len(msgs))
	}
	_ = json.Unmarshal(msgs[0].Data, &out)
	if out.Data.DocKind != events.KindArticle || out.Data.Discussion != nil {
		t.Fatalf("legacy event kind %q", out.Data.DocKind)
	}
}

func TestRejectsNonPost(t *testing.T) {
	h := newHandler(&stubFetcher{}, textstore.File{Dir: t.TempDir()}, &bus.Memory{})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/push", nil))
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status %d", rec.Code)
	}
}
