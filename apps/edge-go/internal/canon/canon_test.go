package canon

import (
	"testing"
)

func TestURL(t *testing.T) {
	cases := []struct {
		name, in, want string
	}{
		{"strips utm and fragment", "https://example.com/post?utm_source=rss&utm_medium=feed#comments", "https://example.com/post"},
		{"lowercases host and scheme", "HTTPS://Example.COM/Post", "https://example.com/Post"},
		{"keeps path case", "https://example.com/A/B", "https://example.com/A/B"},
		{"drops www", "https://www.anthropic.com/news/x", "https://anthropic.com/news/x"},
		{"drops default port", "https://example.com:443/a", "https://example.com/a"},
		{"keeps custom port", "https://example.com:8443/a", "https://example.com:8443/a"},
		{"http upgraded", "http://example.com/a", "https://example.com/a"},
		{"trailing slash removed", "https://example.com/a/", "https://example.com/a"},
		{"root keeps slash", "https://example.com", "https://example.com/"},
		{"amp suffix", "https://example.com/story/amp", "https://example.com/story"},
		{"amp subdomain", "https://amp.example.com/story", "https://example.com/story"},
		{"sorts remaining params", "https://example.com/s?b=2&a=1&fbclid=x", "https://example.com/s?a=1&b=2"},
		{"keeps meaningful params", "https://news.ycombinator.com/item?id=123", "https://news.ycombinator.com/item?id=123"},
		{"case-insensitive tracking keys", "https://example.com/p?UTM_Campaign=z&Ref=hn", "https://example.com/p"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := URL(tc.in)
			if err != nil {
				t.Fatalf("URL(%q) error: %v", tc.in, err)
			}
			if got != tc.want {
				t.Fatalf("URL(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

func TestURLRejectsUnsupported(t *testing.T) {
	for _, in := range []string{
		"ftp://example.com/a", "javascript:alert(1)", "file:///etc/passwd", "/relative/path",
		"https://user:pass@example.com/", "https://", "not a url at all",
	} {
		if got, err := URL(in); err == nil {
			t.Errorf("URL(%q) = %q, want error", in, got)
		}
	}
}

func FuzzURLIsIdempotent(f *testing.F) {
	for _, seed := range []string{
		"https://www.example.com/a/?utm_source=x&b=2&a=1#frag",
		"http://amp.example.com:80/story/amp",
		"https://example.com/%7Euser?x=%20y",
	} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, in string) {
		once, err := URL(in)
		if err != nil {
			return
		}
		twice, err := URL(once)
		if err != nil {
			t.Fatalf("canonical form %q rejected: %v", once, err)
		}
		if once != twice {
			t.Fatalf("not idempotent: %q -> %q -> %q", in, once, twice)
		}
	})
}

func TestArticleIDMatchesContractFixture(t *testing.T) {
	// contracts/fixtures/article.discovered.v1.json: data.url -> data.canonical_url -> data.article_id
	canonical, err := URL("https://www.anthropic.com/news/claude-example?utm_source=rss")
	if err != nil {
		t.Fatal(err)
	}
	if canonical != "https://anthropic.com/news/claude-example" {
		t.Fatalf("canonical = %s", canonical)
	}
	if got, want := ArticleID(canonical), "b6057b134e61b96fde7799b648e05b79f840502ca05565d16ee82c44f16ba490"; got != want {
		t.Fatalf("ArticleID = %s, want %s", got, want)
	}
}
