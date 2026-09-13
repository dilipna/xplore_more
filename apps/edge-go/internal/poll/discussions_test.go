package poll

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
)

const longText = "We keep hitting the same failure: the job silently drops rows after a schema change and nothing alerts us."

// discussionSource returns a registry entry with defaults applied the way Parse does.
func discussionSource(t *testing.T, serverURL, yaml string) sources.Source {
	t.Helper()
	entry := strings.Replace(yaml, "{", `{url: "https://api.example", `, 1)
	srcs, err := sources.Parse([]byte("sources:\n  - " + entry))
	if err != nil {
		t.Fatal(err)
	}
	srcs[0].URL = serverURL // the registry requires https; httptest serves plain http
	return srcs[0]
}

// failAfter lets `ok` publishes succeed, then fails every later one.
type failAfter struct {
	*bus.Memory
	ok int
}

func (f *failAfter) Publish(ctx context.Context, topic string, data []byte, attrs map[string]string) error {
	if len(f.Snapshot()) >= f.ok {
		return errors.New("pubsub down")
	}
	return f.Memory.Publish(ctx, topic, data, attrs)
}

func decodeDiscovered(t *testing.T, msgs []bus.Message) []events.ArticleDiscovered {
	t.Helper()
	out := make([]events.ArticleDiscovered, 0, len(msgs))
	for _, m := range msgs {
		var env events.Envelope[events.ArticleDiscovered]
		if err := json.Unmarshal(m.Data, &env); err != nil {
			t.Fatal(err)
		}
		if _, err := events.NormalizeKind(env.Data.DocKind, env.Data.Discussion); err != nil {
			t.Fatalf("published contract-invalid event: %v", err)
		}
		out = append(out, env.Data)
	}
	return out
}

func TestAskHNPublishesMaturedPostsWithHashedAuthors(t *testing.T) {
	var filters atomic.Value
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		filters.Store(r.URL.Query().Get("numericFilters"))
		fmt.Fprintf(w, `{"hits":[
			{"objectID":"1","title":"Ask HN: How do you monitor data pipelines?","story_text":"<p>%s</p><p>Is there a tool for x &lt; y checks?</p>","author":"Alice","points":42,"num_comments":17,"created_at_i":1789250000},
			{"objectID":"2","title":"Ask HN: short","story_text":"too short","author":"bob","points":1,"num_comments":0,"created_at_i":1789250000},
			{"objectID":"3","title":"Ask HN: link only","story_text":"","author":"carol","points":3,"num_comments":0,"created_at_i":1789250000}
		]}`, longText)
	}))
	defer srv.Close()

	pub := &bus.Memory{}
	p := newPoller(t, pub)
	p.AuthorSalt = "salt"
	src := discussionSource(t, srv.URL, `{id: hn-ask, kind: hn_algolia, name: x, authority: 0.5, tags: [ask_hn], min_age_hours: 12, max_age_hours: 60}`)
	reports, err := p.RunOnce(context.Background(), []sources.Source{src})
	if err != nil {
		t.Fatal(err)
	}
	now := p.Now()
	wantFilter := fmt.Sprintf("created_at_i>%d,created_at_i<%d", now.Add(-60*time.Hour).Unix(), now.Add(-12*time.Hour).Unix())
	if filters.Load() != wantFilter {
		t.Fatalf("maturity window %q, want %q", filters.Load(), wantFilter)
	}
	docs := decodeDiscovered(t, pub.Snapshot())
	if len(docs) != 1 || reports[0].Published != 1 {
		t.Fatalf("published %d (report %+v)", len(docs), reports[0])
	}
	d := docs[0]
	if d.CanonicalURL != "https://news.ycombinator.com/item?id=1" || d.DocKind != events.KindDiscussion {
		t.Fatalf("doc %+v", d)
	}
	if !strings.Contains(*d.FeedSummary, "x < y checks") || !strings.HasPrefix(*d.FeedSummary, "Ask HN: How do you monitor") {
		t.Fatalf("text not plain or title missing: %q", *d.FeedSummary)
	}
	disc := d.Discussion
	wantHash := events.Sha256Hex("salt|hn|alice")
	if disc.AuthorHash == nil || *disc.AuthorHash != wantHash || disc.ParentURL != nil || *disc.Engagement.Points != 42 || *disc.Engagement.Comments != 17 {
		t.Fatalf("discussion %+v", disc)
	}
	raw, _ := json.Marshal(pub.Snapshot())
	if strings.Contains(strings.ToLower(string(raw)), "alice") {
		t.Fatal("raw username leaked into a published event")
	}
}

func hnCommentsServer(t *testing.T, itemFetches *atomic.Int32) *httptest.Server {
	t.Helper()
	comment := func(id int, author string, replies int) string {
		children := make([]string, replies)
		for i := range children {
			children[i] = fmt.Sprintf(`{"id":%d,"type":"comment","author":"r","text":"reply","children":[]}`, id*100+i)
		}
		return fmt.Sprintf(`{"id":%d,"type":"comment","author":%q,"text":"<p>%s</p>","created_at_i":1789260000,"children":[%s]}`,
			id, author, longText, strings.Join(children, ","))
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/search":
			if !strings.HasPrefix(r.URL.Query().Get("numericFilters"), "points>=100,") {
				t.Errorf("filters %q", r.URL.Query().Get("numericFilters"))
			}
			_, _ = w.Write([]byte(`{"hits":[{"objectID":"500"}]}`))
		case r.URL.Path == "/items/500":
			itemFetches.Add(1)
			fmt.Fprintf(w, `{"id":500,"type":"story","title":"Postgres at scale","children":[%s,%s,%s,%s]}`,
				comment(11, "few", 1),
				comment(12, "many", 5),
				`{"id":13,"type":"comment","author":"","text":"deleted","children":[]}`,
				comment(14, "mid", 3))
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestHNCommentsRankByRepliesAndCompleteThreads(t *testing.T) {
	var fetches atomic.Int32
	srv := hnCommentsServer(t, &fetches)
	src := discussionSource(t, srv.URL, `{id: hn-comments, kind: hn_comments, name: x, authority: 0.5, min_points: 100, per_thread: 2}`)

	// An outage after the thread's FIRST comment published must not mark the thread seen,
	// or its second comment would never be published.
	mem := &bus.Memory{}
	pub := &failAfter{Memory: mem, ok: 1}
	p := newPoller(t, pub)
	p.AuthorSalt = "salt"
	if _, err := p.RunOnce(context.Background(), []sources.Source{src}); err != nil {
		t.Fatal(err)
	}
	if len(mem.Snapshot()) != 1 {
		t.Fatalf("setup: published %d before the outage", len(mem.Snapshot()))
	}
	pub.ok = 1 << 30 // outage over
	if _, err := p.RunOnce(context.Background(), []sources.Source{src}); err != nil {
		t.Fatal(err)
	}
	if fetches.Load() != 2 {
		t.Fatalf("thread fetched %d times, want a retry after the outage", fetches.Load())
	}
	docs := decodeDiscovered(t, mem.Snapshot())
	if len(docs) != 2 {
		t.Fatalf("per_thread cap / completeness: published %d", len(docs))
	}
	if docs[0].CanonicalURL != "https://news.ycombinator.com/item?id=12" || docs[1].CanonicalURL != "https://news.ycombinator.com/item?id=14" {
		t.Fatalf("not ranked by replies: %s, %s", docs[0].CanonicalURL, docs[1].CanonicalURL)
	}
	d := docs[0]
	if *d.FeedTitle != "Comment on: Postgres at scale" || d.Discussion.ParentURL == nil ||
		*d.Discussion.ParentURL != "https://news.ycombinator.com/item?id=500" || *d.Discussion.Engagement.Comments != 5 {
		t.Fatalf("comment doc %+v %+v", d, d.Discussion)
	}

	// Thread fully published: the next run does not expand it again.
	if _, err := p.RunOnce(context.Background(), []sources.Source{src}); err != nil {
		t.Fatal(err)
	}
	if fetches.Load() != 2 {
		t.Fatalf("completed thread refetched: %d", fetches.Load())
	}
}

// ctxPublisher fails when its context is done, as the real Pub/Sub client does.
type ctxPublisher struct{ *bus.Memory }

func (c ctxPublisher) Publish(ctx context.Context, topic string, data []byte, attrs map[string]string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	return c.Memory.Publish(ctx, topic, data, attrs)
}

func TestSlowThreadLeavesTimeToPublishGatheredItems(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/search":
			_, _ = w.Write([]byte(`{"hits":[{"objectID":"1"},{"objectID":"2"}]}`))
		case "/items/1":
			fmt.Fprintf(w, `{"id":1,"type":"story","title":"Fast","children":[{"id":10,"type":"comment","author":"a","text":"%s","children":[]}]}`, longText)
		case "/items/2":
			select { // a huge thread: slower than the whole source budget
			case <-r.Context().Done():
			case <-time.After(3 * time.Second):
			}
		}
	}))
	defer srv.Close()

	mem := &bus.Memory{}
	p := newPoller(t, ctxPublisher{mem})
	p.PerSourceTimout = 800 * time.Millisecond
	src := discussionSource(t, srv.URL, `{id: hn-comments, kind: hn_comments, name: x, authority: 0.5}`)
	reports, err := p.RunOnce(context.Background(), []sources.Source{src})
	if err != nil {
		t.Fatal(err)
	}
	r := reports[0]
	if r.Error != "" || r.Warning == "" || r.Published != 1 || len(mem.Snapshot()) != 1 {
		t.Fatalf("gathered items must still publish after a fetch timeout: %+v", r)
	}
}

func TestGitHubQueriesFitTheSearchLimitAndCoverEveryRepo(t *testing.T) {
	repos := make([]string, 40)
	for i := range repos {
		repos[i] = fmt.Sprintf("some-organization-%02d/a-fairly-long-repository-name", i)
	}
	queries := githubQueries(repos, time.Date(2026, 8, 14, 0, 0, 0, 0, time.UTC))
	covered := 0
	for _, q := range queries {
		if len(q) > githubQueryLimit {
			t.Fatalf("query length %d > %d", len(q), githubQueryLimit)
		}
		if !strings.HasPrefix(q, "is:issue is:open updated:>2026-08-14 ") {
			t.Fatalf("query %q", q)
		}
		covered += strings.Count(q, " repo:")
	}
	if covered != len(repos) {
		t.Fatalf("covered %d of %d repos", covered, len(repos))
	}
}

func TestGitHubRateLimitKeepsGatheredIssues(t *testing.T) {
	var calls atomic.Int32
	var auth atomic.Value
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth.Store(r.Header.Get("Authorization"))
		if calls.Add(1) > 1 {
			w.Header().Set("X-RateLimit-Remaining", "0")
			w.WriteHeader(http.StatusForbidden)
			return
		}
		fmt.Fprintf(w, `{"items":[
			{"html_url":"https://github.com/o/r/issues/1","title":"Streaming breaks with tool calls","body":"<!-- template: describe the bug -->%s","comments":9,"created_at":"2026-09-01T00:00:00Z","user":{"login":"dev1","type":"User"},"reactions":{"total_count":31,"+1":25}},
			{"html_url":"https://github.com/o/r/pull/2","title":"Fix streaming","body":"%s","user":{"login":"dev2","type":"User"},"pull_request":{"url":"x"}},
			{"html_url":"https://github.com/o/r/issues/3","title":"Dependency update","body":"%s","user":{"login":"renovate[bot]","type":"Bot"}}
		]}`, longText, longText, longText)
	}))
	defer srv.Close()

	repos := make([]string, 30)
	for i := range repos {
		repos[i] = fmt.Sprintf("organization-%02d/repository-%02d", i, i)
	}
	src := discussionSource(t, srv.URL, `{id: gh, kind: github_issues, name: x, authority: 0.5, max_age_hours: 720, repos: [`+strings.Join(repos, ",")+`]}`)
	pub := &bus.Memory{}
	p := newPoller(t, pub)
	p.GitHubToken = "tkn"
	reports, err := p.RunOnce(context.Background(), []sources.Source{src})
	if err != nil {
		t.Fatal(err)
	}
	if calls.Load() < 2 || auth.Load() != "Bearer tkn" {
		t.Fatalf("calls %d auth %v", calls.Load(), auth.Load())
	}
	r := reports[0]
	if r.Warning == "" || r.Error != "" || r.Published != 1 {
		t.Fatalf("rate limit must yield a partial result, got %+v", r)
	}
	d := decodeDiscovered(t, pub.Snapshot())[0]
	if strings.Contains(*d.FeedSummary, "template") || *d.Discussion.Engagement.Reactions != 31 || *d.Discussion.Engagement.Points != 25 {
		t.Fatalf("issue doc %q %+v", *d.FeedSummary, d.Discussion.Engagement)
	}
	if d.Discussion.AuthorHash != nil {
		t.Fatal("author_hash must be null when no salt is configured")
	}
}

func TestLobstersThreadsUseTopLevelCommentsInWindow(t *testing.T) {
	var threadFetches atomic.Int32
	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/t/ask.json":
			fmt.Fprintf(w, `[
				{"short_id":"abc","short_id_url":"%[1]s/s/abc","created_at":"2026-09-12T04:00:00.000-05:00","title":"How do you test migrations?","score":12,"comment_count":3,"description_plain":"%[2]s","submitter_user":"asker"},
				{"short_id":"new","created_at":"2026-09-13T09:30:00.000Z","title":"Too fresh","score":50,"comment_count":1,"submitter_user":"x"},
				{"short_id":"low","created_at":"2026-09-12T04:00:00.000Z","title":"Low score","score":1,"comment_count":1,"submitter_user":"x"}
			]`, srvURL, longText)
		case "/s/abc.json":
			threadFetches.Add(1)
			fmt.Fprintf(w, `{"short_id":"abc","comments":[
				{"short_id_url":"%[1]s/c/c1","created_at":"2026-09-12T05:00:00.000-05:00","score":2,"comment_plain":"%[2]s","depth":0,"commenting_user":"u1"},
				{"short_id_url":"%[1]s/c/c2","created_at":"2026-09-12T05:00:00.000-05:00","score":9,"comment_plain":"%[2]s","depth":0,"commenting_user":{"username":"u2"}},
				{"short_id_url":"%[1]s/c/c3","created_at":"2026-09-12T05:00:00.000-05:00","score":20,"comment_plain":"%[2]s","depth":1,"commenting_user":"u3"},
				{"short_id_url":"%[1]s/c/c4","created_at":"2026-09-12T05:00:00.000-05:00","score":30,"comment_plain":"%[2]s","depth":0,"is_deleted":true,"commenting_user":"u4"}
			]}`, srvURL, longText)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()
	srvURL = srv.URL

	src := discussionSource(t, srv.URL, `{id: lob, kind: lobsters, name: x, authority: 0.5, tags: [ask], min_points: 5, per_thread: 5}`)
	pub := &bus.Memory{}
	p := newPoller(t, pub)
	p.AuthorSalt = "salt"
	if _, err := p.RunOnce(context.Background(), []sources.Source{src}); err != nil {
		t.Fatal(err)
	}
	docs := decodeDiscovered(t, pub.Snapshot())
	if len(docs) != 3 || threadFetches.Load() != 1 {
		t.Fatalf("published %d docs, %d thread fetches", len(docs), threadFetches.Load())
	}
	if docs[0].Discussion.ParentURL != nil || !strings.HasSuffix(docs[1].CanonicalURL, "/c/c2") || !strings.HasSuffix(docs[2].CanonicalURL, "/c/c1") {
		t.Fatalf("order/filters wrong: %s %s %s", docs[0].CanonicalURL, docs[1].CanonicalURL, docs[2].CanonicalURL)
	}
	if *docs[1].Discussion.AuthorHash != events.Sha256Hex("salt|lobsters|u2") {
		t.Fatal("object-form commenting_user not handled")
	}
	if _, err := p.RunOnce(context.Background(), []sources.Source{src}); err != nil {
		t.Fatal(err)
	}
	if threadFetches.Load() != 1 || len(pub.Snapshot()) != 3 {
		t.Fatalf("second run refetched or republished: fetches %d msgs %d", threadFetches.Load(), len(pub.Snapshot()))
	}
}

func TestStackExchangeQuestionsAndQuotaWarning(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if q.Get("site") != "stackoverflow" || q.Get("filter") != "withbody" || q.Get("fromdate") == "" || q.Get("todate") == "" {
			t.Errorf("query %v", q)
		}
		fmt.Fprintf(w, `{"items":[
			{"question_id":7,"link":"https://stackoverflow.com/questions/7/pgvector-index","title":"pgvector HNSW index &quot;not used&quot;","body":"<p>%s</p><pre><code>if a &lt; b</code></pre>","score":-1,"answer_count":0,"creation_date":1789250000,"owner":{"user_id":99}}
		],"quota_remaining":5}`, longText)
	}))
	defer srv.Close()

	src := discussionSource(t, srv.URL, `{id: so, kind: stackexchange, name: x, authority: 0.5, site: stackoverflow, tags: [pgvector, kubernetes]}`)
	pub := &bus.Memory{}
	p := newPoller(t, pub)
	p.AuthorSalt = "salt"
	reports, err := p.RunOnce(context.Background(), []sources.Source{src})
	if err != nil {
		t.Fatal(err)
	}
	if reports[0].Warning == "" || reports[0].Published != 1 {
		t.Fatalf("low quota must warn and stop early: %+v", reports[0])
	}
	d := decodeDiscovered(t, pub.Snapshot())[0]
	if *d.FeedTitle != `pgvector HNSW index "not used"` || !strings.Contains(*d.FeedSummary, "if a < b") {
		t.Fatalf("unescaping: %q / %q", *d.FeedTitle, *d.FeedSummary)
	}
	if *d.Discussion.Engagement.Points != -1 || *d.Discussion.AuthorHash != events.Sha256Hex("salt|stackexchange|stackoverflow:99") {
		t.Fatalf("discussion %+v", d.Discussion)
	}
}
