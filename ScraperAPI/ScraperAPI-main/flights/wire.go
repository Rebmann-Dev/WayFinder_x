package flights

// wire.go implements the subset of the protobuf binary wire format needed
// to encode the Google Flights `tfs` search parameter and the `tfu`
// view-state parameter.  These two parameters together define the full
// state of a Google Flights search URL.
//
// We only need two protobuf wire types:
//
//	0  varint  — int32 scalar fields (trip, seat, stop counts, passenger codes)
//	2  LEN     — length-delimited (strings and embedded messages)
//
// Full wire-format spec: https://protobuf.dev/programming-guides/encoding/
//
// ─── The tfs (search) payload ────────────────────────────────────────────
//
// Reverse-engineered from real Chrome DevTools captures.  Field numbers
// below describe what encodeTFS actually writes — this block is the
// single source of truth for the layout:
//
//	message Airport {
//	    int32  airport_type = 1;   // 1 = airport, 2 = city; always 1 here
//	    string iata         = 2;
//	}
//
//	message FlightInfo {
//	    string  date             = 2;
//	    Airport departure_airport = 13;
//	    Airport arrival_airport   = 14;
//	}
//
//	message FlightPayload {
//	    int32              trip_type    =  2;  // 1 = round-trip, 2 = one-way
//	    repeated FlightInfo legs        =  3;
//	    repeated int32      passengers  =  8;  // 1=adult 2=child 3=inf_seat 4=inf_lap
//	    int32              max_stops    =  9;  // 1=nonstop 2=max1 3=max2
//	    int32              max_price    = 12;
//	    // NOTE: seat class is NOT encoded yet — see encodeTFS doc comment.
//	}
//
// ─── The tfu (view state) payload ────────────────────────────────────────
//
// Reverse-engineered from a live Google Flights URL.  The outer message
// has a single LEN-delimited sub-message at field 2 holding five varint
// knobs whose individual meanings are not yet mapped.  encodeTFU
// reproduces the exact payload observed on real search URLs; until we
// understand each knob it is treated as an opaque constant.

// ─── Wire-type constants ──────────────────────────────────────────────────────

const (
	wireVarint = 0
	wireLen    = 2
)

// ─── Primitive encoders ───────────────────────────────────────────────────────

// appendVarint encodes v as a base-128 (LEB128) varint and appends it to b.
func appendVarint(b []byte, v uint64) []byte {
	for v >= 0x80 {
		b = append(b, byte(v)|0x80)
		v >>= 7
	}
	return append(b, byte(v))
}

// appendTag encodes the field tag (field number + wire type) as a varint.
func appendTag(b []byte, fieldNum int, wireType int) []byte {
	return appendVarint(b, uint64(fieldNum<<3|wireType))
}

// appendString encodes a protobuf string field:
//
//	tag (LEN) | varint(len) | bytes
func appendString(b []byte, fieldNum int, s string) []byte {
	b = appendTag(b, fieldNum, wireLen)
	b = appendVarint(b, uint64(len(s)))
	return append(b, s...)
}

// appendInt32 encodes a protobuf int32 field as a varint:
//
//	tag (varint) | varint(v)
//
// Zero values are omitted, mirroring proto3 default-field elision.  Use
// appendVarintField when you need to force-emit a zero (e.g. reproducing
// an observed tfu payload where a zero field is actually present on the
// wire).
func appendInt32(b []byte, fieldNum int, v int32) []byte {
	if v == 0 {
		return b
	}
	return appendVarintField(b, fieldNum, uint64(v))
}

// appendVarintField writes a varint field unconditionally, including
// zero values.  Needed when replicating captured payloads where the
// server expects the field to be present even when its value is 0.
func appendVarintField(b []byte, fieldNum int, v uint64) []byte {
	b = appendTag(b, fieldNum, wireVarint)
	return appendVarint(b, v)
}

// appendMessage encodes a nested message field:
//
//	tag (LEN) | varint(len(msg)) | msg
func appendMessage(b []byte, fieldNum int, msg []byte) []byte {
	if len(msg) == 0 {
		return b
	}
	b = appendTag(b, fieldNum, wireLen)
	b = appendVarint(b, uint64(len(msg)))
	return append(b, msg...)
}

// ─── Message encoders ─────────────────────────────────────────────────────────

// Airport type discriminators observed on the Google Flights wire:
// 1 = specific airport (IATA code), 2 = metropolitan area / city code.
// All queries originated from this service use specific airports, so
// encodeAirport pins the value to 1.  Omitting the field entirely causes
// Google to return empty results.
const airportTypeAirport = 1

// encodeAirport encodes an Airport sub-message.
//
//	message Airport {
//	    int32  airport_type = 1;  // 1 = airport, 2 = city
//	    string iata         = 2;
//	}
func encodeAirport(iata string) []byte {
	var b []byte
	b = appendInt32(b, 1, airportTypeAirport)
	b = appendString(b, 2, iata)
	return b
}

// encodeFlightInfo encodes one FlightInfo leg.
//
//	message FlightInfo {
//	    string  date        = 2;
//	    Airport dep_airport = 13;
//	    Airport arr_airport = 14;
//	}
func encodeFlightInfo(leg flightLeg) []byte {
	var b []byte
	b = appendString(b, 2, leg.date)
	b = appendMessage(b, 13, encodeAirport(leg.from))
	b = appendMessage(b, 14, encodeAirport(leg.to))
	return b
}

// Passenger type codes written into the repeated passengers field
// (field 8 of FlightPayload).  Each passenger produces one (tag, varint)
// pair — Google Flights uses unpacked encoding here, so N adults emit N
// separate `field 8 = 1` entries rather than a single packed slice.
const (
	paxAdult       = 1
	paxChild       = 2
	paxInfantSeat  = 3
	paxInfantOnLap = 4
)

// encodePassengers appends the repeated passenger codes that describe
// the party to b.  Passengers are written at field 8 of the enclosing
// FlightPayload message; this function does not wrap the output in any
// sub-message of its own.
func encodePassengers(pax PassengerCount) []byte {
	var b []byte

	for range pax.Adults {
		b = appendInt32(b, 8, paxAdult)
	}
	for range pax.Children {
		b = appendInt32(b, 8, paxChild)
	}
	for range pax.InfantsInSeat {
		b = appendInt32(b, 8, paxInfantSeat)
	}
	for range pax.InfantsOnLap {
		b = appendInt32(b, 8, paxInfantOnLap)
	}

	return b
}

// encodeTFS encodes the top-level FlightPayload message.  See the
// package-level wire.go comment for the full field layout — this
// function is the source of truth for which fields are actually written.
//
// Known gap: seat class (f.seat) is NOT currently encoded.  The field
// number is reverse-engineered to be 19 but that has not been verified
// against a live capture.  Until then, searches always run as economy
// regardless of f.seat.  See the review notes in the repo issue tracker.
func encodeTFS(f *Filter) []byte {
	var b []byte

	// field 2: trip type (1 = round-trip, 2 = one-way)
	b = appendInt32(b, 2, int32(f.trip))

	// field 3: repeated FlightInfo legs
	for _, leg := range f.legs {
		b = appendMessage(b, 3, encodeFlightInfo(leg))
	}

	// field 8: repeated passenger type codes (1=adult, 2=child,
	// 3=infant in seat, 4=infant on lap).  Unpacked — one entry per head.
	b = append(b, encodePassengers(f.pax)...)

	// field 9: max stops (omitted when AnyStops so Google applies no filter)
	if f.stops != AnyStops {
		b = appendInt32(b, 9, int32(f.stops))
	}

	// field 12: max price in USD (omitted when 0 = no cap)
	if f.price > 0 {
		b = appendInt32(b, 12, int32(f.price))
	}

	return b
}

// ─── tfu (view state) encoder ────────────────────────────────────────────────

// encodeTFU encodes the view-state payload Google Flights expects on the
// &tfu= query parameter.  The outer message contains a single
// LEN-delimited sub-message at field 2 holding five varint knobs that
// control UI state (selected tab, sort order, etc.).  The individual
// semantics are not yet mapped; the constants below reproduce exactly
// the bytes observed on a live search URL:
//
//	12 0a 08 01 10 01 18 00 20 01 28 06
//
// which base64url-encodes to "EgoIARABGAAgASgG".  When each knob is
// understood, replace the magic numbers with named parameters derived
// from the Filter (e.g. sort order, fare type).
func encodeTFU() []byte {
	var inner []byte
	// appendInt32 elides zero, so use appendVarintField where we need
	// to emit a zero field (field 3 below).
	inner = appendVarintField(inner, 1, 1)
	inner = appendVarintField(inner, 2, 1)
	inner = appendVarintField(inner, 3, 0)
	inner = appendVarintField(inner, 4, 1)
	inner = appendVarintField(inner, 5, 6)

	var b []byte
	b = appendMessage(b, 2, inner)
	return b
}
