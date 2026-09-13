// Package sources loads and validates the source registries (config/sources.yaml for
// articles, config/problem_sources.yaml for discussions).
package sources

import (
	"fmt"
	"net/url"
	"os"
	"regexp"

	"go.yaml.in/yaml/v3"
)

// Kind selects the polling strategy.
type Kind string

const (
	KindRSS Kind = "rss"
	KindHN  Kind = "hn"

	// Discussion kinds read public platform APIs. Their text comes from the API response,
	// so the ingestor never fetches their HTML.
	KindHNAlgolia     Kind = "hn_algolia"    // Ask HN / Show HN posts via Algolia (tags)
	KindHNComments    Kind = "hn_comments"   // top-level comments of high-engagement stories
	KindGitHubIssues  Kind = "github_issues" // open issues of listed repos, by reactions
	KindLobsters      Kind = "lobsters"      // Lobsters stories (tags) and top-level comments
	KindStackExchange Kind = "stackexchange" // questions for tags on one site
)

// IsDiscussion reports whether the kind produces doc_kind=discussion documents.
func (k Kind) IsDiscussion() bool {
	switch k {
	case KindHNAlgolia, KindHNComments, KindGitHubIssues, KindLobsters, KindStackExchange:
		return true
	}
	return false
}

// Source is one registry entry.
type Source struct {
	ID        string  `yaml:"id"`
	Kind      Kind    `yaml:"kind"`
	Name      string  `yaml:"name"`
	URL       string  `yaml:"url"`
	Authority float64 `yaml:"authority"`
	MaxItems  int     `yaml:"max_items"`
	Disabled  bool    `yaml:"disabled"`

	// Discussion options (ignored by article kinds).
	Tags        []string `yaml:"tags"`          // hn_algolia, lobsters, stackexchange
	Repos       []string `yaml:"repos"`         // github_issues: owner/name
	Site        string   `yaml:"site"`          // stackexchange: e.g. stackoverflow
	MinPoints   int      `yaml:"min_points"`    // hn_comments, lobsters: thread engagement floor
	MaxThreads  int      `yaml:"max_threads"`   // hn_comments, lobsters: threads expanded per run
	PerThread   int      `yaml:"per_thread"`    // top-level comments kept per thread
	MinAgeHours int      `yaml:"min_age_hours"` // engagement is observed once, after maturing
	MaxAgeHours int      `yaml:"max_age_hours"`
}

var (
	idPattern   = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{1,63}$`)
	repoPattern = regexp.MustCompile(`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`)
	tagPattern  = regexp.MustCompile(`^[a-z0-9][a-z0-9_.+#-]{0,63}$`)
)

const (
	defaultMaxItems    = 50
	defaultMaxThreads  = 10
	defaultPerThread   = 8
	defaultMinAgeHours = 12
	defaultMaxAgeHours = 60
)

// Load reads and validates a registry file.
func Load(path string) ([]Source, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return Parse(raw)
}

// Parse validates registry YAML. Every problem is reported, not just the first.
func Parse(raw []byte) ([]Source, error) {
	var doc struct {
		Sources []Source `yaml:"sources"`
	}
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return nil, fmt.Errorf("parse registry: %w", err)
	}
	seen := map[string]bool{}
	var problems []string
	for i := range doc.Sources {
		s := &doc.Sources[i]
		if !idPattern.MatchString(s.ID) {
			problems = append(problems, fmt.Sprintf("source %d: invalid id %q", i, s.ID))
		}
		if seen[s.ID] {
			problems = append(problems, fmt.Sprintf("duplicate id %q", s.ID))
		}
		seen[s.ID] = true
		if s.Kind != KindRSS && s.Kind != KindHN && !s.Kind.IsDiscussion() {
			problems = append(problems, fmt.Sprintf("%s: unknown kind %q", s.ID, s.Kind))
		}
		if u, err := url.Parse(s.URL); err != nil || u.Scheme != "https" || u.Host == "" {
			problems = append(problems, fmt.Sprintf("%s: url must be absolute https", s.ID))
		}
		if s.Authority < 0 || s.Authority > 1 {
			problems = append(problems, fmt.Sprintf("%s: authority must be in [0,1]", s.ID))
		}
		if s.MaxItems == 0 {
			s.MaxItems = defaultMaxItems
		}
		if s.MaxItems < 0 {
			problems = append(problems, fmt.Sprintf("%s: max_items must be positive", s.ID))
		}
		if s.Kind.IsDiscussion() {
			problems = append(problems, validateDiscussion(s)...)
		}
	}
	if len(problems) > 0 {
		return nil, fmt.Errorf("invalid registry: %v", problems)
	}
	return doc.Sources, nil
}

func validateDiscussion(s *Source) []string {
	var problems []string
	if s.MaxThreads == 0 {
		s.MaxThreads = defaultMaxThreads
	}
	if s.PerThread == 0 {
		s.PerThread = defaultPerThread
	}
	if s.MinAgeHours == 0 {
		s.MinAgeHours = defaultMinAgeHours
	}
	if s.MaxAgeHours == 0 {
		s.MaxAgeHours = defaultMaxAgeHours
	}
	if s.MaxThreads < 0 || s.PerThread < 0 || s.MinPoints < 0 {
		problems = append(problems, fmt.Sprintf("%s: max_threads, per_thread and min_points must not be negative", s.ID))
	}
	if s.MinAgeHours < 0 || s.MaxAgeHours <= s.MinAgeHours {
		problems = append(problems, fmt.Sprintf("%s: need 0 <= min_age_hours < max_age_hours", s.ID))
	}
	for _, tag := range s.Tags {
		if !tagPattern.MatchString(tag) {
			problems = append(problems, fmt.Sprintf("%s: invalid tag %q", s.ID, tag))
		}
	}
	switch s.Kind {
	case KindHNAlgolia:
		if len(s.Tags) == 0 {
			problems = append(problems, fmt.Sprintf("%s: hn_algolia needs tags (e.g. ask_hn)", s.ID))
		}
	case KindGitHubIssues:
		if len(s.Repos) == 0 {
			problems = append(problems, fmt.Sprintf("%s: github_issues needs repos", s.ID))
		}
		for _, r := range s.Repos {
			if !repoPattern.MatchString(r) {
				problems = append(problems, fmt.Sprintf("%s: invalid repo %q", s.ID, r))
			}
		}
	case KindStackExchange:
		if s.Site == "" || !tagPattern.MatchString(s.Site) || len(s.Tags) == 0 {
			problems = append(problems, fmt.Sprintf("%s: stackexchange needs site and tags", s.ID))
		}
	}
	return problems
}
