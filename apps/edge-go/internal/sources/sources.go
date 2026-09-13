// Package sources loads and validates the source registry (config/sources.yaml).
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
)

// Source is one registry entry.
type Source struct {
	ID        string  `yaml:"id"`
	Kind      Kind    `yaml:"kind"`
	Name      string  `yaml:"name"`
	URL       string  `yaml:"url"`
	Authority float64 `yaml:"authority"`
	MaxItems  int     `yaml:"max_items"`
	Disabled  bool    `yaml:"disabled"`
}

var idPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{1,63}$`)

const defaultMaxItems = 50

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
		if s.Kind != KindRSS && s.Kind != KindHN {
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
	}
	if len(problems) > 0 {
		return nil, fmt.Errorf("invalid registry: %v", problems)
	}
	return doc.Sources, nil
}
