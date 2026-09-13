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

func TestProblemRegistryIsValid(t *testing.T) {
	srcs, err := Load(filepath.Join("..", "..", "..", "..", "config", "problem_sources.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	kinds := map[Kind]bool{}
	for _, s := range srcs {
		if !s.Kind.IsDiscussion() {
			t.Errorf("%s: problem registry must only hold discussion kinds, got %q", s.ID, s.Kind)
		}
		if s.PerThread <= 0 || s.MaxThreads <= 0 || s.MaxAgeHours <= s.MinAgeHours {
			t.Errorf("%s: discussion defaults not applied: %+v", s.ID, s)
		}
		kinds[s.Kind] = true
	}
	for _, k := range []Kind{KindHNAlgolia, KindHNComments, KindGitHubIssues, KindLobsters, KindStackExchange} {
		if !kinds[k] {
			t.Errorf("no source of kind %q", k)
		}
	}
}

func TestDiscussionKindsAreValidated(t *testing.T) {
	_, err := Parse([]byte(`
sources:
  - {id: gh, kind: github_issues, name: x, url: "https://api.github.com", authority: 0.5, repos: ["not a repo"]}
  - {id: gh-empty, kind: github_issues, name: x, url: "https://api.github.com", authority: 0.5}
  - {id: se, kind: stackexchange, name: x, url: "https://api.stackexchange.com/2.3", authority: 0.5, tags: [k8s]}
  - {id: ask, kind: hn_algolia, name: x, url: "https://hn.algolia.com/api/v1", authority: 0.5}
  - {id: win, kind: lobsters, name: x, url: "https://lobste.rs", authority: 0.5, min_age_hours: 10, max_age_hours: 5, tags: ["Bad Tag"]}
`))
	if err == nil {
		t.Fatal("expected validation error")
	}
	for _, want := range []string{"invalid repo", "github_issues needs repos", "needs site and tags", "hn_algolia needs tags", "min_age_hours", "invalid tag"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error missing %q: %v", want, err)
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
