package server

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

// Server is a wrapper around our core
type Server struct {
	addr string
	e    *http.Server
}

// New will create a new instance of the server.
func New() *Server {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	router := SetupRouter()

	return &Server{
		e: &http.Server{
			Addr:    fmt.Sprintf(":%s", port),
			Handler: router,
		},
	}
}

// Start runs the HTTP server in a background goroutine and blocks until
// the process receives SIGINT or SIGTERM. On shutdown it calls
// http.Server.Shutdown with a 5-second deadline so in-flight requests can
// drain before the process exits.
func (s *Server) Start() {
	var wg sync.WaitGroup

	wg.Go(func() {
		log.Println("Starting server at", s.e.Addr)
		if err := s.e.ListenAndServe(); err != nil {
			if err == http.ErrServerClosed {
				log.Println("Server closed")
			} else {
				log.Fatalf("Server error: %v", err)
			}
		}
	})

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)
	<-quit

	log.Println("shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := s.e.Shutdown(ctx); err != nil {
		log.Fatalf("forced shutdown: %v", err)
	}
	log.Println("done")
}
