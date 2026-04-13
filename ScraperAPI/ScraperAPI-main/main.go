package main

import (
	"log"

	"github.com/ai-wayfinder/scraperAPI/flights"
	"github.com/ai-wayfinder/scraperAPI/server"
)

func main() {
	if err := flights.ParseAirportCSV(); err != nil {
		log.Fatalf("failed to load airport data: %v", err)
	}

	if err := flights.ParseAirlineCSV(); err != nil {
		log.Fatalf("failed to load airline data: %v", err)
	}

	srv := server.New()
	srv.Start()
}
