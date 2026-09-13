// Package ingest implements the Pub/Sub push endpoint that turns a discovered URL into an
// extracted article event.
//
// Response codes are the retry policy:
//
//	204  processed, or permanently unprocessable (acked; reason logged and counted)
//	503  transient failure: Pub/Sub redelivers with exponential backoff, and the
//	     subscription's dead-letter policy captures messages that keep failing
//
// Authentication is enforced by Cloud Run IAM. Only the Pub/Sub push service account holds
// roles/run.invoker, so unauthenticated requests never reach this handler.
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
	"sync/atomic"
	"time"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/canon"
	"github.com/dilipna/xploremore/apps/edge-go/internal/events"
	"github.com/dilipna/xploremore/apps/edge-go/internal/extract"
	"github.com/dilipna/xploremore/apps/edge-go/internal/fetch"
	"github.com/dilipna/xploremore/apps/edge-go/internal/textstore"
)

const (
	maxPushBody = 1 << 20
	maxURLLen   = 2048
	sourceName  = "edge/ingestor"
)

// Fetcher is the subset of fetch.Fetcher the handler needs.
type Fetcher interface {
	Get(ctx context.Context, rawURL string) (*fetch.Result, error)
}

// Handler processes push deliveries.
type Handler struct {
	Fetcher        Fetcher
	Store          textstore.Store
	Publisher      bus.Publisher
	ExtractedTopic string
	Log            *slog.Logger
	Now            func() time.Time
	FetchTimeout   time.Duration

	Stats Stats
}

// Stats are cumulative outcome counters (exported via /metrics and logs).
type Stats struct {
	Extracted atomic.Int64
	Rejected  atomic.Int64
	Retried   atomic.Int64
}

type pushRequest struct {
	Message struct {
		Data       []byte            `json:"data"` // base64 in JSON; encoding/json decodes []byte
		Attributes map[string]string `json:"attributes"`
		MessageID  string            `json:"messageId"`
	} `json:"message"`
	Subscription    string `json:"subscription"`
	DeliveryAttempt int    `json:"deliveryAttempt"`
}

type outcome struct {
	status int
	reason string
}

var (
	okExtracted = outcome{http.StatusNoContent, "extracted"}
	retryLater  = func(reason string) outcome { return outcome{http.StatusServiceUnavailable, reason} }
	reject      = func(reason string) outcome { return outcome{http.StatusNoContent, reason} }
)

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var push pushRequest
	if err := json.NewDecoder(io.LimitReader(r.Body, maxPushBody)).Decode(&push); err != nil {
		h.finish(w, push, "", reject("malformed push envelope"))
		return
	}
	env, err := decodeDiscovered(push.Message.Data)
	if err != nil {
		h.finish(w, push, "", reject("contract violation: "+err.Error()))
		return
	}
	h.finish(w, push, env.Data.ArticleID, h.process(r.Context(), env))
}

func decodeDiscovered(data []byte) (events.Envelope[events.ArticleDiscovered], error) {
	var env events.Envelope[events.ArticleDiscovered]
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&env); err != nil {
		return env, err
	}
	if env.Type != events.TypeArticleDiscovered || env.SchemaVersion != 1 {
		return env, fmt.Errorf("unexpected type %q v%d", env.Type, env.SchemaVersion)
	}
	if env.Data.CanonicalURL == "" || env.Data.SourceID == "" || env.Data.DiscoveredAt == "" {
		return env, errors.New("missing required fields")
	}
	return env, nil
}

func (h *Handler) process(ctx context.Context, env events.Envelope[events.ArticleDiscovered]) outcome {
	d := env.Data
	fetchCtx, cancel := context.WithTimeout(ctx, h.FetchTimeout)
	defer cancel()

	feedTitle, feedSummary := deref(d.FeedTitle), deref(d.FeedSummary)
	origin := events.OriginPage
	var doc *extract.Document
	var finalURL string

	res, err := h.Fetcher.Get(fetchCtx, d.CanonicalURL)
	switch {
	case errors.Is(err, fetch.ErrPermanent):
		// Blocked, disallowed or gone: fall back to the syndication feed's own content.
		if doc, err = extract.FromFeed(feedTitle, feedSummary, d.CanonicalURL); err != nil {
			return reject("fetch: permanent failure and no usable feed content")
		}
		origin, finalURL = events.OriginFeed, d.CanonicalURL
	case err != nil:
		return retryLater("fetch: " + err.Error())
	default:
		finalURL = res.FinalURL.String()
		doc, err = extract.FromHTML(res.Body, res.FinalURL, feedTitle)
		if err != nil {
			if doc, err = extract.FromFeed(feedTitle, feedSummary, d.CanonicalURL); err != nil {
				return reject("extract: no content in page or feed")
			}
			origin = events.OriginFeed
		}
	}

	if len(finalURL) > maxURLLen || len(doc.CanonicalURL) > maxURLLen {
		return reject("url exceeds contract length")
	}
	now := h.Now().UTC()
	articleID := canon.ArticleID(doc.CanonicalURL)

	textURI, err := h.Store.Put(ctx, articleID, doc.ContentHash, doc.Text, now)
	if err != nil {
		return retryLater("store: " + err.Error())
	}

	published := d.PublishedAt
	if published == nil && doc.PublishedAt != nil {
		ts := events.Timestamp(*doc.PublishedAt)
		published = &ts
	}
	extracted := events.NewExtracted(sourceName, events.ArticleExtracted{
		ArticleID:     articleID,
		CanonicalURL:  doc.CanonicalURL,
		FinalURL:      finalURL,
		SourceID:      d.SourceID,
		Title:         doc.Title,
		Lede:          doc.Lede,
		TextURI:       textURI,
		ContentHash:   doc.ContentHash,
		Lang:          doc.Lang,
		WordCount:     doc.WordCount,
		ContentOrigin: origin,
		PublishedAt:   published,
		DiscoveredAt:  d.DiscoveredAt,
		ExtractedAt:   events.Timestamp(now),
		Signals:       d.Signals,
	}, env.ID, now)

	// Publish must succeed before we ack the input. If it fails we return 503, and the
	// redelivered discovery re-runs extraction. Downstream idempotency (keyed on content
	// hash) absorbs the duplicate this can create.
	if err := bus.PublishJSON(ctx, h.Publisher, h.ExtractedTopic, extracted.Type, extracted); err != nil {
		return retryLater("publish: " + err.Error())
	}
	return okExtracted
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func (h *Handler) finish(w http.ResponseWriter, push pushRequest, articleID string, o outcome) {
	level := slog.LevelInfo
	switch {
	case o == okExtracted:
		h.Stats.Extracted.Add(1)
	case o.status == http.StatusServiceUnavailable:
		h.Stats.Retried.Add(1)
		level = slog.LevelWarn
	default:
		h.Stats.Rejected.Add(1)
	}
	h.Log.Log(context.Background(), level, "ingest",
		"outcome", o.reason, "status", o.status, "article_id", articleID,
		"message_id", push.Message.MessageID, "delivery_attempt", push.DeliveryAttempt)
	w.WriteHeader(o.status)
}
