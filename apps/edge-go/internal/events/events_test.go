package events

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"testing"
	"time"
)

var fixtures = filepath.Join("..", "..", "..", "..", "contracts", "fixtures")

// decodeStrict fails on fields the Go types do not declare, so the Go side cannot silently
// drop data the contract (and the Python side) knows about.
func decodeStrict[T any](t *testing.T, name string) (Envelope[T], []byte) {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join(fixtures, name))
	if err != nil {
		t.Fatal(err)
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	var env Envelope[T]
	if err := dec.Decode(&env); err != nil {
		t.Fatalf("%s: %v", name, err)
	}
	return env, raw
}

func assertRoundTrip[T any](t *testing.T, env Envelope[T], raw []byte) {
	t.Helper()
	encoded, err := json.Marshal(env)
	if err != nil {
		t.Fatal(err)
	}
	var want, got any
	_ = json.Unmarshal(raw, &want)
	_ = json.Unmarshal(encoded, &got)
	wantJSON, _ := json.Marshal(want)
	gotJSON, _ := json.Marshal(got)
	if !bytes.Equal(wantJSON, gotJSON) {
		t.Fatalf("round trip mismatch\nwant %s\ngot  %s", wantJSON, gotJSON)
	}
}

func TestDiscoveredFixtureContract(t *testing.T) {
	env, raw := decodeStrict[ArticleDiscovered](t, "article.discovered.v1.json")
	assertRoundTrip(t, env, raw)
	if got := IdempotencyKey(env.Type, env.Subject, ""); got != env.IdempotencyKey {
		t.Fatalf("idempotency key %s, fixture %s", got, env.IdempotencyKey)
	}
	if Sha256Hex(env.Data.CanonicalURL) != env.Data.ArticleID {
		t.Fatal("article_id must be sha256(canonical_url)")
	}
}

func TestExtractedFixtureContract(t *testing.T) {
	env, raw := decodeStrict[ArticleExtracted](t, "article.extracted.v1.json")
	assertRoundTrip(t, env, raw)
	if got := IdempotencyKey(env.Type, env.Subject, env.Data.ContentHash); got != env.IdempotencyKey {
		t.Fatalf("idempotency key %s, fixture %s", got, env.IdempotencyKey)
	}
}

func TestUUIDv7Format(t *testing.T) {
	re := regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	prev := ""
	base := time.Date(2026, 9, 13, 10, 0, 0, 0, time.UTC)
	for i := range 100 {
		id := NewUUIDv7(base.Add(time.Duration(i) * time.Millisecond))
		if !re.MatchString(id) {
			t.Fatalf("bad uuidv7 %q", id)
		}
		if id[:13] < prev {
			t.Fatalf("not time ordered: %s after %s", id, prev)
		}
		prev = id[:13]
	}
}
