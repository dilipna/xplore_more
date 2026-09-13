// Command extractcheck measures real-world fetch+extraction quality per source.
//
// It discovers current items (dry run, nothing published), samples up to -per-source
// URLs from each source, fetches and extracts them with production settings, and prints
// per-source success rates. Use it before enabling a new source and to catch
// silent regressions (a site moving to client-side rendering, bot blocking).
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/extract"
	"github.com/dilipna/xploremore/apps/edge-go/internal/fetch"
	"github.com/dilipna/xploremore/apps/edge-go/internal/poll"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
	"github.com/dilipna/xploremore/apps/edge-go/internal/ssrf"
)

type result struct {
	source  string
	outcome string // ok | fetch_permanent | fetch_transient | no_content
	words   int
}

func main() {
	registry := flag.String("sources", "../../config/sources.yaml", "source registry")
	perSource := flag.Int("per-source", 3, "URLs sampled per source")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	srcs, err := sources.Load(*registry)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	opts := fetch.DefaultOptions()
	fetcher := fetch.New(ssrf.DefaultPolicy(), opts)
	mem := &bus.Memory{}
	p := &poll.Poller{
		Client: fetcher.Client(), Publisher: mem, UserAgent: opts.UserAgent,
		State:           poll.FileStateStore{Path: fmt.Sprintf("%s/xm-extractcheck-%d.json", os.TempDir(), time.Now().UnixNano())},
		DiscoveredTopic: "dry-run", Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Now: time.Now, PerSourceTimout: 45 * time.Second,
	}
	if _, err := p.RunOnce(ctx, srcs); err != nil && !errors.Is(err, poll.ErrStateConflict) {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	bySource := map[string][]events.ArticleDiscovered{}
	for _, m := range mem.Snapshot() {
		var env events.Envelope[events.ArticleDiscovered]
		if json.Unmarshal(m.Data, &env) == nil && len(bySource[env.Data.SourceID]) < *perSource {
			bySource[env.Data.SourceID] = append(bySource[env.Data.SourceID], env.Data)
		}
	}

	var (
		mu      sync.Mutex
		results []result
		wg      sync.WaitGroup
		sem     = make(chan struct{}, 12)
	)
	for sourceID, items := range bySource {
		for _, d := range items {
			wg.Add(1)
			go func() {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				r := result{source: sourceID}
				res, err := fetcher.Get(ctx, d.CanonicalURL)
				switch {
				case errors.Is(err, fetch.ErrPermanent):
					r.outcome = "fetch_permanent"
				case err != nil:
					r.outcome = "fetch_transient"
				default:
					title := ""
					if d.FeedTitle != nil {
						title = *d.FeedTitle
					}
					if doc, err := extract.FromHTML(res.Body, res.FinalURL, title); err != nil {
						r.outcome = "no_content"
					} else {
						r.outcome, r.words = "ok", doc.WordCount
					}
				}
				mu.Lock()
				results = append(results, r)
				mu.Unlock()
			}()
		}
	}
	wg.Wait()

	type agg struct {
		total, ok, words int
		failures         []string
	}
	table := map[string]*agg{}
	overall := &agg{}
	for _, r := range results {
		a := table[r.source]
		if a == nil {
			a = &agg{}
			table[r.source] = a
		}
		for _, x := range []*agg{a, overall} {
			x.total++
			if r.outcome == "ok" {
				x.ok++
				x.words += r.words
			} else {
				x.failures = append(x.failures, r.outcome)
			}
		}
	}
	ids := make([]string, 0, len(table))
	for id := range table {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	fmt.Printf("%-22s %6s %8s  %s\n", "source", "ok", "avg_words", "failures")
	for _, id := range ids {
		a := table[id]
		avg := 0
		if a.ok > 0 {
			avg = a.words / a.ok
		}
		fmt.Printf("%-22s %2d/%-3d %8d  %s\n", id, a.ok, a.total, avg, strings.Join(a.failures, ","))
	}
	fmt.Printf("\nOVERALL extraction success: %d/%d (%.0f%%)\n", overall.ok, overall.total, 100*float64(overall.ok)/float64(max(overall.total, 1)))
}
