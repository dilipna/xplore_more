package poll

// Discussion fetchers read public platform APIs and return posts and comments whose text
// is already plain. They share three policies:
//
//   - Maturity window: an item is read once, when it is between min_age_hours and
//     max_age_hours old, so its engagement has settled and is comparable across items.
//   - Thread completeness: a thread's key is marked seen only on its LAST emitted item.
//     pollSource stops at the first publish failure, so a thread is never marked seen
//     while some of its comments are still unpublished.
//   - Quotas: when a platform refuses mid-run (rate limit), items already gathered are
//     published and the source reports a warning instead of discarding them.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
)

const (
	// minDiscussionRunes matches the ingestor's minimum for API-provided text; shorter
	// items ("+1", "thanks") carry no problem statement.
	minDiscussionRunes = 80
	githubQueryLimit   = 256
	hnItemURL          = "https://news.ycombinator.com/item?id="
	commentTitlePrefix = "Comment on: "
	lowQuotaThreshold  = 20
)

// discussionMeta travels with an Item until the poller turns it into contract fields.
type discussionMeta struct {
	Platform  string
	ThreadURL string
	ParentURL string // empty for a thread's opening post
	Author    string // raw handle: hashed with the deployment salt, never published
	Points    *int
	Comments  *int
	Reactions *int
}

// partialError means a source returned some items before a platform refused (quota).
type partialError struct{ err error }

func (e *partialError) Error() string { return "partial: " + e.err.Error() }
func (e *partialError) Unwrap() error { return e.err }

// partialOr keeps gathered items when a later request fails.
func partialOr(items []Item, err error) ([]Item, error) {
	if len(items) > 0 {
		return items, &partialError{err}
	}
	return nil, err
}

// statusError is a non-200 API response.
type statusError struct {
	URL  string
	Code int
}

func (e *statusError) Error() string { return fmt.Sprintf("%s: status %d", e.URL, e.Code) }

func maturityWindow(src sources.Source, now time.Time) (from, to time.Time) {
	return now.Add(-time.Duration(src.MaxAgeHours) * time.Hour), now.Add(-time.Duration(src.MinAgeHours) * time.Hour)
}

func collapse(s string) string { return strings.Join(strings.Fields(s), " ") }

// htmlToText strips markup first and unescapes second, so an escaped "&lt;b&gt;" in a
// comment stays literal text. The result is stored and embedded, never rendered as HTML.
func htmlToText(s string) string { return collapse(html.UnescapeString(stripTags(s))) }

// openingText makes the title part of a post's text: for issues and questions the title
// is usually the clearest statement of the problem.
func openingText(title, body string) string {
	if body == "" {
		return title
	}
	return title + ". " + body
}

func longEnough(text string) bool { return utf8.RuneCountInString(text) >= minDiscussionRunes }

func intPtr(v int) *int { return &v }

func unixTime(sec int64) *time.Time {
	t := time.Unix(sec, 0).UTC()
	return &t
}

// finishThread applies the thread-completeness policy described at the top of the file.
func finishThread(st *SourceState, key string, thread []Item, now time.Time) []Item {
	if len(thread) == 0 {
		st.Seen[key] = now.Unix()
		return nil
	}
	thread[len(thread)-1].ExternalID = key
	return thread
}

// threadParallelism bounds concurrent thread expansions per source: fast enough for 60
// threads inside the fetch budget, gentle on community-run APIs.
const threadParallelism = 4

// fetchInOrder runs fetch for indexes 0..n-1 with bounded concurrency and returns results
// in index order, so callers can apply ordered, stop-at-first-error policies.
func fetchInOrder[T any](n int, fetch func(i int) (T, error)) ([]T, []error) {
	results := make([]T, n)
	errs := make([]error, n)
	sem := make(chan struct{}, threadParallelism)
	var wg sync.WaitGroup
	for i := range n {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[i], errs[i] = fetch(i)
		}()
	}
	wg.Wait()
	return results, errs
}

// --- Hacker News (Algolia) ----------------------------------------------------------

type algoliaHit struct {
	ObjectID    string `json:"objectID"`
	Title       string `json:"title"`
	StoryText   string `json:"story_text"`
	Author      string `json:"author"`
	Points      *int   `json:"points"`
	NumComments *int   `json:"num_comments"`
	CreatedAtI  int64  `json:"created_at_i"`
}

type algoliaSearch struct {
	Hits []algoliaHit `json:"hits"`
}

type algoliaItem struct {
	ID         int64         `json:"id"`
	Type       string        `json:"type"`
	Author     string        `json:"author"`
	Text       string        `json:"text"`
	Title      string        `json:"title"`
	CreatedAtI int64         `json:"created_at_i"`
	Children   []algoliaItem `json:"children"`
}

func algoliaWindowFilter(src sources.Source, now time.Time) string {
	from, to := maturityWindow(src, now)
	return fmt.Sprintf("created_at_i>%d,created_at_i<%d", from.Unix(), to.Unix())
}

// fetchHNAlgolia reads self posts (Ask HN) whose text states the question.
func fetchHNAlgolia(ctx context.Context, client *http.Client, src sources.Source, userAgent string, now time.Time) ([]Item, error) {
	var items []Item
	for _, tag := range src.Tags {
		q := url.Values{}
		q.Set("tags", tag)
		q.Set("numericFilters", algoliaWindowFilter(src, now))
		q.Set("hitsPerPage", strconv.Itoa(min(src.MaxItems, 1000)))
		var res algoliaSearch
		if err := getJSON(ctx, client, src.URL+"/search_by_date?"+q.Encode(), userAgent, &res); err != nil {
			return partialOr(items, err)
		}
		for _, h := range res.Hits {
			title := collapse(h.Title)
			text := openingText(title, htmlToText(h.StoryText))
			if title == "" || h.ObjectID == "" || h.StoryText == "" || !longEnough(text) {
				continue
			}
			link := hnItemURL + h.ObjectID
			items = append(items, Item{
				URL: link, Title: title, Summary: text, PublishedAt: unixTime(h.CreatedAtI),
				Discussion: &discussionMeta{
					Platform: events.PlatformHN, ThreadURL: link, Author: h.Author,
					Points: h.Points, Comments: h.NumComments,
				},
			})
		}
	}
	return items, nil
}

// fetchHNComments expands high-engagement stories into their top-level comments, ranked
// by reply count (HN does not expose comment scores; replies are the visible signal).
func fetchHNComments(ctx context.Context, client *http.Client, src sources.Source, st *SourceState, userAgent string, now time.Time) ([]Item, error) {
	q := url.Values{}
	q.Set("tags", "story")
	q.Set("numericFilters", fmt.Sprintf("points>=%d,%s", src.MinPoints, algoliaWindowFilter(src, now)))
	q.Set("hitsPerPage", strconv.Itoa(min(src.MaxThreads*3, 1000)))
	var res algoliaSearch
	if err := getJSON(ctx, client, src.URL+"/search?"+q.Encode(), userAgent, &res); err != nil {
		return nil, err
	}

	var ids []string
	for _, h := range res.Hits {
		if h.ObjectID != "" && st.Seen["hnthread:"+h.ObjectID] == 0 && len(ids) < src.MaxThreads {
			ids = append(ids, h.ObjectID)
		}
	}
	stories, errs := fetchInOrder(len(ids), func(i int) (algoliaItem, error) {
		var story algoliaItem
		err := getJSON(ctx, client, src.URL+"/items/"+url.PathEscape(ids[i]), userAgent, &story)
		return story, err
	})

	var items []Item
	for i, id := range ids {
		if errs[i] != nil {
			return partialOr(items, errs[i])
		}
		if len(items) >= src.MaxItems {
			break
		}
		key := "hnthread:" + id
		story := stories[i]
		threadURL := hnItemURL + id
		title := truncate(commentTitlePrefix+collapse(story.Title), titleRunes)

		type ranked struct {
			item    Item
			replies int
			id      int64
		}
		var candidates []ranked
		for _, c := range story.Children {
			text := htmlToText(c.Text)
			if c.Type != "comment" || c.Author == "" || !longEnough(text) {
				continue
			}
			replies := countDescendants(c.Children)
			candidates = append(candidates, ranked{
				id: c.ID, replies: replies,
				item: Item{
					URL: hnItemURL + strconv.FormatInt(c.ID, 10), Title: title, Summary: text,
					PublishedAt: unixTime(c.CreatedAtI),
					Discussion: &discussionMeta{
						Platform: events.PlatformHN, ThreadURL: threadURL, ParentURL: threadURL,
						Author: c.Author, Comments: intPtr(replies),
					},
				},
			})
		}
		sort.Slice(candidates, func(i, j int) bool {
			if candidates[i].replies != candidates[j].replies {
				return candidates[i].replies > candidates[j].replies
			}
			return candidates[i].id < candidates[j].id
		})
		thread := make([]Item, 0, src.PerThread)
		for _, c := range candidates[:min(len(candidates), src.PerThread)] {
			thread = append(thread, c.item)
		}
		items = append(items, finishThread(st, key, thread, now)...)
	}
	return items, nil
}

func countDescendants(children []algoliaItem) int {
	n := 0
	for _, c := range children {
		n += 1 + countDescendants(c.Children)
	}
	return n
}

// --- GitHub issues ------------------------------------------------------------------

type githubIssue struct {
	HTMLURL   string    `json:"html_url"`
	Title     string    `json:"title"`
	Body      string    `json:"body"`
	Comments  int       `json:"comments"`
	CreatedAt time.Time `json:"created_at"`
	User      struct {
		Login string `json:"login"`
		Type  string `json:"type"`
	} `json:"user"`
	PullRequest json.RawMessage `json:"pull_request"`
	Reactions   struct {
		TotalCount int `json:"total_count"`
		PlusOne    int `json:"+1"`
	} `json:"reactions"`
}

var htmlComment = regexp.MustCompile(`(?s)<!--.*?-->`)

// githubQueries packs repos into as few search queries as fit GitHub's 256-char limit,
// because the search API allows only 10 (30 with a token) requests per minute.
func githubQueries(repos []string, updatedSince time.Time) []string {
	prefix := "is:issue is:open updated:>" + updatedSince.UTC().Format("2006-01-02")
	var queries []string
	current := prefix
	for _, r := range repos {
		term := " repo:" + r
		if len(current)+len(term) > githubQueryLimit && current != prefix {
			queries = append(queries, current)
			current = prefix
		}
		current += term
	}
	if current != prefix {
		queries = append(queries, current)
	}
	return queries
}

// fetchGitHubIssues lists open, recently active issues ordered by reactions. Pull
// requests and bot-authored issues are excluded.
func fetchGitHubIssues(ctx context.Context, client *http.Client, src sources.Source, userAgent, token string, now time.Time) ([]Item, error) {
	from, _ := maturityWindow(src, now)
	headers := map[string]string{"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
	if token != "" {
		headers["Authorization"] = "Bearer " + token
	}
	var items []Item
	for _, query := range githubQueries(src.Repos, from) {
		q := url.Values{}
		q.Set("q", query)
		q.Set("sort", "reactions")
		q.Set("order", "desc")
		q.Set("per_page", strconv.Itoa(min(src.MaxItems, 100)))
		var res struct {
			Items []githubIssue `json:"items"`
		}
		if err := getJSONWithHeaders(ctx, client, src.URL+"/search/issues?"+q.Encode(), userAgent, headers, &res); err != nil {
			return partialOr(items, err)
		}
		for _, is := range res.Items {
			if len(is.PullRequest) > 0 || is.User.Type == "Bot" || strings.HasSuffix(is.User.Login, "[bot]") {
				continue
			}
			title := collapse(is.Title)
			text := openingText(title, collapse(htmlComment.ReplaceAllString(is.Body, " ")))
			if title == "" || is.HTMLURL == "" || !longEnough(text) {
				continue
			}
			created := is.CreatedAt.UTC()
			items = append(items, Item{
				URL: is.HTMLURL, Title: title, Summary: text, PublishedAt: &created,
				Discussion: &discussionMeta{
					Platform: events.PlatformGitHub, ThreadURL: is.HTMLURL, Author: is.User.Login,
					Points: intPtr(is.Reactions.PlusOne), Comments: intPtr(is.Comments),
					Reactions: intPtr(is.Reactions.TotalCount),
				},
			})
		}
	}
	return items, nil
}

// --- Lobsters -----------------------------------------------------------------------

// lobstersUser accepts both API spellings: a bare username or an object with one.
type lobstersUser string

func (u *lobstersUser) UnmarshalJSON(b []byte) error {
	var name string
	if err := json.Unmarshal(b, &name); err == nil {
		*u = lobstersUser(name)
		return nil
	}
	var obj struct {
		Username string `json:"username"`
	}
	if err := json.Unmarshal(b, &obj); err != nil {
		return err
	}
	*u = lobstersUser(obj.Username)
	return nil
}

type lobstersComment struct {
	ShortIDURL   string       `json:"short_id_url"`
	CreatedAt    time.Time    `json:"created_at"`
	Score        int          `json:"score"`
	CommentPlain string       `json:"comment_plain"`
	Depth        int          `json:"depth"`
	IsDeleted    bool         `json:"is_deleted"`
	IsModerated  bool         `json:"is_moderated"`
	User         lobstersUser `json:"commenting_user"`
}

type lobstersStory struct {
	ShortID          string            `json:"short_id"`
	ShortIDURL       string            `json:"short_id_url"`
	CreatedAt        time.Time         `json:"created_at"`
	Title            string            `json:"title"`
	Score            int               `json:"score"`
	CommentCount     int               `json:"comment_count"`
	DescriptionPlain string            `json:"description_plain"`
	Submitter        lobstersUser      `json:"submitter_user"`
	Comments         []lobstersComment `json:"comments"`
}

// fetchLobsters reads stories for the listed tags (hottest when none), then each matured
// thread's self text and its top-scored top-level comments.
func fetchLobsters(ctx context.Context, client *http.Client, src sources.Source, st *SourceState, userAgent string, now time.Time) ([]Item, error) {
	lists := []string{src.URL + "/hottest.json"}
	if len(src.Tags) > 0 {
		lists = lists[:0]
		for _, tag := range src.Tags {
			lists = append(lists, src.URL+"/t/"+url.PathEscape(tag)+".json")
		}
	}
	from, to := maturityWindow(src, now)
	byID := map[string]lobstersStory{}
	for _, list := range lists {
		var stories []lobstersStory
		if err := getJSON(ctx, client, list, userAgent, &stories); err != nil {
			if len(byID) == 0 {
				return nil, err
			}
			break // expand what we have; the next run retries the list
		}
		for _, s := range stories {
			if s.ShortID != "" && s.Score >= src.MinPoints && s.CreatedAt.After(from) && s.CreatedAt.Before(to) {
				byID[s.ShortID] = s
			}
		}
	}
	candidates := make([]lobstersStory, 0, len(byID))
	for _, s := range byID {
		candidates = append(candidates, s)
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].Score != candidates[j].Score {
			return candidates[i].Score > candidates[j].Score
		}
		return candidates[i].ShortID < candidates[j].ShortID
	})

	var selected []lobstersStory
	for _, s := range candidates {
		if st.Seen["lobthread:"+s.ShortID] == 0 && len(selected) < src.MaxThreads {
			selected = append(selected, s)
		}
	}
	threadsJSON, errs := fetchInOrder(len(selected), func(i int) (lobstersStory, error) {
		var full lobstersStory
		if selected[i].CommentCount == 0 {
			return full, nil
		}
		err := getJSON(ctx, client, src.URL+"/s/"+url.PathEscape(selected[i].ShortID)+".json", userAgent, &full)
		return full, err
	})

	var items []Item
	for i, s := range selected {
		if errs[i] != nil {
			return partialOr(items, errs[i])
		}
		if len(items) >= src.MaxItems {
			break
		}
		key := "lobthread:" + s.ShortID
		threadURL := src.URL + "/s/" + url.PathEscape(s.ShortID)
		title := collapse(s.Title)
		var thread []Item
		if text := openingText(title, collapse(s.DescriptionPlain)); s.DescriptionPlain != "" && longEnough(text) {
			created := s.CreatedAt.UTC()
			thread = append(thread, Item{
				URL: threadURL, Title: title, Summary: text, PublishedAt: &created,
				Discussion: &discussionMeta{
					Platform: events.PlatformLobsters, ThreadURL: threadURL, Author: string(s.Submitter),
					Points: intPtr(s.Score), Comments: intPtr(s.CommentCount),
				},
			})
		}
		if s.CommentCount > 0 {
			var top []lobstersComment
			for _, c := range threadsJSON[i].Comments {
				if c.Depth == 0 && !c.IsDeleted && !c.IsModerated && c.User != "" && c.ShortIDURL != "" && longEnough(collapse(c.CommentPlain)) {
					top = append(top, c)
				}
			}
			sort.SliceStable(top, func(i, j int) bool { return top[i].Score > top[j].Score })
			for _, c := range top[:min(len(top), src.PerThread)] {
				created := c.CreatedAt.UTC()
				thread = append(thread, Item{
					URL: c.ShortIDURL, Title: truncate(commentTitlePrefix+title, titleRunes),
					Summary: collapse(c.CommentPlain), PublishedAt: &created,
					Discussion: &discussionMeta{
						Platform: events.PlatformLobsters, ThreadURL: threadURL, ParentURL: threadURL,
						Author: string(c.User), Points: intPtr(c.Score),
					},
				})
			}
		}
		items = append(items, finishThread(st, key, thread, now)...)
	}
	return items, nil
}

// --- Stack Exchange -----------------------------------------------------------------

type stackExchangeResponse struct {
	Items          []stackExchangeQuestion `json:"items"`
	QuotaRemaining int                     `json:"quota_remaining"`
}

type stackExchangeQuestion struct {
	QuestionID   int64  `json:"question_id"`
	Link         string `json:"link"`
	Title        string `json:"title"`
	Body         string `json:"body"`
	Score        int    `json:"score"`
	AnswerCount  int    `json:"answer_count"`
	CreationDate int64  `json:"creation_date"`
	Owner        struct {
		UserID int64 `json:"user_id"`
	} `json:"owner"`
}

// errLowQuota is reported (as a partial result) so operators see the daily budget running out.
var errLowQuota = errors.New("stack exchange quota nearly exhausted")

// fetchStackExchange reads matured questions per tag, one request per tag.
func fetchStackExchange(ctx context.Context, client *http.Client, src sources.Source, userAgent string, now time.Time) ([]Item, error) {
	from, to := maturityWindow(src, now)
	var items []Item
	for _, tag := range src.Tags {
		q := url.Values{}
		q.Set("order", "desc")
		q.Set("sort", "creation")
		q.Set("tagged", tag)
		q.Set("site", src.Site)
		q.Set("pagesize", strconv.Itoa(min(src.MaxItems, 100)))
		q.Set("filter", "withbody")
		q.Set("fromdate", strconv.FormatInt(from.Unix(), 10))
		q.Set("todate", strconv.FormatInt(to.Unix(), 10))
		var res stackExchangeResponse
		if err := getJSON(ctx, client, src.URL+"/questions?"+q.Encode(), userAgent, &res); err != nil {
			return partialOr(items, err)
		}
		for _, qu := range res.Items {
			title := collapse(html.UnescapeString(qu.Title))
			text := openingText(title, htmlToText(qu.Body))
			if title == "" || qu.Link == "" || !longEnough(text) {
				continue
			}
			author := ""
			if qu.Owner.UserID > 0 {
				author = src.Site + ":" + strconv.FormatInt(qu.Owner.UserID, 10)
			}
			items = append(items, Item{
				URL: qu.Link, Title: title, Summary: text, PublishedAt: unixTime(qu.CreationDate),
				Discussion: &discussionMeta{
					Platform: events.PlatformStackExchange, ThreadURL: qu.Link, Author: author,
					Points: intPtr(qu.Score), Comments: intPtr(qu.AnswerCount),
				},
			})
		}
		if res.QuotaRemaining > 0 && res.QuotaRemaining < lowQuotaThreshold {
			return partialOr(items, fmt.Errorf("%w: %d left", errLowQuota, res.QuotaRemaining))
		}
	}
	return items, nil
}

// getJSONWithHeaders is getJSON with extra request headers (API versioning, auth).
func getJSONWithHeaders(ctx context.Context, client *http.Client, rawURL, userAgent string, headers map[string]string, v any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", userAgent)
	for k, val := range headers {
		req.Header.Set(k, val)
	}
	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return &statusError{URL: redactQuery(rawURL), Code: res.StatusCode}
	}
	return json.NewDecoder(io.LimitReader(res.Body, 5<<20)).Decode(v)
}

// redactQuery keeps error messages short and free of query strings.
func redactQuery(rawURL string) string {
	if i := strings.IndexByte(rawURL, '?'); i >= 0 {
		return rawURL[:i]
	}
	return rawURL
}
