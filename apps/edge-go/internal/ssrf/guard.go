// Package ssrf provides an HTTP client that cannot be tricked into reaching internal networks.
//
// Every URL the ingestor fetches comes from an untrusted feed or a link on the open web. On
// Cloud Run the metadata server (169.254.169.254) hands out OAuth tokens for the service
// account, so a successful SSRF would be a credential leak.
//
// The check runs in net.Dialer.Control, which sees the IP address actually being
// connected to after DNS resolution. That defeats DNS rebinding (a hostname that resolves
// public at validation time and private at connect time), because there is no gap between
// check and use. Redirects dial through the same Control hook, so a public URL that
// redirects to a private address is blocked too.
package ssrf

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"strconv"
	"syscall"
	"time"
)

// ErrBlocked means a connection target was rejected by policy.
var ErrBlocked = errors.New("ssrf: destination blocked")

// blockedPrefixes covers addresses that are never valid public web destinations.
var blockedPrefixes = mustPrefixes(
	"0.0.0.0/8",       // "this network"
	"10.0.0.0/8",      // private
	"100.64.0.0/10",   // carrier-grade NAT
	"127.0.0.0/8",     // loopback
	"169.254.0.0/16",  // link-local, incl. cloud metadata
	"172.16.0.0/12",   // private
	"192.0.0.0/24",    // IETF protocol assignments
	"192.0.2.0/24",    // TEST-NET-1
	"192.88.99.0/24",  // 6to4 relay anycast
	"192.168.0.0/16",  // private
	"198.18.0.0/15",   // benchmarking
	"198.51.100.0/24", // TEST-NET-2
	"203.0.113.0/24",  // TEST-NET-3
	"224.0.0.0/4",     // multicast
	"240.0.0.0/4",     // reserved + broadcast
	"::/128",          // unspecified
	"::1/128",         // loopback
	"64:ff9b::/96",    // NAT64: can embed any IPv4, incl. private
	"64:ff9b:1::/48",  // local-use NAT64
	"100::/64",        // discard
	"2001:db8::/32",   // documentation
	"2002::/16",       // 6to4: embeds IPv4
	"fc00::/7",        // unique local
	"fe80::/10",       // link-local
	"ff00::/8",        // multicast
)

func mustPrefixes(cidrs ...string) []netip.Prefix {
	out := make([]netip.Prefix, len(cidrs))
	for i, c := range cidrs {
		out[i] = netip.MustParsePrefix(c)
	}
	return out
}

// Policy decides which connection targets are allowed.
type Policy struct {
	AllowedPorts map[int]struct{}
	// AllowLoopback exists only so tests can use httptest servers. Never set in production.
	AllowLoopback bool
}

// DefaultPolicy permits only public addresses on standard web ports.
func DefaultPolicy() Policy {
	return Policy{AllowedPorts: map[int]struct{}{80: {}, 443: {}}}
}

// CheckAddr validates a resolved "ip:port" connection target.
func (p Policy) CheckAddr(address string) error {
	host, portStr, err := net.SplitHostPort(address)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrBlocked, err)
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return fmt.Errorf("%w: bad port %q", ErrBlocked, portStr)
	}
	ip, err := netip.ParseAddr(host)
	if err != nil {
		return fmt.Errorf("%w: unresolved host %q", ErrBlocked, host)
	}
	ip = ip.Unmap() // ::ffff:10.0.0.1 must be judged as 10.0.0.1
	if p.AllowLoopback && ip.IsLoopback() {
		return nil
	}
	if _, ok := p.AllowedPorts[port]; !ok {
		return fmt.Errorf("%w: port %d", ErrBlocked, port)
	}
	for _, prefix := range blockedPrefixes {
		if prefix.Contains(ip) {
			return fmt.Errorf("%w: %s in %s", ErrBlocked, ip, prefix)
		}
	}
	return nil
}

// ClientOptions bounds resource usage per fetch.
type ClientOptions struct {
	Timeout      time.Duration
	MaxRedirects int
	UserAgent    string
}

// NewClient returns an http.Client whose every connection passes the policy.
func NewClient(policy Policy, opts ClientOptions) *http.Client {
	dialer := &net.Dialer{
		Timeout:   5 * time.Second,
		KeepAlive: 30 * time.Second,
		Control: func(network, address string, _ syscall.RawConn) error {
			if network != "tcp4" && network != "tcp6" {
				return fmt.Errorf("%w: network %s", ErrBlocked, network)
			}
			return policy.CheckAddr(address)
		},
	}
	transport := &http.Transport{
		Proxy:                 nil, // never honour HTTP(S)_PROXY from the environment
		DialContext:           dialer.DialContext,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   4,
		IdleConnTimeout:       60 * time.Second,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: 10 * time.Second,
	}
	userAgent := opts.UserAgent
	return &http.Client{
		Timeout:   opts.Timeout,
		Transport: userAgentTransport{base: transport, ua: userAgent},
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) > opts.MaxRedirects {
				return fmt.Errorf("%w: too many redirects", ErrBlocked)
			}
			if req.URL.Scheme != "http" && req.URL.Scheme != "https" {
				return fmt.Errorf("%w: redirect to scheme %q", ErrBlocked, req.URL.Scheme)
			}
			return nil
		},
	}
}

type userAgentTransport struct {
	base http.RoundTripper
	ua   string
}

func (t userAgentTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if t.ua != "" && req.Header.Get("User-Agent") == "" {
		req = req.Clone(req.Context())
		req.Header.Set("User-Agent", t.ua)
	}
	return t.base.RoundTrip(req)
}

// IsBlocked reports whether err (possibly wrapped by net/http) is a policy rejection.
func IsBlocked(err error) bool {
	return errors.Is(err, ErrBlocked)
}
