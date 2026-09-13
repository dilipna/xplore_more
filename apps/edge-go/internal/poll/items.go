package poll

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/mmcdole/gofeed"

	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
)

const maxFeedBytes = 10 << 20

// Item is a candidate article found in a source.
type Item struct {
	URL         string
	Title       string
	Summary     string
	PublishedAt *time.Time
	ExternalID  string // e.g. HN item id; used to avoid re-fetching API items
	HNItemID    *int64
	HNPoints    *int
	HNComments  *int
	Discussion  *discussionMeta // set by discussion fetchers; Summary is then plain text
}

// errNotModified signals a 304: nothing new, not a failure.
var errNotModified = errors.New("not modified")

// fetchFeed performs a conditional GET and parses RSS/Atom/JSON Feed.
func fetchFeed(ctx context.Context, client *http.Client, src sources.Source, st *SourceState, userAgent string) ([]Item, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, src.URL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Accept", "application/rss+xml, application/atom+xml, application/feed+json, application/xml;q=0.9, */*;q=0.1")
	if st.ETag != "" {
		req.Header.Set("If-None-Match", st.ETag)
	}
	if st.LastModified != "" {
		req.Header.Set("If-Modified-Since", st.LastModified)
	}
	res, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusNotModified {
		return nil, errNotModified
	}
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("feed status %d", res.StatusCode)
	}
	feed, err := gofeed.NewParser().Parse(io.LimitReader(res.Body, maxFeedBytes))
	if err != nil {
		return nil, fmt.Errorf("parse feed: %w", err)
	}
	st.ETag = res.Header.Get("ETag")
	st.LastModified = res.Header.Get("Last-Modified")

	items := make([]Item, 0, len(feed.Items))
	for _, it := range feed.Items {
		link := strings.TrimSpace(it.Link)
		if link == "" && len(it.Links) > 0 {
			link = strings.TrimSpace(it.Links[0])
		}
		if link == "" {
			continue
		}
		published := it.PublishedParsed
		if published == nil {
			published = it.UpdatedParsed
		}
		// Atom puts release notes and full posts in <content>; RSS usually uses
		// <description>. Keep whichever says more (the ingestor falls back to it).
		summary := strings.TrimSpace(it.Description)
		if content := strings.TrimSpace(it.Content); len(content) > len(summary) {
			summary = content
		}
		items = append(items, Item{
			URL:         link,
			Title:       strings.TrimSpace(it.Title),
			Summary:     summary,
			PublishedAt: published,
		})
		if len(items) >= src.MaxItems {
			break
		}
	}
	return items, nil
}

type hnItem struct {
	ID          int64  `json:"id"`
	Type        string `json:"type"`
	URL         string `json:"url"`
	Title       string `json:"title"`
	Score       int    `json:"score"`
	Descendants int    `json:"descendants"`
	Time        int64  `json:"time"`
	Dead        bool   `json:"dead"`
	Deleted     bool   `json:"deleted"`
}

// fetchHN lists new and top stories and resolves only item ids not seen before.
// Stories without an external URL (Ask HN) are skipped: we index articles, not threads.
func fetchHN(ctx context.Context, client *http.Client, src sources.Source, st *SourceState, userAgent string) ([]Item, error) {
	var ids []int64
	for _, list := range []string{"newstories", "topstories"} {
		var listIDs []int64
		if err := getJSON(ctx, client, fmt.Sprintf("%s/%s.json", src.URL, list), userAgent, &listIDs); err != nil {
			return nil, err
		}
		ids = append(ids, listIDs...)
	}

	var fresh []int64
	uniq := map[int64]bool{}
	for _, id := range ids {
		key := "hn:" + strconv.FormatInt(id, 10)
		if uniq[id] || st.Seen[key] != 0 {
			continue
		}
		uniq[id] = true
		fresh = append(fresh, id)
		if len(fresh) >= src.MaxItems {
			break
		}
	}

	items := make([]Item, len(fresh))
	valid := make([]bool, len(fresh))
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup
	for i, id := range fresh {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			var it hnItem
			if err := getJSON(ctx, client, fmt.Sprintf("%s/item/%d.json", src.URL, id), userAgent, &it); err != nil {
				return
			}
			key := "hn:" + strconv.FormatInt(id, 10)
			if it.Type != "story" || it.Dead || it.Deleted || it.URL == "" {
				items[i] = Item{ExternalID: key} // remember so we do not refetch it
				return
			}
			published := time.Unix(it.Time, 0).UTC()
			points, comments, itemID := it.Score, it.Descendants, it.ID
			items[i] = Item{
				URL: it.URL, Title: it.Title, PublishedAt: &published, ExternalID: key,
				HNItemID: &itemID, HNPoints: &points, HNComments: &comments,
			}
			valid[i] = true
		}()
	}
	wg.Wait()

	out := make([]Item, 0, len(items))
	for i, it := range items {
		if it.ExternalID == "" {
			continue // fetch failed: retry next run
		}
		if !valid[i] {
			st.Seen[it.ExternalID] = time.Now().Unix()
			continue
		}
		out = append(out, it)
	}
	return out, nil
}

func getJSON(ctx context.Context, client *http.Client, url, userAgent string, v any) error {
	return getJSONWithHeaders(ctx, client, url, userAgent, nil, v)
}
