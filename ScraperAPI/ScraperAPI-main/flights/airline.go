package flights

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strings"
)

type Airline struct {
	Name       string `json:"name"`
	OperatedBy string `json:"operated_by"`
	Code       string `json:"code"`
	Country    string `json:"country"`
	Callsign   string `json:"callsign"`
}

type Airlines map[string]*Airline

// AIRLINESBYCODE and AIRLINESBYCALLSIGN are package-level lookup tables
// populated from airlines.csv during startup.
//
// Concurrency invariant: both maps must be fully populated by
// ParseAirlineCSV() before any HTTP handler begins serving, and must NEVER
// be mutated afterwards.  Readers hold no lock — once the write phase is
// done, the maps are treated as immutable.  If a future change introduces
// runtime refresh, switch to sync.RWMutex or sync.Map to avoid data races.
var (
	AIRLINESBYCODE     = make(Airlines, 10000)
	AIRLINESBYCALLSIGN = make(Airlines, 10000)
)

// ParseAirlineCSV loads flights/data/airlines.csv into the package-level
// AIRLINESBYCODE and AIRLINESBYCALLSIGN lookup tables. It must be called
// exactly once during process startup, before any HTTP handler begins
// serving, because the maps are treated as immutable afterwards (see the
// concurrency invariant documented on AIRLINESBYCODE).
func ParseAirlineCSV() error {
	f, err := os.Open("./flights/data/airlines.csv")
	if err != nil {
		return fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1 // allow flexible field counts if needed

	expected := []string{
		"AirportID",
		"Name",
		"Alias",
		"IATA",
		"ICAO",
		"Callsign",
		"Country",
		"Active",
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

		airline := Airline{
			Name:     strings.TrimSpace(record[1]),
			Code:     strings.TrimSpace(record[3]),
			Callsign: strings.ToLower(strings.TrimSpace(record[5])),
			Country:  strings.TrimSpace(record[6]),
		}
		if airline.Code == "" {
			if strings.TrimSpace(record[4]) == "" {
				continue
			}

			airline.Code = strings.TrimSpace(record[4])
		}

		AIRLINESBYCODE[strings.ToUpper(airline.Code)] = &airline
		AIRLINESBYCALLSIGN[airline.Callsign] = &airline
	}

	return nil
}
