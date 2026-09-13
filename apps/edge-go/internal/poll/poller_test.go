package poll

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
)

const rssBody = `<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example</title>
<item><title>Post one</title><link>https://example.com/one?utm_source=rss</link>
  <description>&lt;p&gt;First &lt;b&gt;summary&lt;/b&gt;&lt;/p&gt;</description>
  <pubDate>Sat, 12 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Post two</title><link>https://www.example.com/two/</link></item>
<item><title>Duplicate of one</title><link>https://example.com/one</link></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
</channel></rss>`

func newPoller(t *testing.T, pub bus.Publisher) *Poller {
	t.Helper()
	return &Poller{
		Client:          http.DefaultClient, // SSRF policy is tested in package ssrf
		Publisher:       pub,
		State:           FileStateStore{Path: filepath.Join(t.TempDir(), "state.json")},
		DiscoveredTopic: "article-discovered",
		UserAgent:       "test",
		Log:             slog.New(slog.NewTextHandler(io.Discard, nil)),
		Now:             func() time.Time { return time.Date(2026, 9, 13, 10, 0, 0, 0, time.UTC) },
		PerSourceTimout: 5 * time.Second,
	}
}

func feedServer(t *testing.T, hits *atomic.Int32) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		if r.Header.Get("If-None-Match") == `"v1"` {
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", `"v1"`)
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rssBody))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func rssSource(url string) sources.Source {
	return sources.Source{ID: "example", Kind: sources.KindRSS, URL: url, MaxItems: 50}
}

func TestFirstRunPublishesUniqueCanonicalItems(t *testing.T) {
	var hits atomic.Int32
	srv := feedServer(t, &hits)
	pub := &bus.Memory{}
	p := newPoller(t, pub)

	reports, err := p.RunOnce(context.Background(), []sources.Source{rssSource(srv.URL)})
	if err != nil {
		t.Fatal(err)
	}
	r := reports[0]
	if r.Found != 4 || r.Published != 2 || r.Skipped != 1 || r.Invalid != 1 {
		t.Fatalf("report %+v", r)
	}

	msgs := pub.Snapshot()
	var env events.Envelope[events.ArticleDiscovered]
	if err := json.Unmarshal(msgs[0].Data, &env); err != nil {
		t.Fatal(err)
	}
	if env.Data.CanonicalURL != "https://example.com/one" || env.Data.URL != "https://example.com/one?utm_source=rss" {
		t.Errorf("urls %+v", env.Data)
	}
	if env.Data.FeedSummary == nil || *env.Data.FeedSummary != "First summary" {
		t.Errorf("summary not stripped of markup: %v", env.Data.FeedSummary)
	}
	if env.Data.PublishedAt == nil || !strings.HasPrefix(*env.Data.PublishedAt, "2026-09-12T10:00:00") {
		t.Errorf("published_at %v", env.Data.PublishedAt)
	}
	if env.IdempotencyKey != events.IdempotencyKey(env.Type, env.Subject, "") {
		t.Error("idempotency key")
	}
}

func TestSecondRunUsesConditionalGetAndPublishesNothing(t *testing.T) {
	var hits atomic.Int32
	srv := feedServer(t, &hits)
	pub := &bus.Memory{}
	p := newPoller(t, pub)
	src := []sources.Source{rssSource(srv.URL)}

	if _, err := p.RunOnce(context.Background(), src); err != nil {
		t.Fatal(err)
	}
	reports, err := p.RunOnce(context.Background(), src)
	if err != nil {
		t.Fatal(err)
	}
	if !reports[0].NotMod || len(pub.Snapshot()) != 2 {
		t.Fatalf("second run report %+v, total published %d", reports[0], len(pub.Snapshot()))
	}
}

func TestPublishFailureLosesNothing(t *testing.T) {
	var hits atomic.Int32
	srv := feedServer(t, &hits)
	pub := &bus.Memory{Err: errors.New("pubsub unavailable")}
	p := newPoller(t, pub)
	src := []sources.Source{rssSource(srv.URL)}

	reports, err := p.RunOnce(context.Background(), src)
	if err != nil {
		t.Fatal(err)
	}
	if reports[0].Error == "" || reports[0].Published != 0 {
		t.Fatalf("report %+v", reports[0])
	}

	pub.Err = nil // outage over
	reports, err = p.RunOnce(context.Background(), src)
	if err != nil {
		t.Fatal(err)
	}
	if reports[0].NotMod || reports[0].Published != 2 {
		t.Fatalf("items lost after outage: %+v", reports[0])
	}
}

func TestSourceFailureIsRecordedAndIsolated(t *testing.T) {
	var hits atomic.Int32
	good := feedServer(t, &hits)
	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer bad.Close()

	pub := &bus.Memory{}
	p := newPoller(t, pub)
	badSrc := sources.Source{ID: "broken", Kind: sources.KindRSS, URL: bad.URL, MaxItems: 10}
	reports, err := p.RunOnce(context.Background(), []sources.Source{rssSource(good.URL), badSrc})
	if err != nil {
		t.Fatal(err)
	}
	byID := map[string]SourceReport{}
	for _, r := range reports {
		byID[r.SourceID] = r
	}
	if byID["broken"].Error == "" || byID["example"].Published != 2 {
		t.Fatalf("reports %+v", reports)
	}
	state, _, _ := p.State.Load(context.Background())
	if state.Sources["broken"].Failures != 1 || state.Sources["example"].LastSuccess == 0 {
		t.Fatalf("health not recorded: %+v %+v", state.Sources["broken"], state.Sources["example"])
	}
}

func TestHackerNewsSkipsThreadsAndCarriesSignals(t *testing.T) {
	var itemFetches atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/newstories.json":
			_, _ = w.Write([]byte(`[101, 102]`))
		case r.URL.Path == "/topstories.json":
			_, _ = w.Write([]byte(`[102, 103]`))
		case strings.HasPrefix(r.URL.Path, "/item/"):
			itemFetches.Add(1)
			var id int
			_, _ = fmt.Sscanf(r.URL.Path, "/item/%d.json", &id)
			switch id {
			case 101:
				_, _ = w.Write([]byte(`{"id":101,"type":"story","url":"https://blog.example/post","title":"A post","score":42,"descendants":7,"time":1789300000}`))
			case 102:
				_, _ = w.Write([]byte(`{"id":102,"type":"story","title":"Ask HN: something","score":5,"time":1789300000}`))
			case 103:
				_, _ = w.Write([]byte(`{"id":103,"type":"story","url":"https://dead.example","dead":true,"time":1789300000}`))
			}
		}
	}))
	defer srv.Close()

	pub := &bus.Memory{}
	p := newPoller(t, pub)
	src := []sources.Source{{ID: "hacker-news", Kind: sources.KindHN, URL: srv.URL, MaxItems: 50}}
	if _, err := p.RunOnce(context.Background(), src); err != nil {
		t.Fatal(err)
	}
	msgs := pub.Snapshot()
	if len(msgs) != 1 {
		t.Fatalf("published %d, want 1", len(msgs))
	}
	var env events.Envelope[events.ArticleDiscovered]
	_ = json.Unmarshal(msgs[0].Data, &env)
	s := env.Data.Signals
	if s.HNItemID == nil || *s.HNItemID != 101 || *s.HNPoints != 42 || *s.HNComments != 7 || s.ObservedAt == nil {
		t.Fatalf("signals %+v", s)
	}
	if itemFetches.Load() != 3 {
		t.Fatalf("item fetches %d", itemFetches.Load())
	}

	// Second run must not refetch items already resolved (including skipped threads).
	if _, err := p.RunOnce(context.Background(), src); err != nil {
		t.Fatal(err)
	}
	if itemFetches.Load() != 3 {
		t.Fatalf("refetched known items: %d fetches", itemFetches.Load())
	}
}

func TestConcurrentWriterIsDetected(t *testing.T) {
	store := FileStateStore{Path: filepath.Join(t.TempDir(), "state.json")}
	ctx := context.Background()
	if err := store.Save(ctx, &State{}, 0); err != nil {
		t.Fatal(err)
	}
	_, version, err := store.Load(ctx)
	if err != nil {
		t.Fatal(err)
	}
	// Another poller writes in between.
	time.Sleep(10 * time.Millisecond)
	later := time.Now().Add(time.Second)
	if err := os.Chtimes(store.Path, later, later); err != nil {
		t.Fatal(err)
	}
	if err := store.Save(ctx, &State{}, version); !errors.Is(err, ErrStateConflict) {
		t.Fatalf("got %v, want conflict", err)
	}
}

func TestPruneBoundsMemory(t *testing.T) {
	now := time.Date(2026, 9, 13, 0, 0, 0, 0, time.UTC)
	s := &State{}
	st := s.source("x")
	st.Seen["old"] = now.Add(-30 * 24 * time.Hour).Unix()
	for i := range 10 {
		st.Seen[fmt.Sprint(i)] = now.Add(-time.Duration(i) * time.Hour).Unix()
	}
	s.Prune(now, 21*24*time.Hour, 5)
	if _, ok := st.Seen["old"]; ok || len(st.Seen) != 5 {
		t.Fatalf("seen after prune: %v", st.Seen)
	}
	if _, ok := st.Seen["0"]; !ok {
		t.Fatal("newest entry evicted")
	}
}
