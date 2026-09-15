// Package fetch retrieves untrusted web pages politely and within strict resource bounds.
//
// Errors are classified as Permanent or Transient because the caller maps them to Pub/Sub
// semantics. Transient errors return non-2xx, so Pub/Sub redelivers with backoff and
// eventually dead-letters. Permanent errors are acknowledged and recorded, because retrying
// a 404 or a blocked address five times only wastes quota.
package fetch

import (
	"context"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/temoto/robotstxt"
	"golang.org/x/time/rate"

	"github.com/dilipna/xploremore/apps/edge-go/internal/ssrf"
)

// ErrPermanent wraps failures that will not succeed on retry.
var ErrPermanent = errors.New("permanent fetch failure")

// ErrTransient wraps failures worth retrying later.
var ErrTransient = errors.New("transient fetch failure")

// ErrThrottled marks a transient failure where the per-host limiter could not grant a slot
// early enough to leave MinFetchBudget before the deadline. It is always wrapped together
// with ErrTransient; callers that only care about retry semantics can ignore it.
var ErrThrottled = errors.New("host rate limit exceeds deadline")

// Result is a successfully fetched document.
type Result struct {
	FinalURL    *url.URL
	Body        []byte
	ContentType string
	Status      int
}

// Options bounds a Fetcher.
type Options struct {
	UserAgent    string
	MaxBytes     int64
	Timeout      time.Duration
	PerHostRate  rate.Limit // requests/second per host (politeness)
	PerHostBurst int
	// MinFetchBudget is the time a request must still have after its rate-limit slot.
	// Waiting for a slot that leaves less only produces a timed-out fetch and burns the slot.
	MinFetchBudget   time.Duration
	RobotsTTL        time.Duration
	AllowedMIMETypes []string
}

// DefaultOptions are conservative production defaults.
func DefaultOptions() Options {
	return Options{
		UserAgent:        "XploreMoreBot/0.1 (+https://github.com/dilipna/xploremore)",
		MaxBytes:         5 << 20,
		Timeout:          15 * time.Second,
		PerHostRate:      rate.Every(2 * time.Second),
		PerHostBurst:     2,
		MinFetchBudget:   5 * time.Second,
		RobotsTTL:        6 * time.Hour,
		AllowedMIMETypes: []string{"text/html", "application/xhtml+xml"},
	}
}

// Fetcher is safe for concurrent use.
type Fetcher struct {
	client *http.Client
	opts   Options

	mu       sync.Mutex
	limiters map[string]*rate.Limiter
	robots   map[string]robotsEntry
}

type robotsEntry struct {
	data    *robotstxt.RobotsData
	expires time.Time
}

// New builds a Fetcher over an SSRF-guarded client.
func New(policy ssrf.Policy, opts Options) *Fetcher {
	return &Fetcher{
		client:   ssrf.NewClient(policy, ssrf.ClientOptions{Timeout: opts.Timeout, MaxRedirects: 3, UserAgent: opts.UserAgent}),
		opts:     opts,
		limiters: map[string]*rate.Limiter{},
		robots:   map[string]robotsEntry{},
	}
}

// Client exposes the guarded client for other untrusted fetches (feeds, APIs).
func (f *Fetcher) Client() *http.Client { return f.client }

func (f *Fetcher) limiter(host string) *rate.Limiter {
	f.mu.Lock()
	defer f.mu.Unlock()
	l, ok := f.limiters[host]
	if !ok {
		l = rate.NewLimiter(f.opts.PerHostRate, f.opts.PerHostBurst)
		f.limiters[host] = l
	}
	return l
}

// waitForSlot reserves a per-host rate-limit slot and waits for it, but only when the slot
// leaves at least MinFetchBudget before ctx's deadline. Otherwise it cancels the reservation
// (returning the token to the limiter for a request that can use it) and fails at once.
//
// rate.Limiter.Wait alone only refuses delays longer than the whole deadline, so a slot granted
// just before the deadline leaves the HTTP request no time: the delivery times out, is retried,
// and has still consumed a politeness slot. The full e2e run logged 485 ingestor retries of
// this family (CONTINUE_SESSION §4.3); the fix is re-measured there.
func (f *Fetcher) waitForSlot(ctx context.Context, host string) error {
	now := time.Now()
	r := f.limiter(host).ReserveN(now, 1)
	if !r.OK() {
		return fmt.Errorf("%w: rate limiter: burst below 1", ErrPermanent)
	}
	delay := r.DelayFrom(now)
	if deadline, ok := ctx.Deadline(); ok {
		if remaining := deadline.Sub(now); delay+f.opts.MinFetchBudget > remaining {
			r.CancelAt(now)
			return fmt.Errorf("%w: %w: slot in %v, %v left", ErrTransient, ErrThrottled,
				delay.Round(time.Millisecond), remaining.Round(time.Millisecond))
		}
	}
	if delay == 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-timer.C:
		return nil
	case <-ctx.Done():
		r.Cancel()
		return fmt.Errorf("%w: rate limiter: %v", ErrTransient, ctx.Err())
	}
}

// allowedByRobots consults a cached robots.txt. Unreachable or 5xx robots files allow
// crawling after caching the failure briefly. Per RFC 9309 a 4xx means "no restrictions".
func (f *Fetcher) allowedByRobots(ctx context.Context, u *url.URL) bool {
	origin := u.Scheme + "://" + u.Host
	f.mu.Lock()
	entry, ok := f.robots[origin]
	f.mu.Unlock()
	if !ok || time.Now().After(entry.expires) {
		entry = robotsEntry{expires: time.Now().Add(f.opts.RobotsTTL)}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, origin+"/robots.txt", nil)
		if err == nil {
			if res, err := f.client.Do(req); err == nil {
				body, _ := io.ReadAll(io.LimitReader(res.Body, 512<<10))
				_ = res.Body.Close()
				if data, err := robotstxt.FromStatusAndBytes(res.StatusCode, body); err == nil {
					entry.data = data
				}
			} else {
				entry.expires = time.Now().Add(10 * time.Minute)
			}
		}
		f.mu.Lock()
		f.robots[origin] = entry
		f.mu.Unlock()
	}
	if entry.data == nil {
		return true
	}
	path := u.EscapedPath()
	if u.RawQuery != "" {
		path += "?" + u.RawQuery
	}
	return entry.data.TestAgent(path, "XploreMoreBot")
}

// Get fetches rawURL, enforcing robots.txt, per-host rate limits, size and type bounds.
func (f *Fetcher) Get(ctx context.Context, rawURL string) (*Result, error) {
	u, err := url.Parse(rawURL)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") {
		return nil, fmt.Errorf("%w: invalid url", ErrPermanent)
	}
	if !f.allowedByRobots(ctx, u) {
		return nil, fmt.Errorf("%w: disallowed by robots.txt", ErrPermanent)
	}
	if err := f.waitForSlot(ctx, u.Hostname()); err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrPermanent, err)
	}
	req.Header.Set("Accept", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1")
	res, err := f.client.Do(req)
	if err != nil {
		return nil, classifyTransportError(err)
	}
	defer res.Body.Close()

	switch {
	case res.StatusCode == http.StatusTooManyRequests || res.StatusCode >= 500:
		return nil, fmt.Errorf("%w: status %d", ErrTransient, res.StatusCode)
	case res.StatusCode >= 400:
		return nil, fmt.Errorf("%w: status %d", ErrPermanent, res.StatusCode)
	}

	mediaType, _, _ := mime.ParseMediaType(res.Header.Get("Content-Type"))
	if !f.mimeAllowed(mediaType) {
		return nil, fmt.Errorf("%w: content-type %q", ErrPermanent, mediaType)
	}
	// The transport transparently gunzips, so this limit applies to decompressed bytes:
	// a small gzip bomb cannot expand past MaxBytes.
	body, err := io.ReadAll(io.LimitReader(res.Body, f.opts.MaxBytes+1))
	if err != nil {
		return nil, fmt.Errorf("%w: reading body: %v", ErrTransient, err)
	}
	if int64(len(body)) > f.opts.MaxBytes {
		return nil, fmt.Errorf("%w: body exceeds %d bytes", ErrPermanent, f.opts.MaxBytes)
	}
	return &Result{FinalURL: res.Request.URL, Body: body, ContentType: mediaType, Status: res.StatusCode}, nil
}

func (f *Fetcher) mimeAllowed(mediaType string) bool {
	for _, allowed := range f.opts.AllowedMIMETypes {
		if strings.EqualFold(mediaType, allowed) {
			return true
		}
	}
	return false
}

func classifyTransportError(err error) error {
	if ssrf.IsBlocked(err) {
		return fmt.Errorf("%w: %v", ErrPermanent, err)
	}
	var dnsErr *net.DNSError
	if errors.As(err, &dnsErr) && dnsErr.IsNotFound {
		return fmt.Errorf("%w: %v", ErrPermanent, err)
	}
	return fmt.Errorf("%w: %v", ErrTransient, err)
}
