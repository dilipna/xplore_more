package ssrf

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestCheckAddrBlocksInternalTargets(t *testing.T) {
	p := DefaultPolicy()
	blocked := []string{
		"169.254.169.254:80",    // GCP/AWS metadata
		"127.0.0.1:443",         // loopback
		"10.1.2.3:443",          // private
		"172.16.0.1:443",        // private
		"192.168.1.1:80",        // private
		"100.64.0.1:443",        // CGNAT
		"0.0.0.0:80",            // this network
		"[::1]:443",             // IPv6 loopback
		"[::ffff:10.0.0.1]:443", // IPv4-mapped private
		"[::ffff:169.254.169.254]:80",
		"[fd00::1]:443",        // unique local
		"[fe80::1]:443",        // link-local
		"[64:ff9b::a00:1]:443", // NAT64-embedded 10.0.0.1
		"[2002:a00:1::1]:443",  // 6to4-embedded 10.0.0.1
		"8.8.8.8:22",           // public but non-web port
		"8.8.8.8:6379",
	}
	for _, addr := range blocked {
		if err := p.CheckAddr(addr); !IsBlocked(err) {
			t.Errorf("CheckAddr(%s) = %v, want blocked", addr, err)
		}
	}
}

func TestCheckAddrAllowsPublicWebTargets(t *testing.T) {
	p := DefaultPolicy()
	for _, addr := range []string{"8.8.8.8:443", "1.1.1.1:80", "[2606:4700:4700::1111]:443"} {
		if err := p.CheckAddr(addr); err != nil {
			t.Errorf("CheckAddr(%s) = %v, want allowed", addr, err)
		}
	}
}

func TestClientBlocksLoopbackAtConnectTime(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("secret"))
	}))
	defer srv.Close()

	// "localhost" resolves to loopback only at dial time. Validating the hostname string
	// alone would miss it, so this proves the check runs on the resolved IP.
	target := strings.Replace(srv.URL, "127.0.0.1", "localhost", 1)
	client := NewClient(DefaultPolicy(), ClientOptions{Timeout: 3 * time.Second, MaxRedirects: 3})
	_, err := client.Get(target)
	if !IsBlocked(err) {
		t.Fatalf("expected blocked, got %v", err)
	}
}

func TestClientBlocksRedirectToInternalAddress(t *testing.T) {
	// A permissive policy lets the test reach the first (loopback) hop. The redirect
	// target is a private address the policy must still refuse.
	policy := DefaultPolicy()
	policy.AllowLoopback = true
	redirector := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "http://169.254.169.254/computeMetadata/v1/", http.StatusFound)
	}))
	defer redirector.Close()

	client := NewClient(policy, ClientOptions{Timeout: 3 * time.Second, MaxRedirects: 3})
	_, err := client.Get(redirector.URL)
	if !IsBlocked(err) {
		t.Fatalf("expected redirect to metadata server to be blocked, got %v", err)
	}
}

func TestClientRejectsRedirectToNonHTTPScheme(t *testing.T) {
	policy := DefaultPolicy()
	policy.AllowLoopback = true
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "gopher://example.com/", http.StatusFound)
	}))
	defer srv.Close()
	client := NewClient(policy, ClientOptions{Timeout: 3 * time.Second, MaxRedirects: 3})
	if _, err := client.Get(srv.URL); err == nil {
		t.Fatal("expected error for gopher redirect")
	}
}

func TestClientCapsRedirectChains(t *testing.T) {
	policy := DefaultPolicy()
	policy.AllowLoopback = true
	var srv *httptest.Server
	srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, srv.URL+"/loop", http.StatusFound)
	}))
	defer srv.Close()
	client := NewClient(policy, ClientOptions{Timeout: 3 * time.Second, MaxRedirects: 3})
	if _, err := client.Get(srv.URL); !IsBlocked(err) {
		t.Fatalf("expected redirect cap, got %v", err)
	}
}

func TestEveryAddressLocalhostResolvesToIsBlocked(t *testing.T) {
	p := DefaultPolicy()
	resolved, _ := net.DefaultResolver.LookupHost(context.Background(), "localhost")
	for _, ip := range resolved {
		if err := p.CheckAddr(net.JoinHostPort(ip, "443")); !IsBlocked(err) {
			t.Errorf("resolved %s should be blocked", ip)
		}
	}
}
