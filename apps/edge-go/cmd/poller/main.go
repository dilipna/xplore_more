// Command poller is a Cloud Run Job: discover new articles once, publish events, exit.
//
//	poller            poll all sources and publish (needs XM_GCP_PROJECT)
//	poller --check    fetch every source and report reachability; publishes nothing
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"cloud.google.com/go/storage"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/config"
	"github.com/dilipna/xploremore/apps/edge-go/internal/fetch"
	"github.com/dilipna/xploremore/apps/edge-go/internal/poll"
	"github.com/dilipna/xploremore/apps/edge-go/internal/sources"
	"github.com/dilipna/xploremore/apps/edge-go/internal/ssrf"
)

func main() {
	check := flag.Bool("check", false, "verify every source is reachable and parseable; publish nothing")
	registry := flag.String("sources", config.String("XM_SOURCES_FILE", "../../config/sources.yaml"), "source registry path")
	flag.Parse()

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, log, *registry, *check); err != nil {
		log.Error("poller failed", "error", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, log *slog.Logger, registry string, check bool) error {
	srcs, err := sources.Load(registry)
	if err != nil {
		return err
	}
	opts := fetch.DefaultOptions()
	client := ssrf.NewClient(ssrf.DefaultPolicy(), ssrf.ClientOptions{
		Timeout: 30 * time.Second, MaxRedirects: 3, UserAgent: opts.UserAgent,
	})

	p := &poll.Poller{
		Client:          client,
		UserAgent:       opts.UserAgent,
		Log:             log,
		Now:             time.Now,
		PerSourceTimout: config.Duration("XM_SOURCE_TIMEOUT", 45*time.Second),
		DiscoveredTopic: config.String("XM_TOPIC_ARTICLE_DISCOVERED", "article-discovered"),
		GitHubToken:     config.String("GITHUB_TOKEN", ""),
		AuthorSalt:      config.String("XM_AUTHOR_SALT", ""),
	}
	hasDiscussions := false
	for _, s := range srcs {
		hasDiscussions = hasDiscussions || (s.Kind.IsDiscussion() && !s.Disabled)
	}

	if check {
		// Dry run: in-memory state and a recording publisher.
		p.State = poll.FileStateStore{Path: fmt.Sprintf("%s/xm-check-%d.json", os.TempDir(), time.Now().UnixNano())}
		p.Publisher = &bus.Memory{}
		if p.AuthorSalt == "" {
			p.AuthorSalt = "check-only"
		}
	} else {
		// Without a stable salt, distinct voices cannot be counted and rotating it later
		// would split every author in two. Refuse to run rather than degrade silently.
		if hasDiscussions && len(p.AuthorSalt) < 16 {
			return errors.New("XM_AUTHOR_SALT (>= 16 chars, from Secret Manager) is required for discussion sources")
		}
		project, err := config.Required("XM_GCP_PROJECT")
		if err != nil {
			return err
		}
		publisher, err := bus.NewPubSub(ctx, project)
		if err != nil {
			return err
		}
		defer publisher.Close()
		p.Publisher = publisher

		if bucket := config.String("XM_STATE_BUCKET", ""); bucket != "" {
			gcs, err := storage.NewClient(ctx)
			if err != nil {
				return err
			}
			defer gcs.Close()
			// Each registry runs as its own job with its own state object, so the article and
			// problem pollers never conflict on one generation precondition.
			object := config.String("XM_STATE_OBJECT", "poller/state.json")
			p.State = poll.GCSStateStore{Client: gcs, Bucket: bucket, Object: object}
		} else {
			p.State = poll.FileStateStore{Path: config.String("XM_STATE_FILE", "./.data/poller-state.json")}
		}
	}

	started := time.Now()
	reports, err := p.RunOnce(ctx, srcs)
	if errors.Is(err, poll.ErrStateConflict) {
		// Another run overlapped. Our events are already published and downstream
		// idempotency absorbs duplicates, so fail loudly for alerting but lose nothing.
		log.Error("state conflict: overlapping poller runs", "error", err)
	}

	summary := map[string]int{"sources": len(reports)}
	for _, r := range reports {
		summary["found"] += r.Found
		summary["published"] += r.Published
		summary["skipped_seen"] += r.Skipped
		summary["invalid_url"] += r.Invalid
		if r.Warning != "" {
			summary["partial_sources"]++
		}
		if r.Error != "" {
			summary["failed_sources"]++
		}
		if r.NotMod {
			summary["not_modified"]++
		}
	}
	if check {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(reports)
	}
	log.Info("poller_run", "duration_s", time.Since(started).Seconds(), "summary", summary)
	return err
}
