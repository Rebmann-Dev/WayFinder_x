package flights

import (
	"encoding/hex"
	"strings"
	"testing"
)

// Golden tests for the tfs / tfu wire encoders.
//
// These tests pin the exact bytes produced for a known filter.  If any
// field number, tag, or ordering changes unintentionally, the scrape
// will silently return empty results because Google Flights rejects
// malformed payloads without an error — so the cheapest way to catch
// regressions is byte-level equality against captured references.
//
// When a test in this file fails, DO NOT blindly update the expected
// string.  First confirm the new encoding still yields results on a
// live scrape; if it does, the golden needs updating with a matching
// explanation in the commit message.

// mustFilter is a small helper to build a Filter in tests without
// having to error-check every call.
func mustFilter(t *testing.T, legs []FlightData, trip TripType, seat SeatClass, pax PassengerCount, stops MaxStops, maxPrice int32) *Filter {
	t.Helper()
	f, err := NewFilter(legs, trip, seat, pax, stops, maxPrice)
	if err != nil {
		t.Fatalf("NewFilter: %v", err)
	}
	return f
}

func TestEncodeTFS_OneWayJFKtoLAXSoloAdult(t *testing.T) {
	f := mustFilter(t,
		[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
		OneWay,
		Economy,
		PassengerCount{Adults: 1},
		AnyStops,
		0,
	)

	// Expected layout (see wire.go for field numbers):
	//
	//   10 02                                         trip=2 (one-way)
	//   1a 1e                                         flight_info, len 30
	//     12 0a 32 30 32 36 2d 30 35 2d 30 31         date="2026-05-01"
	//     6a 07 08 01 12 03 4a 46 4b                  dep: airport_type=1, iata="JFK"
	//     72 07 08 01 12 03 4c 41 58                  arr: airport_type=1, iata="LAX"
	//   40 01                                         passenger=adult
	const want = "10021a1e120a323032362d30352d30316a07080112034a464b7207080112034c41584001"

	got := hex.EncodeToString(encodeTFS(f))
	if got != want {
		t.Errorf("encodeTFS mismatch\n  want: %s\n   got: %s", want, got)
	}
}

func TestEncodeTFS_StopsAndPriceEmittedWhenSet(t *testing.T) {
	f := mustFilter(t,
		[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
		OneWay,
		Economy,
		PassengerCount{Adults: 1},
		Nonstop,
		500,
	)

	got := hex.EncodeToString(encodeTFS(f))

	// Nonstop is MaxStops(1) at field 9 → "4801"
	if !strings.Contains(got, "4801") {
		t.Errorf("expected stops field (48 01) in output: %s", got)
	}
	// maxPrice 500 is varint-encoded: 500 = 0xf4 0x03.  Field 12 tag
	// is (12<<3)|0 = 96 = 0x60 → expected fragment "60f403".
	if !strings.Contains(got, "60f403") {
		t.Errorf("expected max price field (60 f4 03) in output: %s", got)
	}
}

func TestEncodeTFS_OmitsAnyStopsAndZeroPrice(t *testing.T) {
	f := mustFilter(t,
		[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
		OneWay,
		Economy,
		PassengerCount{Adults: 1},
		AnyStops,
		0,
	)

	got := hex.EncodeToString(encodeTFS(f))

	// Field 9 (stops) tag is 0x48; must NOT appear when AnyStops.
	if strings.Contains(got, "48") {
		// 0x48 also happens to be ASCII 'H', so a date containing
		// that byte could false-positive — guard by checking the
		// stops sub-sequence "48 0?" instead.
		if strings.Contains(got, "4800") || strings.Contains(got, "4801") || strings.Contains(got, "4802") || strings.Contains(got, "4803") {
			t.Errorf("AnyStops should omit field 9, got: %s", got)
		}
	}
	// Field 12 (maxPrice) tag is 0x60; must NOT appear when price=0.
	if strings.Contains(got, "60") {
		// Same caveat — guard against coincidental byte matches.
		if strings.Contains(got, "60f4") || strings.Contains(got, "6001") || strings.Contains(got, "6002") {
			t.Errorf("Zero maxPrice should omit field 12, got: %s", got)
		}
	}
}

func TestEncodePassengers_EmitsOnePerHead(t *testing.T) {
	// 2 adults + 1 child + 1 infant in seat + 1 infant on lap.
	// Expected sequence at field 8 (tag 0x40):
	//   40 01 40 01   (two adults)
	//   40 02         (one child)
	//   40 03         (one infant in seat)
	//   40 04         (one infant on lap)
	// Total: 12 bytes.
	const want = "400140014002400340 04"
	got := hex.EncodeToString(encodePassengers(PassengerCount{
		Adults:        2,
		Children:      1,
		InfantsInSeat: 1,
		InfantsOnLap:  1,
	}))
	if got != strings.ReplaceAll(want, " ", "") {
		t.Errorf("encodePassengers mismatch\n  want: %s\n   got: %s",
			strings.ReplaceAll(want, " ", ""), got)
	}
}

func TestEncodeTFU_MatchesObservedPayload(t *testing.T) {
	// Byte-for-byte reproduction of the payload captured from a live
	// Google Flights search URL:
	//
	//   tfu=EgoIARABGAAgASgG
	//
	// decodes to:
	//
	//   12 0a 08 01 10 01 18 00 20 01 28 06
	const want = "120a08011001180020012806"

	got := hex.EncodeToString(encodeTFU())
	if got != want {
		t.Errorf("encodeTFU mismatch\n  want: %s\n   got: %s", want, got)
	}
}

func TestFilterURL_ContainsTFSAndTFU(t *testing.T) {
	f := mustFilter(t,
		[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
		OneWay,
		Economy,
		PassengerCount{Adults: 1},
		AnyStops,
		0,
	)

	url := f.URL()
	const tfuExpected = "tfu=EgoIARABGAAgASgG"
	if !strings.Contains(url, tfuExpected) {
		t.Errorf("URL missing expected tfu fragment %q: %s", tfuExpected, url)
	}
	if !strings.Contains(url, "hl=en") || !strings.Contains(url, "curr=USD") {
		t.Errorf("URL missing locale/currency params: %s", url)
	}
	if !strings.HasPrefix(url, "https://www.google.com/travel/flights/search?tfs=") {
		t.Errorf("URL does not start with expected search path: %s", url)
	}
}

func TestNewFilter_ValidatesInfants(t *testing.T) {
	tests := []struct {
		name    string
		pax     PassengerCount
		wantErr string
	}{
		{
			name:    "lap infant without adult",
			pax:     PassengerCount{Adults: 0, InfantsOnLap: 1},
			wantErr: "at least 1 adult",
		},
		{
			name:    "more lap infants than adults",
			pax:     PassengerCount{Adults: 1, InfantsOnLap: 2},
			wantErr: "lap infants",
		},
		{
			name:    "total exceeds 9 via infants",
			pax:     PassengerCount{Adults: 4, Children: 3, InfantsInSeat: 2, InfantsOnLap: 1},
			wantErr: "maximum of 9",
		},
		{
			name:    "negative count",
			pax:     PassengerCount{Adults: 1, Children: -1},
			wantErr: "non-negative",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := NewFilter(
				[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
				OneWay, Economy, tc.pax, AnyStops, 0,
			)
			if err == nil {
				t.Fatalf("expected error containing %q, got nil", tc.wantErr)
			}
			if !strings.Contains(err.Error(), tc.wantErr) {
				t.Errorf("expected error containing %q, got: %v", tc.wantErr, err)
			}
		})
	}
}

func TestNewFilter_AcceptsValidInfantMix(t *testing.T) {
	_, err := NewFilter(
		[]FlightData{{Date: "2026-05-01", FromAirport: "JFK", ToAirport: "LAX"}},
		OneWay, Economy,
		PassengerCount{Adults: 2, Children: 1, InfantsInSeat: 1, InfantsOnLap: 2},
		AnyStops, 0,
	)
	if err != nil {
		t.Errorf("expected valid infant mix to pass, got: %v", err)
	}
}
