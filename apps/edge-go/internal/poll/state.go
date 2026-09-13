package poll

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"cloud.google.com/go/storage"
	"google.golang.org/api/googleapi"
)

// ErrStateConflict means another poller wrote the state since we loaded it.
var ErrStateConflict = errors.New("poll state modified concurrently")

// SourceState is what the poller remembers per source between runs.
type SourceState struct {
	ETag         string           `json:"etag,omitempty"`
	LastModified string           `json:"last_modified,omitempty"`
	Seen         map[string]int64 `json:"seen"` // key (article id or external id) -> unix seconds first seen
	LastSuccess  int64            `json:"last_success,omitempty"`
	LastError    string           `json:"last_error,omitempty"`
	Failures     int              `json:"consecutive_failures,omitempty"`
}

// State is the whole poller memory, stored as ONE object: one read and one write per run.
// That keeps object-storage operations inside the free tier (see docs/storage-economics.md).
type State struct {
	Sources map[string]*SourceState `json:"sources"`
}

func (s *State) source(id string) *SourceState {
	if s.Sources == nil {
		s.Sources = map[string]*SourceState{}
	}
	st, ok := s.Sources[id]
	if !ok {
		st = &SourceState{Seen: map[string]int64{}}
		s.Sources[id] = st
	}
	if st.Seen == nil {
		st.Seen = map[string]int64{}
	}
	return st
}

// Prune forgets seen keys older than maxAge and caps each source's memory.
func (s *State) Prune(now time.Time, maxAge time.Duration, maxPerSource int) {
	cutoff := now.Add(-maxAge).Unix()
	for _, st := range s.Sources {
		for k, ts := range st.Seen {
			if ts < cutoff {
				delete(st.Seen, k)
			}
		}
		for len(st.Seen) > maxPerSource {
			oldestKey, oldestTS := "", int64(1<<62)
			for k, ts := range st.Seen {
				if ts < oldestTS {
					oldestKey, oldestTS = k, ts
				}
			}
			delete(st.Seen, oldestKey)
		}
	}
}

// StateStore loads and saves State with optimistic concurrency.
type StateStore interface {
	Load(ctx context.Context) (*State, int64, error)         // state + version token
	Save(ctx context.Context, s *State, version int64) error // ErrStateConflict if version moved
}

// GCSStateStore keeps state in one object, guarded by generation preconditions.
type GCSStateStore struct {
	Client *storage.Client
	Bucket string
	Object string
}

func (g GCSStateStore) Load(ctx context.Context) (*State, int64, error) {
	obj := g.Client.Bucket(g.Bucket).Object(g.Object)
	r, err := obj.NewReader(ctx)
	if errors.Is(err, storage.ErrObjectNotExist) {
		return &State{}, 0, nil
	}
	if err != nil {
		return nil, 0, fmt.Errorf("read state: %w", err)
	}
	defer r.Close()
	var s State
	if err := json.NewDecoder(r).Decode(&s); err != nil {
		return nil, 0, fmt.Errorf("decode state: %w", err)
	}
	return &s, r.Attrs.Generation, nil
}

func (g GCSStateStore) Save(ctx context.Context, s *State, generation int64) error {
	obj := g.Client.Bucket(g.Bucket).Object(g.Object)
	if generation == 0 {
		obj = obj.If(storage.Conditions{DoesNotExist: true})
	} else {
		obj = obj.If(storage.Conditions{GenerationMatch: generation})
	}
	w := obj.NewWriter(ctx)
	w.ContentType = "application/json"
	if err := json.NewEncoder(w).Encode(s); err != nil {
		_ = w.Close()
		return err
	}
	if err := w.Close(); err != nil {
		var gErr *googleapi.Error
		if errors.As(err, &gErr) && gErr.Code == 412 {
			return ErrStateConflict
		}
		return fmt.Errorf("write state: %w", err)
	}
	return nil
}

// FileStateStore is for local development; version is the file's modification time.
type FileStateStore struct {
	Path string
}

func (f FileStateStore) Load(context.Context) (*State, int64, error) {
	file, err := os.Open(f.Path)
	if errors.Is(err, os.ErrNotExist) {
		return &State{}, 0, nil
	}
	if err != nil {
		return nil, 0, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, 0, err
	}
	raw, err := io.ReadAll(file)
	if err != nil {
		return nil, 0, err
	}
	var s State
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, 0, err
	}
	return &s, info.ModTime().UnixNano(), nil
}

func (f FileStateStore) Save(_ context.Context, s *State, version int64) error {
	if info, err := os.Stat(f.Path); err == nil && info.ModTime().UnixNano() != version {
		return ErrStateConflict
	}
	if err := os.MkdirAll(filepath.Dir(f.Path), 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(s, "", " ")
	if err != nil {
		return err
	}
	tmp := f.Path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, f.Path)
}
