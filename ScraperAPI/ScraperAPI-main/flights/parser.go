package flights

import (
	"bytes"
	"fmt"
	"log"
	"regexp"
	"strconv"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

// ─── CSS selector constants ───────────────────────────────────────────────────
//
// These selectors were derived by inspecting the Google Flights HTML response.
// Google occasionally changes class names; if results become empty, these are
// the first thing to audit.
const (
	selFlightGroups = `div[role="tabpanel"]:not([style*="display: none"]) > div:not([role="region"])`

	// Outer container for every flight card (both "best" and regular).
	selFlightItem = `ul > li`

	// Airline name(s) within a card.
	selAirlineName = `div > div+div > div > div+div > div > div+div > div+div:not([aria-hidden=true]) > span:not([jsshadow])`

	// Flight duration.
	selDuration = `div > div > div > div > div > div+div+div > div[aria-label^="Total duration "]`

	// Stop count.
	selStops = `div > div > div > div > div > div+div+div > div > span[aria-label$=" flight."]`

	// Emissions info, e.g. "Emissions: 200 kg CO₂".
	selEmissions = `div > div > div > div > div > div+div+div+div+div > div[data-travelimpactmodelwebsiteurl]`

	// Price — the main displayed fare.
	selPrice = `div > div > div > div > div > div > div > div+div > span[role="text"]`

	// Current price level.
	selPriceLevel = `div > div > div > div > div > div+div > div > span`

	selTime = `span[data-position="1"] > span > span > span[aria-label^="%s time: "][role="text"]`
)

// div > div > div > div >  span[data-gs]
// stopsRe matches "Nonstop", "1 stop", "2 stops", etc.
var stopsRe = regexp.MustCompile(`(?i)(\d+)\s+stop|nonstop`)

// parseFlights parses a Google Flights HTML response body and returns a Result.
func parseFlights(html []byte) (*Result, error) {
	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		return nil, err
	}

	return extractData(doc), nil
}

// ─── data cards ─────────────────────────────────────────────────────────────
func extractData(doc *goquery.Document) *Result {

	result := Result{
		CurrentPrice: PriceUnknown,
		Flights:      []Flight{},
	}

	numGroups := 0
	smallest := 100000
	largest := -1

	var topFlights *goquery.Selection
	var otherFlights *goquery.Selection
	doc.Find(selFlightGroups).Each(func(_ int, group *goquery.Selection) {
		flights := group.Find(selFlightItem)

		if len(flights.Nodes) == 0 {
			priceGroup := group.Find(selPriceLevel).Text()

			switch strings.ToLower(priceGroup) {
			case "low":
				result.CurrentPrice = PriceLow
			case "typical", "typical price":
				result.CurrentPrice = PriceTypical
			case "high":
				result.CurrentPrice = PriceHigh
			}
		} else {
			if len(flights.Nodes) < smallest {
				smallest = len(flights.Nodes)
				topFlights = flights
			}
			if len(flights.Nodes) > largest {
				largest = len(flights.Nodes)
				otherFlights = flights
			}
			numGroups++
		}
	})

	if otherFlights != nil {
		otherFlights.Each(func(_ int, s *goquery.Selection) {
			flight := extractFlightData(s)
			if flight != nil {
				flight.IsTop = false

				result.Flights = append(result.Flights, *flight)
			}

		})
	}

	if numGroups > 1 && topFlights != nil {
		topFlights.Each(func(_ int, s *goquery.Selection) {
			flight := extractFlightData(s)
			if flight != nil {
				flight.IsTop = true

				result.Flights = append(result.Flights, *flight)
			}
		})
	}

	return &result
}

func extractFlightData(s *goquery.Selection) *Flight {
	airline := extractAirlineName(s)
	if airline.Name == "" || airline.Name == "Unknown" {
		return nil
	}
	flight := Flight{
		Airline:   airline,
		Price:     extractPrice(s),
		Duration:  extractDuration(s),
		Emissions: extractEmissions(s),
	}

	flight.ParseTravelImpactURL()
	flight.extractStopsData(s)

	flight.Departure, flight.Arrival, flight.ArrivalTimeAhead = extractTimes(s)

	return &flight
}

func (f *Flight) extractStopsData(s *goquery.Selection) {
	node := s.Find(selStops)

	text := strings.ToLower(strings.TrimSpace(node.Text()))

	if text == "nonstop" {
		f.Stops = 0
		return
	}
	if text == "" {
		return
	}

	parentNode := node.Parent()
	siblingNode := parentNode.Siblings()
	layoverData, _ := siblingNode.First().Attr("aria-label")

	var i int
	for lo := range strings.SplitSeq(layoverData, ".") {
		if lo == "" {
			continue
		}
		re := regexp.MustCompile(`\b((?:\d+\s*hr(?:\s+\d+\s*min)?)|(?:\d+\s*min))\b`)
		duration := re.FindString(lo)

		if i >= len(f.Legs) {
			break
		}

		f.Legs[i].LayoverDuration = duration

		i++
	}

	// Use the stopsRe regex to robustly extract the stop count.  Avoid
	// slicing text[:1] directly, since a non-numeric or multi-digit prefix
	// (e.g. "10 stops") would either panic or silently produce the wrong
	// value.
	if m := stopsRe.FindStringSubmatch(text); len(m) >= 2 && m[1] != "" {
		if n, err := strconv.Atoi(m[1]); err == nil {
			f.Stops = n
		}
	}
}

func extractAirlineName(s *goquery.Selection) Airline {
	names := s.Find(selAirlineName)
	parts := make([]string, 0, names.Length())
	names.Each(func(_ int, n *goquery.Selection) {
		if t := strings.TrimSpace(n.Text()); t != "" && t != "Bags filter" {
			parts = append(parts, t)
		}
	})

	if len(parts) == 0 {
		return Airline{Name: "Unknown"}
	}

	airline, ok := AIRLINESBYCALLSIGN[strings.ToLower(parts[0])]

	if !ok || airline == nil {
		return Airline{Name: parts[0]}
	}

	return *airline
}

func extractTimes(s *goquery.Selection) (departure, arrival, ahead string) {
	// Google renders departure + arrival as two adjacent spans inside a
	// common container.  We grab all aria-label'd time spans.
	departure = s.Find(fmt.Sprintf(selTime, "Departure")).Text()
	arrival = s.Find(fmt.Sprintf(selTime, "Arrival")).Text()

	arrival = strings.Replace(arrival, "+1", "", -1)

	ahead = s.Find(fmt.Sprintf(selTime, "Arrival") + `> span`).Text()

	return
}

func extractDuration(s *goquery.Selection) string {
	return strings.TrimSpace(s.Find(selDuration).First().Text())
}

func extractPrice(s *goquery.Selection) string {
	p := strings.TrimSpace(s.Find(selPrice).First().Text())

	return p
}

// parseEmissionInt parses an integer emission attribute, logging malformed
// values so silent upstream format changes don't go unnoticed.
func parseEmissionInt(attr, raw string) int {
	n, err := strconv.Atoi(raw)
	if err != nil {
		log.Printf("flights: emissions %s: could not parse %q as int: %v", attr, raw, err)
		return 0
	}
	return n
}

func extractEmissions(s *goquery.Selection) Emissions {
	flightEmissions := Emissions{}

	emissions := s.Find(selEmissions).First()

	// Extract emission data from attributes
	if current, ok := emissions.Attr("data-co2currentflight"); ok {
		flightEmissions.Current = parseEmissionInt("data-co2currentflight", current)
	}

	if typical, ok := emissions.Attr("data-co2typical"); ok {
		flightEmissions.Typical = parseEmissionInt("data-co2typical", typical)
	}

	if savings, ok := emissions.Attr("data-co2savings"); ok {
		flightEmissions.Savings = parseEmissionInt("data-co2savings", savings)
	}

	if percentageDiff, ok := emissions.Attr("data-percentagediff"); ok {
		diff, err := strconv.ParseFloat(percentageDiff, 32)
		if err != nil {
			log.Printf("flights: emissions data-percentagediff: could not parse %q as float: %v", percentageDiff, err)
		} else {
			flightEmissions.PercentageDiff = float32(diff)
		}
	}

	if environmentalRanking, ok := emissions.Attr("data-environmentalranking"); ok {
		flightEmissions.EnvironmentalRanking = parseEmissionInt("data-environmentalranking", environmentalRanking)
	}

	if contrailsImpact, ok := emissions.Attr("data-contrailsimpact"); ok {
		flightEmissions.ContrailsImpact = parseEmissionInt("data-contrailsimpact", contrailsImpact)
	}

	flightEmissions.TravelImpactURL, _ = emissions.Attr("data-travelimpactmodelwebsiteurl")

	return flightEmissions
}
