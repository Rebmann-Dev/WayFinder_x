package flights

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
)

type Airport struct {
	Name       string `json:"name"`
	Code       string `json:"code"`
	TimeZoneID string `json:"time_zone_id"`
	CityCode   string `json:"city_code"`
	CountryID  string `json:"country_id"`
	Location   string `json:"location"`
	Elevation  *int   `json:"elevation,omitempty"`
	URL        string `json:"url"`
	ICAO       string `json:"icao"`
	City       string `json:"city"`
	County     string `json:"county"`
	State      string `json:"state"`
}

type Airports map[string]*Airport

// AIRPORTS is a package-level lookup table keyed by IATA code.
//
// Concurrency invariant: AIRPORTS must be fully populated by
// ParseAirportCSV() during startup (before any HTTP handler begins serving),
// and must NEVER be mutated afterwards.  Readers intentionally hold no lock
// — once the write phase is done, the map is treated as immutable.  If a
// future change introduces runtime refresh (hot-reload, background fetch,
// etc.), switch to sync.RWMutex or sync.Map to avoid data races.
var AIRPORTS = make(Airports, 10000)

// ParseAirportCSV loads flights/data/airports.csv into the package-level
// AIRPORTS lookup table keyed by IATA code. It must be called exactly
// once during process startup, before any HTTP handler begins serving,
// because the map is treated as immutable afterwards (see the concurrency
// invariant documented on AIRPORTS).
func ParseAirportCSV() error {
	f, err := os.Open("./flights/data/airports.csv")
	if err != nil {
		return fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1 // allow flexible field counts if needed

	expected := []string{
		"code",
		"time_zone_id",
		"name",
		"city_code",
		"country_id",
		"location",
		"elevation",
		"url",
		"icao",
		"city",
		"county",
		"state",
	}

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("read record: %w", err)
		}

		if len(record) < len(expected) {
			return fmt.Errorf("invalid record length: got %d fields, want %d", len(record), len(expected))
		}

		var elevation *int
		val, err := strconv.Atoi(strings.TrimSpace(record[6]))
		if err != nil {
			return fmt.Errorf("parse elevation %q: %w", record[6], err)
		}
		if record[6] != "" {
			elevation = &val
		}

		airport := Airport{
			Code:       strings.TrimSpace(record[0]),
			TimeZoneID: strings.TrimSpace(record[1]),
			Name:       strings.TrimSpace(record[2]),
			CityCode:   strings.TrimSpace(record[3]),
			CountryID:  strings.TrimSpace(record[4]),
			Location:   strings.TrimSpace(record[5]),
			Elevation:  elevation,
			URL:        strings.TrimSpace(record[7]),
			ICAO:       strings.TrimSpace(record[8]),
			City:       strings.TrimSpace(record[9]),
			County:     strings.TrimSpace(record[10]),
			State:      strings.TrimSpace(record[11]),
		}

		AIRPORTS[airport.Code] = &airport
	}

	return nil
}
