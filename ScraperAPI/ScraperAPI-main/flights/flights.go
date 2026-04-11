package flights

import (
	"fmt"
	"strings"
)

// Flight represents a single flight result scraped from Google Flights.
type Flight struct {
	// IsBest is true when Google marks this result as a "best" flight.
	IsTop bool `json:"is_top"`

	// Name is the airline name(s), e.g. "Delta", "Delta · United".
	Airline Airline `json:"airline"`

	// Departure is the departure time, e.g. "8:00 AM".
	Departure string `json:"departure"`

	// Arrival is the arrival time, e.g. "11:30 AM".
	Arrival string `json:"arrival"`

	// ArrivalTimeAhead is non-empty when the flight lands the next day or
	// later, e.g. "+1" means the next calendar day.
	ArrivalTimeAhead string `json:"arrival_time_ahead"`

	// Duration is the total flight time, e.g. "5 hr 30 min".
	Duration string `json:"duration"`

	// Stops is 0 for nonstop, 1 for one stop, etc.
	Stops int `json:"stops"`

	Legs []Leg `json:"legs,omitempty"`

	// Delay is non-nil when Google reports a typical delay for this flight,
	// e.g. "Often delayed by 30+ min".
	Delay *string `json:"delay,omitempty"`

	// Price is the fare as a formatted string, e.g. "$342".
	Price string `json:"price"`

	// Number is the flight number, e.g. "DL 1234".
	Number string `json:"number"`

	// Emissions data
	Emissions Emissions `json:"emissions"`
}

type Leg struct {
	DepartureAirport *Airport `json:"departure_airport"`
	ArrivalAirport   *Airport `json:"arrival_airport"`

	Airline *Airline `json:"airline"`

	FlightNumber string `json:"flight_number"`
	ArrivalDate  string `json:"arrival_date"`

	IsLayover       bool   `json:"is_layover"`
	LayoverDuration string `json:"layover_duration,omitempty"`

	Order int `json:"order"`
}

// String returns a single-line, human-readable summary of the Flight
// suitable for log output or debugging. It includes the airline, a
// "[top]" marker when IsTop is true, the departure/arrival times, the
// total duration, the stop count, and the price. It satisfies
// fmt.Stringer.
func (f Flight) String() string {
	stops := "nonstop"
	if f.Stops == 1 {
		stops = "1 stop"
	} else if f.Stops > 1 {
		stops = fmt.Sprintf("%d stops", f.Stops)
	}

	best := ""
	if f.IsTop {
		best = " [top]"
	}

	return fmt.Sprintf("%s%s | %s → %s%s | %s | %s | %s",
		f.Airline.Name+" · "+f.Airline.OperatedBy, best,
		f.Departure, f.Arrival, f.ArrivalTimeAhead,
		f.Duration, stops, f.Price,
	)
}

// ParseTravelImpactURL populates f.Legs by parsing the itinerary segment of
// the travel-impact URL.  It is a best-effort enrichment step: malformed or
// missing segments are skipped silently so a partial URL still yields the
// legs it can.
func (f *Flight) ParseTravelImpactURL() {
	if f.Emissions.TravelImpactURL == "" {
		return
	}

	itinerary := strings.Replace(f.Emissions.TravelImpactURL, "https://www.travelimpactmodel.org/lookup/flight?itinerary=", "", 1)

	itineraryArr := strings.Split(itinerary, ",")

	for i, part := range itineraryArr {
		legArr := strings.Split(part, "-")
		if len(legArr) < 5 {
			continue
		}

		// The date segment is expected in YYYYMMDD format (8 chars).  Guard
		// against upstream format changes that would otherwise panic with
		// an out-of-range slice.
		arrivalDate := legArr[4]
		if len(arrivalDate) >= 8 {
			arrivalDate = fmt.Sprintf("%s-%s-%s", arrivalDate[:4], arrivalDate[4:6], arrivalDate[6:8])
		}

		leg := Leg{
			DepartureAirport: AIRPORTS[legArr[0]],
			ArrivalAirport:   AIRPORTS[legArr[1]],
			Airline:          AIRLINESBYCODE[strings.ToUpper(legArr[2])],
			FlightNumber:     fmt.Sprintf("%s %s", legArr[2], legArr[3]),
			ArrivalDate:      arrivalDate,
			Order:            i + 1,
		}

		if leg.Order < len(itineraryArr) {
			leg.IsLayover = true
		}

		f.Legs = append(f.Legs, leg)
	}
}
