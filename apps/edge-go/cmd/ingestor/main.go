// Command ingestor is the untrusted-zone Cloud Run service: Pub/Sub push in, extracted
// article events out. It holds no database credentials by design.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"cloud.google.com/go/storage"

	"github.com/dilipna/xploremore/apps/edge-go/internal/bus"
	"github.com/dilipna/xploremore/apps/edge-go/internal/config"
	"github.com/dilipna/xploremore/apps/edge-go/internal/fetch"
	"github.com/dilipna/xploremore/apps/edge-go/internal/ingest"
	"github.com/dilipna/xploremore/apps/edge-go/internal/ssrf"
	"github.com/dilipna/xploremore/apps/edge-go/internal/textstore"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	if err := run(log); err != nil {
		log.Error("ingestor exited", "error", err)
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	project, err := config.Required("XM_GCP_PROJECT")
	if err != nil {
		return err
	}
	publisher, err := bus.NewPubSub(ctx, project)
	if err != nil {
		return err
	}
	defer publisher.Close()

	var store textstore.Store
	if bucket := config.String("XM_TEXT_BUCKET", ""); bucket != "" {
		gcs, err := storage.NewClient(ctx)
		if err != nil {
			return fmt.Errorf("storage client: %w", err)
		}
		defer gcs.Close()
		store = textstore.GCS{Client: gcs, Bucket: bucket}
	} else {
		store = textstore.File{Dir: config.String("XM_TEXT_DIR", "./.data/text")}
	}

	handler := &ingest.Handler{
		Fetcher:        fetch.New(ssrf.DefaultPolicy(), fetch.DefaultOptions()),
		Store:          store,
		Publisher:      publisher,
		ExtractedTopic: config.String("XM_TOPIC_ARTICLE_EXTRACTED", "article-extracted"),
		Log:            log,
		Now:            time.Now,
		FetchTimeout:   config.Duration("XM_FETCH_TIMEOUT", 20*time.Second),
	}

	mux := http.NewServeMux()
	mux.Handle("POST /push/article-discovered", handler)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := &http.Server{
		Addr:              ":" + config.String("PORT", "8080"),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		// Must exceed fetch timeout + store + publish; Cloud Run's request timeout is the
		// outer bound and the push subscription's ack deadline is set above it.
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  90 * time.Second,
	}

	errCh := make(chan error, 1)
	go func() {
		log.Info("ingestor listening", "addr", srv.Addr)
		errCh <- srv.ListenAndServe()
	}()

	select {
	case err := <-errCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
		// Cloud Run sends SIGTERM and allows ~10s. Stop accepting new work and let
		// in-flight requests finish. Anything cut off is redelivered by Pub/Sub.
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 9*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			return fmt.Errorf("shutdown: %w", err)
		}
	}
	log.Info("ingestor stopped",
		"extracted", handler.Stats.Extracted.Load(),
		"rejected", handler.Stats.Rejected.Load(),
		"retried", handler.Stats.Retried.Load(),
		"throttled", handler.Stats.Throttled.Load())
	return nil
}
