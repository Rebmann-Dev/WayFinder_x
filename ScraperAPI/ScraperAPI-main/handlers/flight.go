package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/ai-wayfinder/scraperAPI/flights"
	"github.com/gorilla/mux"
)

const (
	FlightDate = "date"
	FlightFrom = "from"
	FlightTo   = "to"

	// flightRequestTimeout bounds the total time a single /flights request
	// may spend scraping.  If the client disconnects before completion,
	// ctx is cancelled and the outbound HTTP call aborts.
	flightRequestTimeout = 60 * time.Second
)

// iataRe validates 3-letter IATA airport codes at the handler boundary so
// unvalidated path segments cannot be spliced into the outbound scrape URL.
var iataRe = regexp.MustCompile(`^[A-Z]{3}$`)

// GetFlights handles GET /flights/{from}/{to}. It validates the IATA path
// parameters, parses the supported query-string filters (date, tripType,
// class, adults, children, stops, maxPrice) into a flights.Filter, performs
// the scrape via flights.GetFlights, and writes the normalized result as
// JSON. The request is bounded by flightRequestTimeout so a disconnected
// client cancels the outbound scrape.
func (h *Handler) GetFlights(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), flightRequestTimeout)
	defer cancel()

	vars := mux.Vars(r)

	from := strings.ToUpper(vars[FlightFrom])
	to := strings.ToUpper(vars[FlightTo])

	if !iataRe.MatchString(from) || !iataRe.MatchString(to) {
		w.WriteHeader(http.StatusBadRequest)
		fmt.Fprint(w, "Invalid airport code: must be a 3-letter IATA code")
		return
	}

	f, err := buildFlightsFilter(r.URL.Query(), from, to)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		fmt.Fprintf(w, "Invalid query parameters: %v", err)
		return
	}

	result, err := flights.GetFlights(ctx, f)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, "Unable to search flights: %v", err)
		return
	}

	jsonStr, err := json.Marshal(result)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, "Unable to marshal json response: %v", err)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write(jsonStr)
}

func buildFlightsFilter(vals url.Values, from, to string) (*flights.Filter, error) {
	date := vals.Get(FlightDate)
	if date == "" {
		return nil, fmt.Errorf("missing date query parameter")
	}

	tripQuery := vals.Get("tripType")
	trip := flights.OneWay
	if tripQuery != "" {
		switch tripQuery {
		case "oneway":
			trip = flights.OneWay
		case "roundtrip":
			trip = flights.RoundTrip
		}
	}

	classQuery := vals.Get("class")
	class := flights.Economy
	if classQuery != "" {
		switch classQuery {
		case "economy":
			class = flights.Economy
		case "premium-economy":
			class = flights.PremiumEconomy
		case "business":
			class = flights.Business
		case "first":
			class = flights.First
		}
	}

	passengerCount := flights.PassengerCount{
		Adults:   1,
		Children: 0,
	}
	numAdults := vals.Get("adults")
	if numAdults != "" {
		n, err := strconv.Atoi(numAdults)
		if err != nil {
			return nil, fmt.Errorf("invalid number of adults query parameter")
		}
		passengerCount.Adults = n
	}

	numChildren := vals.Get("children")
	if numChildren != "" {
		n, err := strconv.Atoi(numChildren)
		if err != nil {
			return nil, fmt.Errorf("invalid number of children query parameter")
		}
		passengerCount.Children = n
	}

	numInfantsInSeat := vals.Get("infantsInSeat")
	if numInfantsInSeat != "" {
		n, err := strconv.Atoi(numInfantsInSeat)
		if err != nil {
			return nil, fmt.Errorf("invalid number of infantsInSeat query parameter")
		}
		passengerCount.InfantsInSeat = n
	}

	numInfantsOnLap := vals.Get("infantsOnLap")
	if numInfantsOnLap != "" {
		n, err := strconv.Atoi(numInfantsOnLap)
		if err != nil {
			return nil, fmt.Errorf("invalid number of infantsOnLap query parameter")
		}
		passengerCount.InfantsOnLap = n
	}

	stopsQuery := vals.Get("stops")
	stops := flights.AnyStops
	if stopsQuery != "" {
		switch stopsQuery {
		case "any":
			stops = flights.AnyStops
		case "nonstop":
			stops = flights.Nonstop
		case "max1":
			stops = flights.MaxOneStop
		case "max2":
			stops = flights.MaxTwoStops
		}
	}

	maxPrice := vals.Get("maxPrice")
	var maxPriceInt int32
	if maxPrice != "" {
		n, err := strconv.Atoi(maxPrice)
		if err != nil {
			return nil, fmt.Errorf("invalid max price query parameter")
		}
		maxPriceInt = int32(n)
	}

	f, err := flights.NewFilter(
		[]flights.FlightData{
			{Date: date, FromAirport: from, ToAirport: to},
		},
		trip,
		class,
		passengerCount,
		stops,
		maxPriceInt,
	)

	return f, err
}
