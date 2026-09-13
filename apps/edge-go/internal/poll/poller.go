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
}

// SourceReport summarizes one source's poll.
type SourceReport struct {
	SourceID  string `json:"source_id"`
	Found     int    `json:"found"`
	Published int    `json:"published"`
	Skipped   int    `json:"skipped_seen"`
	Invalid   int    `json:"invalid_url"`
	NotMod    bool   `json:"not_modified,omitempty"`
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

	var items []Item
	var err error
	switch src.Kind {
	case sources.KindHN:
		items, err = fetchHN(srcCtx, p.Client, src, local, p.UserAgent)
	default:
		items, err = fetchFeed(srcCtx, p.Client, src, local, p.UserAgent)
	}

	now := p.Now().UTC()
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

	switch {
	case errors.Is(err, errNotModified):
		report.NotMod = true
		return report
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
		env := events.NewDiscovered(sourceName, p.discoveredData(src, it, canonicalURL, articleID, now), now)
		if err := bus.PublishJSON(srcCtx, p.Publisher, p.DiscoveredTopic, env.Type, env); err != nil {
			report.Error = "publish: " + err.Error()
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

func (p *Poller) discoveredData(src sources.Source, it Item, canonicalURL, articleID string, now time.Time) events.ArticleDiscovered {
	d := events.ArticleDiscovered{
		ArticleID:    articleID,
		URL:          truncate(it.URL, 2048),
		CanonicalURL: canonicalURL,
		SourceID:     src.ID,
		DiscoveredAt: events.Timestamp(now),
	}
	if it.PublishedAt != nil {
		ts := events.Timestamp(*it.PublishedAt)
		d.PublishedAt = &ts
	}
	if title := truncate(strings.Join(strings.Fields(it.Title), " "), titleRunes); title != "" {
		d.FeedTitle = &title
	}
	if summary := truncate(strings.Join(strings.Fields(stripTags(it.Summary)), " "), summaryRunes); summary != "" {
		d.FeedSummary = &summary
	}
	if it.HNItemID != nil {
		observed := events.Timestamp(now)
		d.Signals = events.Signals{HNItemID: it.HNItemID, HNPoints: it.HNPoints, HNComments: it.HNComments, ObservedAt: &observed}
	}
	return d
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
