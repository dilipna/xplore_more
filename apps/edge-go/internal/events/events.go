// Package events mirrors contracts/events/*.schema.json for the Go edge.
package events

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"time"
)

const (
	TypeArticleDiscovered = "xm.article.discovered.v1"
	TypeArticleExtracted  = "xm.article.extracted.v1"
)

// Envelope is the CloudEvents-style wrapper carried as the Pub/Sub message body.
type Envelope[T any] struct {
	ID             string  `json:"id"`
	Type           string  `json:"type"`
	Source         string  `json:"source"`
	Subject        string  `json:"subject"`
	Time           string  `json:"time"`
	SchemaVersion  int     `json:"schema_version"`
	IdempotencyKey string  `json:"idempotency_key"`
	CausedBy       *string `json:"caused_by"`
	Data           T       `json:"data"`
}

// Signals are engagement values observed at emission time.
type Signals struct {
	HNItemID   *int64  `json:"hn_item_id"`
	HNPoints   *int    `json:"hn_points"`
	HNComments *int    `json:"hn_comments"`
	ObservedAt *string `json:"observed_at"`
}

type ArticleDiscovered struct {
	ArticleID    string  `json:"article_id"`
	URL          string  `json:"url"`
	CanonicalURL string  `json:"canonical_url"`
	SourceID     string  `json:"source_id"`
	DiscoveredAt string  `json:"discovered_at"`
	PublishedAt  *string `json:"published_at"`
	FeedTitle    *string `json:"feed_title"`
	FeedSummary  *string `json:"feed_summary"`
	Signals      Signals `json:"signals"`
}

type ArticleExtracted struct {
	ArticleID    string  `json:"article_id"`
	CanonicalURL string  `json:"canonical_url"`
	FinalURL     string  `json:"final_url"`
	SourceID     string  `json:"source_id"`
	Title        string  `json:"title"`
	Lede         string  `json:"lede"`
	TextURI      string  `json:"text_uri"`
	ContentHash  string  `json:"content_hash"`
	Lang         string  `json:"lang"`
	WordCount    int     `json:"word_count"`
	PublishedAt  *string `json:"published_at"`
	DiscoveredAt string  `json:"discovered_at"`
	ExtractedAt  string  `json:"extracted_at"`
	Signals      Signals `json:"signals"`
}

// Sha256Hex returns the lowercase hex sha256 of s.
func Sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

// IdempotencyKey implements the contract: sha256("{type}|{subject}|{discriminator}").
func IdempotencyKey(eventType, subject, discriminator string) string {
	return Sha256Hex(eventType + "|" + subject + "|" + discriminator)
}

// Timestamp formats t the way the contracts expect (RFC 3339, UTC).
func Timestamp(t time.Time) string {
	return t.UTC().Format(time.RFC3339Nano)
}

// NewUUIDv7 returns a time-ordered RFC 9562 UUID string.
func NewUUIDv7(now time.Time) string {
	var b [16]byte
	ms := uint64(now.UnixMilli())
	binary.BigEndian.PutUint64(b[0:8], ms<<16)
	if _, err := rand.Read(b[6:]); err != nil {
		panic(err) // crypto/rand failure is unrecoverable
	}
	b[6] = (b[6] & 0x0f) | 0x70 // version 7
	b[8] = (b[8] & 0x3f) | 0x80 // RFC 9562 variant
	h := hex.EncodeToString(b[:])
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32]
}

// NewDiscovered builds a discovered event for a canonicalized article.
func NewDiscovered(source string, data ArticleDiscovered, now time.Time) Envelope[ArticleDiscovered] {
	return Envelope[ArticleDiscovered]{
		ID:             NewUUIDv7(now),
		Type:           TypeArticleDiscovered,
		Source:         source,
		Subject:        data.ArticleID,
		Time:           Timestamp(now),
		SchemaVersion:  1,
		IdempotencyKey: IdempotencyKey(TypeArticleDiscovered, data.ArticleID, ""),
		Data:           data,
	}
}

// NewExtracted builds an extracted event, linked to the discovery that caused it.
func NewExtracted(source string, data ArticleExtracted, causedBy string, now time.Time) Envelope[ArticleExtracted] {
	var cause *string
	if causedBy != "" {
		cause = &causedBy
	}
	return Envelope[ArticleExtracted]{
		ID:             NewUUIDv7(now),
		Type:           TypeArticleExtracted,
		Source:         source,
		Subject:        data.ArticleID,
		Time:           Timestamp(now),
		SchemaVersion:  1,
		IdempotencyKey: IdempotencyKey(TypeArticleExtracted, data.ArticleID, data.ContentHash),
		CausedBy:       cause,
		Data:           data,
	}
}
