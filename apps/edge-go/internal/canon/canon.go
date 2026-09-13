// Package canon turns the many spellings of an article URL into one canonical form.
//
// The canonical URL is identity: article_id = sha256(canonical_url). Over-normalizing
// merges distinct pages; under-normalizing lets tracking parameters split one article into
// many. The rules here are deliberately conservative and each has a test.
package canon

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net"
	"net/netip"
	"net/url"
	"slices"
	"strings"

	"golang.org/x/net/idna"
)

// ErrUnsupportedURL is returned for anything that is not an absolute http(s) URL.
var ErrUnsupportedURL = errors.New("canon: unsupported url")

// trackingParams are removed because they identify the referrer, not the resource.
var trackingParams = map[string]struct{}{
	"fbclid": {}, "gclid": {}, "dclid": {}, "msclkid": {}, "yclid": {}, "twclid": {},
	"mc_cid": {}, "mc_eid": {}, "igshid": {}, "ref": {}, "ref_src": {}, "ref_url": {},
	"source": {}, "cmpid": {}, "_hsenc": {}, "_hsmi": {}, "mkt_tok": {}, "guccounter": {},
	"guce_referrer": {}, "guce_referrer_sig": {}, "amp": {}, "output": {},
}

// URL returns the canonical form of raw.
func URL(raw string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return "", ErrUnsupportedURL
	}
	scheme := strings.ToLower(u.Scheme)
	if (scheme != "http" && scheme != "https") || u.Host == "" || u.User != nil {
		return "", ErrUnsupportedURL
	}

	host := untilStable(strings.ToLower(u.Hostname()), func(h string) string {
		h = strings.TrimSuffix(h, ".")
		h = strings.TrimPrefix(h, "www.")
		return strings.TrimPrefix(h, "amp.")
	})
	host, ok := validHost(host)
	if !ok {
		return "", ErrUnsupportedURL
	}
	port := u.Port()
	if port == "80" || port == "443" {
		port = "" // output is always https (see below), so both defaults collapse
	}
	switch {
	case port != "":
		host = net.JoinHostPort(host, port)
	case strings.Contains(host, ":"):
		host = "[" + host + "]" // bare IPv6 literal
	}

	path := untilStable(u.EscapedPath(), func(p string) string {
		p = strings.TrimRight(p, "/")
		return strings.TrimSuffix(p, "/amp")
	})
	if path == "" {
		path = "/"
	}

	query := u.Query()
	for key := range query {
		lower := strings.ToLower(key)
		if strings.HasPrefix(lower, "utm_") {
			query.Del(key)
			continue
		}
		if _, drop := trackingParams[lower]; drop {
			query.Del(key)
		}
	}
	keys := make([]string, 0, len(query))
	for k := range query {
		keys = append(keys, k)
	}
	slices.Sort(keys)
	var rawQuery strings.Builder
	for i, k := range keys {
		values := query[k]
		slices.Sort(values)
		for j, v := range values {
			if i > 0 || j > 0 {
				rawQuery.WriteByte('&')
			}
			rawQuery.WriteString(url.QueryEscape(k))
			rawQuery.WriteByte('=')
			rawQuery.WriteString(url.QueryEscape(v))
		}
	}

	// https is assumed canonical: nearly every news source redirects http to https, and
	// treating them as distinct would double-count the same article.
	out := "https://" + host + path
	if rawQuery.Len() > 0 {
		out += "?" + rawQuery.String()
	}
	return out, nil
}

// validHost accepts IP literals and DNS names, converting internationalized names to
// punycode so both spellings of an IDN map to one identity.
func validHost(host string) (string, bool) {
	if host == "" {
		return "", false
	}
	if addr, err := netip.ParseAddr(host); err == nil {
		return addr.Unmap().String(), true
	}
	ascii, err := idna.Lookup.ToASCII(host)
	if err != nil || ascii == "" || len(ascii) > 253 {
		return "", false
	}
	for _, r := range ascii {
		if !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '-' || r == '.') {
			return "", false
		}
	}
	return ascii, true
}

// untilStable applies f until the value stops changing, so "www.www.x" and "/a/amp/amp"
// normalize fully in one call. Canonicalization must be idempotent (fuzz-tested).
func untilStable(s string, f func(string) string) string {
	for {
		next := f(s)
		if next == s {
			return s
		}
		s = next
	}
}

// ArticleID is the contract-defined identity: hex(sha256(canonical_url)).
func ArticleID(canonicalURL string) string {
	sum := sha256.Sum256([]byte(canonicalURL))
	return hex.EncodeToString(sum[:])
}
