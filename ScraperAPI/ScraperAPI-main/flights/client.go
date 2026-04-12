package flights

import (
	"context"
	"fmt"
	"net/http"
	"time"

	utls "github.com/refraction-networking/utls"
)

// h1Conn wraps a utls.UConn and overrides ConnectionState so that
// net/http.Transport sees NegotiatedProtocol = "http/1.1" regardless of
// what was actually negotiated in ALPN.
//
// Why this is needed:
//   - HelloChrome_Auto advertises ["h2", "http/1.1"] in ALPN. Google agrees
//     on h2, so uConn.ConnectionState().NegotiatedProtocol == "h2".
//   - net/http.Transport inspects NegotiatedProtocol after DialTLSContext
//     returns. If it sees "h2" it expects to speak HTTP/2 on that conn —
//     but since we used a plain *http.Transport (not http2.Transport), it
//     has no HTTP/2 framer and immediately blows up with
//     "malformed HTTP response \x00\x00\x12\x04...".
//   - By lying and returning "http/1.1" here, Transport stays in HTTP/1.1
//     mode for the full request/response cycle, which works fine.
//   - The actual wire bytes are still the real Chrome TLS handshake — we are
//     only overriding the Go struct field that Transport reads afterwards.
type h1Conn struct {
	*utls.UConn
}

// ConnectionState returns the underlying uTLS connection state with the
// NegotiatedProtocol field rewritten to "http/1.1". See the h1Conn type
// comment for the full explanation of why this override is required.
func (c h1Conn) ConnectionState() utls.ConnectionState {
	cs := c.UConn.ConnectionState()
	cs.NegotiatedProtocol = "http/1.1"
	return cs
}

// httpClient is the shared HTTP client used for every outbound scrape
// request.  A singleton lets net/http.Transport reuse TCP/TLS connections
// across requests instead of rebuilding them on every call.
var httpClient = &http.Client{
	Transport: &http.Transport{},
	Timeout:   60 * time.Second,
}

// chromeHeaders returns the minimum set of HTTP headers that make Google
// believe the request came from a desktop Chrome browser.
func chromeHeaders() map[string]string {
	return map[string]string{
		"User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
		"Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
		"Accept-Language":           "en-US,en;q=0.9",
		"Accept-Encoding":           "gzip, deflate, br",
		"Cache-Control":             "no-cache",
		"Pragma":                    "no-cache",
		"Sec-Fetch-Dest":            "document",
		"Sec-Fetch-Mode":            "navigate",
		"Sec-Fetch-Site":            "none",
		"Sec-Fetch-User":            "?1",
		"Upgrade-Insecure-Requests": "1",
	}
}

// fetchHTML fetches the raw HTML from a URL using the uTLS Chrome-mimicking
// client.  It returns the response body bytes.
func fetchHTML(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("flights: failed to build request: %w", err)
	}

	for k, v := range chromeHeaders() {
		req.Header.Set(k, v)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("flights: HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("flights: unexpected HTTP status %d for %s", resp.StatusCode, url)
	}

	// Respect Content-Encoding: gzip / br — net/http decodes gzip automatically
	// when Transport.DisableCompression == false.
	body, err := readBody(resp)
	if err != nil {
		return nil, fmt.Errorf("flights: failed to read response body: %w", err)
	}

	return body, nil
}

// GetFlights fetches and parses Google Flights results for the given Filter.
//
// The context controls the HTTP request deadline; a 30–60 s timeout is
// recommended since Google Flights pages can be large.
func GetFlights(ctx context.Context, f *Filter) (*Result, error) {
	print(f.URL())
	print()
	html, err := fetchHTML(ctx, f.URL())
	if err != nil {
		return nil, fmt.Errorf("flights.GetFlights: %w", err)
	}

	result, err := parseFlights(html)
	if err != nil {
		return nil, fmt.Errorf("flights.GetFlights: parse error: %w", err)
	}

	return result, nil
}
