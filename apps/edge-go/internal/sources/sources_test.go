package sources

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRepositoryRegistryIsValid(t *testing.T) {
	srcs, err := Load(filepath.Join("..", "..", "..", "..", "config", "sources.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if len(srcs) < 30 {
		t.Fatalf("expected a substantial registry, got %d sources", len(srcs))
	}
	for _, s := range srcs {
		if s.MaxItems <= 0 {
			t.Errorf("%s: max_items default not applied", s.ID)
		}
	}
}

func TestParseReportsAllProblems(t *testing.T) {
	_, err := Parse([]byte(`
sources:
  - {id: "Bad ID", kind: rss, name: x, url: "https://a.example/feed", authority: 0.5}
  - {id: dup, kind: rss, name: x, url: "http://insecure.example/feed", authority: 0.5}
  - {id: dup, kind: carrier-pigeon, name: x, url: "https://b.example", authority: 1.5}
`))
	if err == nil {
		t.Fatal("expected validation error")
	}
	for _, want := range []string{"invalid id", "absolute https", "duplicate id", "unknown kind", "authority"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error missing %q: %v", want, err)
		}
	}
}
