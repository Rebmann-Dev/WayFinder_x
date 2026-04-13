package flights

import (
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
	"net/http"

	"github.com/andybalholm/brotli"
)

// readBody reads and decompresses the response body according to the
// Content-Encoding header.
//
//   - gzip  → handled by net/http automatically (DisableCompression=false),
//     but we handle it here too as a safety net.
//   - br    → decoded with andybalholm/brotli (same library used by primp).
//   - identity / missing → plain read.
func readBody(resp *http.Response) ([]byte, error) {
	encoding := resp.Header.Get("Content-Encoding")

	switch encoding {
	case "br":
		r := brotli.NewReader(resp.Body)
		return io.ReadAll(r)

	case "gzip":
		gr, err := gzip.NewReader(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("gzip reader: %w", err)
		}
		defer gr.Close()
		return io.ReadAll(gr)

	default:
		raw, err := io.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
		// Defensive: some servers send gzip without the header
		if bytes.HasPrefix(raw, []byte{0x1f, 0x8b}) {
			gr, err := gzip.NewReader(bytes.NewReader(raw))
			if err == nil {
				defer gr.Close()
				return io.ReadAll(gr)
			}
		}
		return raw, nil
	}
}