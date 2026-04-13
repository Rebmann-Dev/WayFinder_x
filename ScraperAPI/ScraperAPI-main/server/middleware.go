package server

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"time"
)

// LogRequest is an http.Handler middleware that dumps every incoming
// request (headers and body) to the standard logger before delegating to
// the next handler. It is intended for local debugging and low-volume
// environments; it is not safe to leave enabled in production traffic
// because it logs full request bodies.
func LogRequest(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reqDump, err := httputil.DumpRequest(r, true)
		if err != nil {
			log.Printf("Error dumping request: %v", err)
		} else {
			log.Printf("Incoming request:\n%s", string(reqDump))
		}
		next.ServeHTTP(w, r)
	})
}

type respInfoHijacker struct {
	http.ResponseWriter
	responseCode int
	respBody     bytes.Buffer
}

// Write captures the response body when the status code indicates an
// error (>= 400) so LogResponseInfo can log it, then forwards the bytes to
// the wrapped ResponseWriter. If WriteHeader was never called explicitly
// the status is defaulted to 200, mirroring net/http's own behavior.
func (w *respInfoHijacker) Write(resp []byte) (int, error) {
	if w.responseCode == 0 {
		w.responseCode = http.StatusOK
	} else if w.responseCode >= 400 {
		_, _ = w.respBody.Write(resp)
	}
	return w.ResponseWriter.Write(resp)
}

// WriteHeader records the status code on the hijacker before forwarding to
// the wrapped ResponseWriter so LogResponseInfo can read it after the
// handler returns.
func (w *respInfoHijacker) WriteHeader(status int) {
	w.responseCode = status
	w.ResponseWriter.WriteHeader(status)
}

// LogResponseInfo is an http.Handler middleware that logs one summary
// line per request (method, path, query, status, duration). For responses
// with status >= 400 it additionally logs the response body and a full
// dump of the offending request to aid debugging. It wraps the
// ResponseWriter with a respInfoHijacker to capture the status and body.
func LogResponseInfo(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var bodyBytes []byte
		var err error

		if r.Body != nil {
			bodyBytes, err = io.ReadAll(r.Body)
			if err != nil {
				log.Printf("Error reading request body: %v", err)
			}
		}

		r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))

		cw := respInfoHijacker{ResponseWriter: w}
		start := time.Now()
		next.ServeHTTP(&cw, r)
		duration := time.Since(start)

		log.Printf("Request: %s %s, Params: %v, Response Code: %d, Duration: %v", r.Method, r.URL.Path, r.URL.Query(), cw.responseCode, duration)
		if cw.responseCode >= 400 {
			log.Printf("Response Body: %s", cw.respBody.String())

			r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			reqDump, err := httputil.DumpRequest(r, true)

			var reqContent string
			if err != nil {
				reqContent = fmt.Sprintf("Error dumping request: %v", err)
			} else {
				reqContent = string(reqDump)
			}
			log.Printf("Request that caused error:\n%s", reqContent)
		}
	})
}
