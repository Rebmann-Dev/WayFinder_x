package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	flights "github.com/ai-wayfinder/scraperAPI/flights"
)

func main() {
	err := flights.ParseAirportCSV()
	if err != nil {
		panic(err)
	}

	err = flights.ParseAirlineCSV()
	if err != nil {
		panic(err)
	}

	// All examples use a 30-second timeout — enough for Google's HTML to load.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	switch example := exampleName(); example {
	case "roundtrip":
		roundTripExample(ctx)
	case "nonstop":
		nonstopExample(ctx)
	default:
		oneWayExample(ctx)
	}
}

// exampleName reads the first CLI arg, defaulting to "oneway".
func exampleName() string {
	if len(os.Args) > 1 {
		return os.Args[1]
	}
	return "oneway"
}

// ─── Example 1: one-way ───────────────────────────────────────────────────────

func oneWayExample(ctx context.Context) {
	fmt.Println("═══════════════════════════════════════")
	fmt.Println("  Example: One-way  JFK → LAX")
	fmt.Println("═══════════════════════════════════════")

	f, err := flights.NewFilter(
		[]flights.FlightData{
			{Date: "2026-08-15", FromAirport: "JFK", ToAirport: "LAX"},
		},
		flights.OneWay,
		flights.Economy,
		flights.PassengerCount{Adults: 1},
		flights.AnyStops,
		0,
	)
	if err != nil {
		log.Fatalf("filter error: %v", err)
	}

	fmt.Println("Search URL:", f.URL())
	fmt.Println()

	result, err := flights.GetFlights(ctx, f)
	if err != nil {
		log.Fatalf("search error: %v", err)
	}

	printResult(result)
}

// ─── Example 2: round-trip ────────────────────────────────────────────────────

func roundTripExample(ctx context.Context) {
	fmt.Println("═══════════════════════════════════════")
	fmt.Println("  Example: Round-trip  SFO ↔ LHR")
	fmt.Println("═══════════════════════════════════════")

	f, err := flights.NewFilter(
		[]flights.FlightData{
			{Date: "2026-09-01", FromAirport: "SFO", ToAirport: "LHR"},
			{Date: "2026-09-14", FromAirport: "LHR", ToAirport: "SFO"},
		},
		flights.RoundTrip,
		flights.Business,
		flights.PassengerCount{Adults: 2},
		flights.AnyStops,
		0,
	)
	if err != nil {
		log.Fatalf("filter error: %v", err)
	}

	fmt.Println("Search URL:", f.URL())
	fmt.Println()

	result, err := flights.GetFlights(ctx, f)
	if err != nil {
		log.Fatalf("search error: %v", err)
	}

	printResult(result)
}

// ─── Example 3: nonstop only ─────────────────────────────────────────────────

func nonstopExample(ctx context.Context) {
	fmt.Println("═══════════════════════════════════════")
	fmt.Println("  Example: Nonstop only  ORD → MIA")
	fmt.Println("═══════════════════════════════════════")

	f, err := flights.NewFilter(
		[]flights.FlightData{
			{Date: "2026-08-20", FromAirport: "ORD", ToAirport: "MIA"},
		},
		flights.OneWay,
		flights.Economy,
		flights.PassengerCount{Adults: 1, Children: 2},
		flights.Nonstop,
		0,
	)
	if err != nil {
		log.Fatalf("filter error: %v", err)
	}

	fmt.Println("Search URL:", f.URL())
	fmt.Println()

	result, err := flights.GetFlights(ctx, f)
	if err != nil {
		log.Fatalf("search error: %v", err)
	}

	printResult(result)
}

// ─── Output formatting ────────────────────────────────────────────────────────

func printResult(r *flights.Result) {
	fmt.Printf("Price level: %s\n", r.CurrentPrice)
	fmt.Printf("Flights found: %d\n", len(r.Flights))
	fmt.Println()

	if len(r.Flights) == 0 {
		fmt.Println("No flights returned — the HTML selectors may need updating.")
		fmt.Println("Tip: capture a live page with curl and run the parser against it.")
		return
	}

	// Separate best vs regular flights.
	var best, rest []flights.Flight
	for _, f := range r.Flights {
		if f.IsTop {
			best = append(best, f)
		} else {
			rest = append(rest, f)
		}
	}

	if len(best) > 0 {
		fmt.Println("── Best flights ────────────────────────")
		for _, f := range best {
			printFlight(f)
		}
		fmt.Println()
	}

	if len(rest) > 0 {
		fmt.Println("── Other flights ───────────────────────")
		for _, f := range rest {
			printFlight(f)
		}
	}
}

func printFlight(f flights.Flight) {
	arrival := f.Arrival
	if f.ArrivalTimeAhead != "" {
		arrival += " " + f.ArrivalTimeAhead
	}

	stops := "nonstop"
	switch f.Stops {
	case 1:
		stops = "1 stop"
	default:
		if f.Stops > 1 {
			stops = fmt.Sprintf("%d stops", f.Stops)
		}
	}

	fmt.Printf("  %-20s  %s → %-12s  %-12s  %-8s  %s \t Emissions: %d kg CO₂ Percentage diff: %.1f%% \n",
		f.Airline.Name, f.Departure, arrival, f.Duration, stops, f.Price, f.Emissions.Current/1000, f.Emissions.PercentageDiff)

	if f.Delay != nil {
		fmt.Printf("  %s⚠  %s\n", indent(32), *f.Delay)
	}
}

func indent(n int) string {
	b := make([]byte, n)
	for i := range b {
		b[i] = ' '
	}
	return string(b)
}
