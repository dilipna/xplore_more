// Package extract turns untrusted HTML into plain text plus the metadata the indexer needs.
//
// HTML is never rendered or stored for display. Only extracted text crosses into the
// trusted zone.
package extract

import (
	"bytes"
	"errors"
	"net/url"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/abadojack/whatlanggo"
	trafilatura "github.com/markusmobius/go-trafilatura"
	"golang.org/x/net/publicsuffix"

	"github.com/dilipna/xploremore/apps/edge-go/internal/canon"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
)

// ErrNoContent means the page had no extractable article text.
var ErrNoContent = errors.New("extract: no article content")

const (
	ledeRunes     = 1000
	titleRunes    = 500
	minTextRunes  = 200
	langMinLength = 60
)

// Document is the extraction output.
type Document struct {
	Title        string
	Text         string // whitespace-normalized
	Lede         string
	Lang         string
	WordCount    int
	ContentHash  string
	CanonicalURL string // validated canonical, or the fetched URL's canonical form
	PublishedAt  *time.Time
}

// FromHTML extracts the main content of body fetched from finalURL.
// fallbackTitle is used when the page has no usable <title> (feeds usually provide one).
func FromHTML(body []byte, finalURL *url.URL, fallbackTitle string) (*Document, error) {
	res, err := trafilatura.Extract(bytes.NewReader(body), trafilatura.Options{
		OriginalURL:     finalURL,
		EnableFallback:  true,
		ExcludeComments: true,
		Deduplicate:     true,
		MaxTreeSize:     50_000,
	})
	if err != nil || res == nil {
		return nil, ErrNoContent
	}
	text := normalizeSpace(res.ContentText)
	if utf8.RuneCountInString(text) < minTextRunes {
		return nil, ErrNoContent
	}

	title := normalizeSpace(res.Metadata.Title)
	if title == "" {
		title = normalizeSpace(fallbackTitle)
	}
	if title == "" {
		return nil, ErrNoContent
	}

	canonicalURL, err := chooseCanonical(finalURL, res.Metadata.URL)
	if err != nil {
		return nil, err
	}

	doc := &Document{
		Title:        truncateRunes(title, titleRunes),
		Text:         text,
		Lede:         truncateRunes(text, ledeRunes),
		Lang:         detectLang(res.Metadata.Language, text),
		WordCount:    len(strings.Fields(text)),
		ContentHash:  events.Sha256Hex(text),
		CanonicalURL: canonicalURL,
	}
	if !res.Metadata.Date.IsZero() && res.Metadata.Date.Before(time.Now().Add(24*time.Hour)) {
		published := res.Metadata.Date.UTC()
		doc.PublishedAt = &published
	}
	return doc, nil
}

// minFeedRunes is lower than minTextRunes: feed content is publisher-curated (release
// notes, abstracts), so a short text is still meaningful, but a bare title is not.
const minFeedRunes = 80

// FromFeed builds a document from the feed's own title and content. It is used when the
// page blocks automated fetches (401/403/robots) or has too little extractable text.
// Publishers offer feeds for syndication, so this respects their access choices.
func FromFeed(title, content, canonicalURL string) (*Document, error) {
	text := normalizeSpace(content)
	title = normalizeSpace(title)
	if title == "" || utf8.RuneCountInString(text) < minFeedRunes {
		return nil, ErrNoContent
	}
	return &Document{
		Title:        truncateRunes(title, titleRunes),
		Text:         text,
		Lede:         truncateRunes(text, ledeRunes),
		Lang:         detectLang("", text),
		WordCount:    len(strings.Fields(text)),
		ContentHash:  events.Sha256Hex(text),
		CanonicalURL: canonicalURL,
	}, nil
}

// chooseCanonical accepts a page-declared canonical URL only when it stays on the same
// registrable domain as the page actually fetched. Otherwise a malicious page could
// declare `<link rel=canonical href="https://anthropic.com/news/x">` and overwrite a
// legitimate article's identity and content downstream (canonical hijacking).
func chooseCanonical(finalURL *url.URL, declared string) (string, error) {
	fetched, err := canon.URL(finalURL.String())
	if err != nil {
		return "", err
	}
	if declared == "" {
		return fetched, nil
	}
	ref, err := url.Parse(declared)
	if err != nil {
		return fetched, nil
	}
	resolved := finalURL.ResolveReference(ref)
	candidate, err := canon.URL(resolved.String())
	if err != nil {
		return fetched, nil
	}
	if sameSite(finalURL.Hostname(), resolved.Hostname()) {
		return candidate, nil
	}
	return fetched, nil
}

func sameSite(a, b string) bool {
	ea, errA := publicsuffix.EffectiveTLDPlusOne(strings.ToLower(a))
	eb, errB := publicsuffix.EffectiveTLDPlusOne(strings.ToLower(b))
	return errA == nil && errB == nil && ea == eb
}

func detectLang(declared, text string) string {
	if utf8.RuneCountInString(text) >= langMinLength {
		sample := truncateRunes(text, 2000)
		if code := whatlanggo.DetectLang(sample).Iso6391(); len(code) == 2 {
			return code
		}
	}
	declared = strings.ToLower(strings.TrimSpace(declared))
	if i := strings.IndexAny(declared, "-_"); i > 0 {
		declared = declared[:i]
	}
	if len(declared) == 2 || len(declared) == 3 {
		return declared
	}
	return "und"
}

func normalizeSpace(s string) string {
	return strings.Join(strings.Fields(s), " ")
}

func truncateRunes(s string, n int) string {
	if utf8.RuneCountInString(s) <= n {
		return s
	}
	runes := []rune(s)
	return string(runes[:n])
}
