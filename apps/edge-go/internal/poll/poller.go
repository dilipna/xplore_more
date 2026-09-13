// Package poll discovers new articles and publishes xm.article.discovered.v1 events.
//
// Run model: a Cloud Run Job triggered by Cloud Scheduler. Each run loads one state
// object, polls every source concurrently, publishes events for unseen items, and saves
// state with an optimistic-concurrency precondition.
//
// Ordering matters for correctness. An item is marked seen only after its publish
// succeeded, and state is saved only after all publishes. A crash can therefore cause a
// re-publish (absorbed by downstream idempotency) but never a silently lost article.
package poll

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/canon"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
)

const (
	sourceName     = "edge/poller"
	summaryRunes   = 2000
	titleRunes     = 500
	seenRetention  = 21 * 24 * time.Hour
	seenPerSource  = 3000
	maxConcurrency = 8
	// fetchBudgetPercent of PerSourceTimout is for fetching; the rest is reserved to publish.
	fetchBudgetPercent = 75
)

// Poller wires sources to the event bus.
type Poller struct {
	Client          *http.Client
	Publisher       bus.Publisher
	State           StateStore
	DiscoveredTopic string
	UserAgent       string
	Log             *slog.Logger
	Now             func() time.Time
	PerSourceTimout time.Duration

	// AuthorSalt keys author_hash for discussion sources. Without it author_hash is null
	// and distinct voices cannot be counted downstream.
	AuthorSalt string
	// GitHubToken is optional; it raises the search quota from 10 to 30 requests/minute.
	GitHubToken string
}

// SourceReport summarizes one source's poll.
type SourceReport struct {
	SourceID  string `json:"source_id"`
	Found     int    `json:"found"`
	Published int    `json:"published"`
	Skipped   int    `json:"skipped_seen"`
	Invalid   int    `json:"invalid_url"`
	NotMod    bool   `json:"not_modified,omitempty"`
	Warning   string `json:"warning,omitempty"` // partial result (e.g. quota), items still published
	Error     string `json:"error,omitempty"`
}

// RunOnce polls all enabled sources a single time.
func (p *Poller) RunOnce(ctx context.Context, srcs []sources.Source) ([]SourceReport, error) {
	state, version, err := p.State.Load(ctx)
	if err != nil {
		return nil, err
	}

	var (
		mu      sync.Mutex // guards state maps during concurrent source polls
		wg      sync.WaitGroup
		reports = make([]SourceReport, 0, len(srcs))
		sem     = make(chan struct{}, maxConcurrency)
	)
	for _, src := range srcs {
		if src.Disabled {
			continue
		}
		mu.Lock()
		st := state.source(src.ID)
		mu.Unlock()
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			report := p.pollSource(ctx, src, st, &mu)
			mu.Lock()
			reports = append(reports, report)
			mu.Unlock()
		}()
	}
	wg.Wait()

	state.Prune(p.Now(), seenRetention, seenPerSource)
	sort.Slice(reports, func(i, j int) bool { return reports[i].SourceID < reports[j].SourceID })
	if err := p.State.Save(ctx, state, version); err != nil {
		return reports, err
	}
	return reports, nil
}

func (p *Poller) pollSource(ctx context.Context, src sources.Source, st *SourceState, mu *sync.Mutex) SourceReport {
	report := SourceReport{SourceID: src.ID}
	srcCtx, cancel := context.WithTimeout(ctx, p.PerSourceTimout)
	defer cancel()

	// Work on a private copy of the seen set; merge under the lock at the end.
	mu.Lock()
	local := &SourceState{ETag: st.ETag, LastModified: st.LastModified, Seen: make(map[string]int64, len(st.Seen))}
	for k, v := range st.Seen {
		local.Seen[k] = v
	}
	mu.Unlock()
	prevETag, prevLastModified := local.ETag, local.LastModified

	now := p.Now().UTC()
	// Fetching gets a share of the source budget so publishing always has time left. A
	// fetch that used the whole deadline once made every publish fail on an expired context.
	fetchCtx, cancelFetch := context.WithTimeout(srcCtx, p.PerSourceTimout*fetchBudgetPercent/100)
	var items []Item
	var err error
	switch src.Kind {
	case sources.KindHN:
		items, err = fetchHN(fetchCtx, p.Client, src, local, p.UserAgent)
	case sources.KindHNAlgolia:
		items, err = fetchHNAlgolia(fetchCtx, p.Client, src, p.UserAgent, now)
	case sources.KindHNComments:
		items, err = fetchHNComments(fetchCtx, p.Client, src, local, p.UserAgent, now)
	case sources.KindGitHubIssues:
		items, err = fetchGitHubIssues(fetchCtx, p.Client, src, p.UserAgent, p.GitHubToken, now)
	case sources.KindLobsters:
		items, err = fetchLobsters(fetchCtx, p.Client, src, local, p.UserAgent, now)
	case sources.KindStackExchange:
		items, err = fetchStackExchange(fetchCtx, p.Client, src, p.UserAgent, now)
	default:
		items, err = fetchFeed(fetchCtx, p.Client, src, local, p.UserAgent)
	}
	cancelFetch()

	defer func() {
		mu.Lock()
		defer mu.Unlock()
		st.ETag, st.LastModified = local.ETag, local.LastModified
		for k, v := range local.Seen {
			st.Seen[k] = v
		}
		if report.Error != "" {
			st.Failures++
			st.LastError = report.Error
		} else {
			st.Failures = 0
			st.LastError = ""
			st.LastSuccess = now.Unix()
		}
	}()

	var partial *partialError
	switch {
	case errors.Is(err, errNotModified):
		report.NotMod = true
		return report
	case errors.As(err, &partial):
		report.Warning = err.Error()
		p.Log.Warn("source poll partial", "source_id", src.ID, "error", err)
	case err != nil:
		report.Error = err.Error()
		p.Log.Warn("source poll failed", "source_id", src.ID, "error", err)
		return report
	}

	report.Found = len(items)
	for _, it := range items {
		canonicalURL, err := canon.URL(it.URL)
		if err != nil {
			report.Invalid++
			continue
		}
		articleID := canon.ArticleID(canonicalURL)
		if local.Seen[articleID] != 0 {
			report.Skipped++
			if it.ExternalID != "" {
				local.Seen[it.ExternalID] = now.Unix()
			}
			continue
		}
		data, ok := p.discoveredData(src, it, canonicalURL, articleID, now)
		if !ok {
			report.Invalid++
			continue
		}
		env := events.NewDiscovered(sourceName, data, now)
		if err := bus.PublishJSON(srcCtx, p.Publisher, p.DiscoveredTopic, env.Type, env); err != nil {
			report.Error = "publish: " + err.Error()
			p.Log.Warn("publish failed; remaining items stay unseen", "source_id", src.ID, "error", err)
			// Unpublished items stay unseen. Restoring the validators forces a full
			// re-fetch next run; keeping the new ETag would get a 304 and lose them.
			local.ETag, local.LastModified = prevETag, prevLastModified
			return report
		}
		local.Seen[articleID] = now.Unix()
		if it.ExternalID != "" {
			local.Seen[it.ExternalID] = now.Unix()
		}
		report.Published++
	}
	return report
}

// discoveredData maps an item to the contract. ok is false when a discussion's thread or
// parent URL cannot be canonicalized.
func (p *Poller) discoveredData(src sources.Source, it Item, canonicalURL, articleID string, now time.Time) (events.ArticleDiscovered, bool) {
	d := events.ArticleDiscovered{
		ArticleID:    articleID,
		URL:          truncate(it.URL, 2048),
		CanonicalURL: canonicalURL,
		SourceID:     src.ID,
		DiscoveredAt: events.Timestamp(now),
		DocKind:      events.KindArticle,
	}
	if it.PublishedAt != nil {
		ts := events.Timestamp(*it.PublishedAt)
		d.PublishedAt = &ts
	}
	if title := truncate(strings.Join(strings.Fields(it.Title), " "), titleRunes); title != "" {
		d.FeedTitle = &title
	}
	summary := it.Summary
	if it.Discussion == nil {
		summary = stripTags(summary) // discussion text is already plain; "a < b" must survive
	}
	if summary := truncate(strings.Join(strings.Fields(summary), " "), summaryRunes); summary != "" {
		d.FeedSummary = &summary
	}
	if it.HNItemID != nil {
		observed := events.Timestamp(now)
		d.Signals = events.Signals{HNItemID: it.HNItemID, HNPoints: it.HNPoints, HNComments: it.HNComments, ObservedAt: &observed}
	}
	if it.Discussion != nil {
		disc, ok := p.discussion(it.Discussion)
		if !ok || d.FeedTitle == nil || d.FeedSummary == nil {
			return d, false
		}
		d.DocKind, d.Discussion = events.KindDiscussion, disc
	}
	return d, true
}

func (p *Poller) discussion(m *discussionMeta) (*events.Discussion, bool) {
	thread, err := canon.URL(m.ThreadURL)
	if err != nil {
		return nil, false
	}
	disc := &events.Discussion{
		Platform:   m.Platform,
		ThreadURL:  thread,
		AuthorHash: p.authorHash(m.Platform, m.Author),
		Engagement: events.Engagement{Points: m.Points, Comments: m.Comments, Reactions: m.Reactions},
	}
	if m.ParentURL != "" {
		parent, err := canon.URL(m.ParentURL)
		if err != nil {
			return nil, false
		}
		disc.ParentURL = &parent
	}
	return disc, true
}

// authorHash implements discussion.v1: sha256(salt | platform | lowercase handle). The
// platform is part of the key because equal handles on two sites need not be one person.
func (p *Poller) authorHash(platform, handle string) *string {
	handle = strings.ToLower(strings.TrimSpace(handle))
	if handle == "" || p.AuthorSalt == "" {
		return nil
	}
	h := events.Sha256Hex(p.AuthorSalt + "|" + platform + "|" + handle)
	return &h
}

func truncate(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n])
}

// stripTags removes markup from feed summaries (they are display hints, never rendered).
func stripTags(s string) string {
	var b strings.Builder
	inTag := false
	for _, r := range s {
		switch {
		case r == '<':
			inTag = true
		case r == '>':
			inTag = false
			b.WriteRune(' ')
		case !inTag:
			b.WriteRune(r)
		}
	}
	return b.String()
}
