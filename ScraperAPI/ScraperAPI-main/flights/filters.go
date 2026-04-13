package flights

import (
	"encoding/base64"
	"fmt"
	"regexp"
	"time"
)

// ─── Enumerations ─────────────────────────────────────────────────────────────

// TripType mirrors the integer values Google encodes in the tfs parameter.
type TripType int32

const (
	RoundTrip TripType = 1
	OneWay    TripType = 2
)

// String returns a human-readable label for the TripType ("round-trip",
// "one-way", or "unknown"). It satisfies fmt.Stringer.
func (t TripType) String() string {
	switch t {
	case RoundTrip:
		return "round-trip"
	case OneWay:
		return "one-way"
	}
	return "unknown"
}

// SeatClass mirrors the seat integer values in the tfs parameter.
type SeatClass int32

const (
	Economy        SeatClass = 1
	PremiumEconomy SeatClass = 2
	Business       SeatClass = 3
	First          SeatClass = 4
)

// String returns a human-readable label for the SeatClass ("economy",
// "premium-economy", "business", "first", or "unknown"). It satisfies
// fmt.Stringer.
func (s SeatClass) String() string {
	switch s {
	case Economy:
		return "economy"
	case PremiumEconomy:
		return "premium-economy"
	case Business:
		return "business"
	case First:
		return "first"
	}
	return "unknown"
}

// MaxStops controls the stop filter encoded in the tfs parameter.
type MaxStops int32

const (
	AnyStops    MaxStops = 0
	Nonstop     MaxStops = 1
	MaxOneStop  MaxStops = 2
	MaxTwoStops MaxStops = 3
)

// ─── Input types ──────────────────────────────────────────────────────────────

// FlightData describes a single leg of the journey.
type FlightData struct {
	// Date in YYYY-MM-DD format.
	Date string
	// FromAirport is the 3-letter IATA departure code (e.g. "JFK").
	FromAirport string
	// ToAirport is the 3-letter IATA arrival code (e.g. "LAX").
	ToAirport string
}

// PassengerCount describes how many of each passenger type to include.
// Google Flights distinguishes four categories:
//
//   - Adults: age 12+
//   - Children: age 2-11
//   - InfantsInSeat: under 2, occupying their own seat
//   - InfantsOnLap: under 2, held by an adult (no seat)
//
// The total across all four categories must not exceed 9 (Google's
// hard cap), and InfantsOnLap must be <= Adults since each lap infant
// requires a supervising adult.
type PassengerCount struct {
	Adults        int
	Children      int
	InfantsInSeat int
	InfantsOnLap  int
}

// ─── Filter ───────────────────────────────────────────────────────────────────

// Filter holds a fully-validated, ready-to-encode flight search query.
// Build one with NewFilter; pass it to GetFlights.
type Filter struct {
	legs  []flightLeg
	trip  TripType
	seat  SeatClass
	pax   PassengerCount
	stops MaxStops
	price int32
}

// flightLeg is the validated internal representation of one FlightData entry.
type flightLeg struct {
	date string
	from string // IATA
	to   string // IATA
}

var (
	dateRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
	iataRe = regexp.MustCompile(`^[A-Z]{3}$`)
)

// NewFilter constructs and validates a Filter.
func NewFilter(
	legs []FlightData,
	trip TripType,
	seat SeatClass,
	pax PassengerCount,
	stops MaxStops,
	maxPrice int32,
) (*Filter, error) {
	if len(legs) == 0 {
		return nil, fmt.Errorf("flights: at least one FlightData leg is required")
	}
	if trip == RoundTrip && len(legs) < 2 {
		return nil, fmt.Errorf("flights: round-trip requires at least 2 FlightData legs")
	}

	validated := make([]flightLeg, 0, len(legs))
	for i, leg := range legs {
		if !dateRe.MatchString(leg.Date) {
			return nil, fmt.Errorf("flights: leg %d: invalid date %q (want YYYY-MM-DD)", i, leg.Date)
		}
		if _, err := time.Parse("2006-01-02", leg.Date); err != nil {
			return nil, fmt.Errorf("flights: leg %d: invalid date %q: %w", i, leg.Date, err)
		}
		if !iataRe.MatchString(leg.FromAirport) {
			return nil, fmt.Errorf("flights: leg %d: FromAirport %q is not a valid IATA code", i, leg.FromAirport)
		}
		if !iataRe.MatchString(leg.ToAirport) {
			return nil, fmt.Errorf("flights: leg %d: ToAirport %q is not a valid IATA code", i, leg.ToAirport)
		}
		validated = append(validated, flightLeg{
			date: leg.Date,
			from: leg.FromAirport,
			to:   leg.ToAirport,
		})
	}

	if pax.Adults < 1 {
		return nil, fmt.Errorf("flights: at least 1 adult passenger is required")
	}
	if pax.Children < 0 || pax.InfantsInSeat < 0 || pax.InfantsOnLap < 0 {
		return nil, fmt.Errorf("flights: passenger counts must be non-negative")
	}
	if pax.InfantsOnLap > pax.Adults {
		return nil, fmt.Errorf("flights: lap infants (%d) cannot exceed adults (%d)", pax.InfantsOnLap, pax.Adults)
	}
	total := pax.Adults + pax.Children + pax.InfantsInSeat + pax.InfantsOnLap
	if total > 9 {
		return nil, fmt.Errorf("flights: total passenger count %d exceeds Google's maximum of 9", total)
	}

	return &Filter{
		legs:  validated,
		trip:  trip,
		seat:  seat,
		pax:   pax,
		stops: stops,
		price: maxPrice,
	}, nil
}

// TFSParam encodes the filter into the base64url tfs query parameter
// (the search payload) that Google Flights expects.
func (f *Filter) TFSParam() string {
	return base64.URLEncoding.WithPadding(base64.NoPadding).EncodeToString(encodeTFS(f))
}

// TFUParam encodes the view-state (`tfu`) query parameter that Google
// Flights expects alongside `tfs`.  Today this is a constant payload
// built by encodeTFU; once the individual knobs inside it are mapped
// (sort order, fare type, etc.), this method can take the Filter as
// input and vary its output accordingly.
func (f *Filter) TFUParam() string {
	return base64.URLEncoding.WithPadding(base64.NoPadding).EncodeToString(encodeTFU())
}

// URL returns the full Google Flights search URL for this filter.
func (f *Filter) URL() string {
	return fmt.Sprintf(
		"https://www.google.com/travel/flights/search?tfs=%s&tfu=%s&hl=en&curr=USD",
		f.TFSParam(),
		f.TFUParam(),
	)
}
