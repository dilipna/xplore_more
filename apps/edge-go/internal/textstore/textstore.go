// Package textstore persists extracted full text outside the database (claim-check pattern).
//
// Keys are content-addressed (article id + content hash), so a retried write of the same
// extraction is idempotent and a changed article gets a new object instead of silently
// overwriting the text an older index row still points to.
package textstore

import (
	"compress/gzip"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"cloud.google.com/go/storage"
	"google.golang.org/api/googleapi"
)

// Store writes text and returns its URI.
type Store interface {
	Put(ctx context.Context, articleID, contentHash, text string, at time.Time) (string, error)
}

func objectKey(articleID, contentHash string, at time.Time) string {
	return fmt.Sprintf("text/%s/%s-%s.txt.gz", at.UTC().Format("2006/01/02"), articleID, contentHash[:16])
}

// GCS stores gzipped text in a bucket (lifecycle rules handle retention).
type GCS struct {
	Client *storage.Client
	Bucket string
}

func (g GCS) Put(ctx context.Context, articleID, contentHash, text string, at time.Time) (string, error) {
	key := objectKey(articleID, contentHash, at)
	// DoesNotExist makes the write idempotent: a retry after a crash finds the object
	// already present and treats that as success instead of paying another write op.
	obj := g.Client.Bucket(g.Bucket).Object(key).If(storage.Conditions{DoesNotExist: true})
	w := obj.NewWriter(ctx)
	w.ContentType = "text/plain; charset=utf-8"
	w.ContentEncoding = "gzip"
	gz := gzip.NewWriter(w)
	if _, err := gz.Write([]byte(text)); err != nil {
		_ = w.Close()
		return "", fmt.Errorf("gzip write: %w", err)
	}
	if err := gz.Close(); err != nil {
		_ = w.Close()
		return "", fmt.Errorf("gzip close: %w", err)
	}
	if err := w.Close(); err != nil && !isPreconditionFailed(err) {
		return "", fmt.Errorf("gcs write %s: %w", key, err)
	}
	return "gs://" + g.Bucket + "/" + key, nil
}

func isPreconditionFailed(err error) bool {
	var gErr *googleapi.Error
	if errors.As(err, &gErr) {
		return gErr.Code == 412
	}
	var apiErr interface{ HTTPCode() int }
	if errors.As(err, &apiErr) {
		return apiErr.HTTPCode() == 412
	}
	return false
}

// File stores text on local disk for development.
type File struct {
	Dir string
}

func (f File) Put(_ context.Context, articleID, contentHash, text string, at time.Time) (string, error) {
	path := filepath.Join(f.Dir, filepath.FromSlash(objectKey(articleID, contentHash, at)))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", err
	}
	out, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
	if errors.Is(err, os.ErrExist) {
		return "file://" + filepath.ToSlash(path), nil
	}
	if err != nil {
		return "", err
	}
	defer out.Close()
	gz := gzip.NewWriter(out)
	if _, err := gz.Write([]byte(text)); err != nil {
		return "", err
	}
	if err := gz.Close(); err != nil {
		return "", err
	}
	abs, _ := filepath.Abs(path)
	return "file://" + filepath.ToSlash(abs), nil
}
