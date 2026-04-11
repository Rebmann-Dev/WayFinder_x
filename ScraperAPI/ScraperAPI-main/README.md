# ScraperAPI

A Go HTTP service that scrapes Google Flights and returns structured
JSON flight results. Built as an internal component of the
[WayFinder](https://github.com/AI-WayFinder) AI travel assistant.

## What it does

ScraperAPI exposes a single REST endpoint that accepts a trip request
(origin, destination, date, passenger counts, seat class, stop
preferences, max price) and returns a normalized list of flight
options. Under the hood it:

1. Encodes the request into Google Flights' `tfs` query parameter
   (a base64url-wrapped protobuf payload).
2. Issues an HTTPS GET to `google.com/travel/flights/search` using a
   Chrome-mimicking HTTP client (uTLS fingerprint + Chrome headers)
   so the request isn't fingerprinted and blocked as a bot.
3. Parses the returned HTML with `goquery`, walking a set of CSS
   selectors to pull out airline, times, duration, stops, price,
   layover info, and CO2 emissions data.
4. Enriches results with structured airline and airport metadata from
   local CSV files (IATA/ICAO codes, city, country, etc.).
5. Returns a clean JSON response for upstream consumption.

## Role in WayFinder

WayFinder is an AI-powered travel assistant. When the assistant needs
live flight pricing and availability to answer a user's question
("find me the cheapest nonstop from JFK to LHR next Friday"),
it delegates the actual flight lookup to this service. ScraperAPI is
the flight-data provider behind the assistant's tool calls: the LLM
agent hands off structured trip parameters, ScraperAPI returns
structured flight options, and the agent synthesizes the answer.

This service intentionally contains no LLM logic, no user-facing UI,
and no persistence. It is a stateless scraper/parser with a stable
JSON interface.

## API

### `GET /flights/{from}/{to}`

Path parameters:

| Name   | Description                              |
| ------ | ---------------------------------------- |
| `from` | 3-letter IATA departure code (e.g. `JFK`) |
| `to`   | 3-letter IATA arrival code (e.g. `LAX`)   |

Query parameters:

| Name       | Required | Values                                          | Default   |
| ---------- | -------- | ----------------------------------------------- | --------- |
| `date`     | yes      | `YYYY-MM-DD`                                    | —         |
| `tripType` | no       | `oneway`, `roundtrip`                           | `oneway`  |
| `class`    | no       | `economy`, `premium-economy`, `business`, `first` | `economy` |
| `adults`   | no       | integer, >= 1                                   | `1`       |
| `children` | no       | integer, >= 0                                   | `0`       |
| `stops`    | no       | `any`, `nonstop`, `max1`, `max2`                | `any`     |
| `maxPrice` | no       | integer (USD)                                   | unlimited |

Total passengers (adults + children) must not exceed 9 — Google
Flights' own limit.

Example:

```sh
curl "http://localhost:8080/flights/JFK/LAX?date=2026-05-01&tripType=oneway&class=economy&adults=1&stops=nonstop"
```

### Response shape

```json
{
  "current_price": "typical",
  "flights": [
    {
      "is_top": true,
      "airline": { "name": "Delta", "iata": "DL", "icao": "DAL", "...": "..." },
      "departure": "8:00 AM",
      "arrival": "11:30 AM",
      "arrival_time_ahead": "",
      "duration": "5 hr 30 min",
      "stops": 0,
      "legs": [
        {
          "departure_airport": { "iata": "JFK", "...": "..." },
          "arrival_airport":   { "iata": "LAX", "...": "..." },
          "airline":           { "iata": "DL",  "...": "..." },
          "flight_number":     "DL 1234",
          "arrival_date":      "2026-05-01",
          "is_layover":        false,
          "layover_duration":  "",
          "order":             1
        }
      ],
      "price": "$342",
      "number": "",
      "emissions": {
        "current": 200,
        "typical": 220,
        "savings": 20,
        "percentage_diff": -9.1,
        "environmental_ranking": 2,
        "contrails_impact": 1,
        "travel_impact_url": "https://www.travelimpactmodel.org/lookup/flight?itinerary=..."
      }
    }
  ]
}
```

`current_price` is Google's own assessment of whether today's prices
are `low`, `typical`, `high`, or `unknown`.

### Errors

| Status | Cause                                           |
| ------ | ----------------------------------------------- |
| 400    | Missing/invalid path params or query params     |
| 500    | Scrape failed, Google returned non-200, or parse error |

All `/flights/...` requests are bounded by a 60-second timeout; if a
client disconnects mid-request the outbound scrape is cancelled.

## File structure

```
.
├── main.go                 # Entrypoint: loads CSV data, starts server
├── server/
│   ├── server.go           # http.Server lifecycle + graceful shutdown
│   ├── router.go           # gorilla/mux route table
│   └── middleware.go       # Request/response logging middleware
├── handlers/
│   ├── handler.go          # Handler struct
│   └── flight.go           # GET /flights/{from}/{to} handler + query parsing
├── flights/                # Core scraping/parsing package
│   ├── client.go           # HTTP client (uTLS Chrome fingerprint), fetchHTML
│   ├── body.go             # gzip/brotli decompression of responses
│   ├── filters.go          # Filter struct + NewFilter validation
│   ├── wire.go             # Protobuf wire-format encoder for the tfs param
│   ├── parser.go           # goquery-based HTML parser + CSS selectors
│   ├── flights.go          # Flight/Leg types, ParseTravelImpactURL
│   ├── result.go           # Result + PriceLevel types
│   ├── emissions.go        # Emissions struct
│   ├── airport.go          # Airport type, AIRPORTS map, ParseAirportCSV
│   ├── airline.go          # Airline type, AIRLINESBY* maps, ParseAirlineCSV
│   ├── data/               # Reference CSVs: airports.csv, airlines.csv
│   └── example/            # Usage example
├── Dockerfile
├── docker-compose.yml
├── go.mod / go.sum
└── LICENSE
```

## Architecture notes

### uTLS and the HTTP client

Google Flights blocks clients whose TLS fingerprint doesn't match a
real browser, so `flights/client.go` uses
[`refraction-networking/utls`](https://github.com/refraction-networking/utls)
to mimic Chrome's ClientHello. See the doc comment on `h1Conn` for why
we forcibly report `http/1.1` as the negotiated ALPN protocol.

The HTTP client is a package-level singleton so TCP/TLS connections
are pooled across requests.

### Reference data

`flights/data/airports.csv` and `flights/data/airlines.csv` are loaded
once at startup into the package-level maps `AIRPORTS`,
`AIRLINESBYCODE`, and `AIRLINESBYCALLSIGN`. These maps are treated as
immutable after startup — there is no lock on the read path. If you
add runtime reload (hot-refresh, background fetch), you must switch to
`sync.RWMutex` or `sync.Map` to avoid data races.

### CSS-selector fragility

`flights/parser.go` defines every selector as a top-of-file constant.
Google periodically reworks their HTML, and when they do, scraping
silently returns empty results. **These constants are the first thing
to audit when results stop appearing.** The file's header comment
lists each one with what it's meant to match.

### The `tfs` query parameter

Google Flights encodes the entire search filter (legs, trip type,
seat class, passenger counts, stop options, max price) as a
base64url-encoded protobuf payload passed in the `tfs` query string.
`flights/wire.go` implements the subset of the protobuf wire format
needed to encode this — no protoc, no generated code. The reference
schema is documented at the top of that file.

## Running locally

Requirements: Go 1.26+.

```sh
go run .
```

By default the server listens on port `8080`. Set `PORT` to override:

```sh
PORT=9000 go run .
```

## Running in Docker

```sh
docker compose up --build
```

The service will be available on `http://localhost:8080`.


## License

See [LICENSE](LICENSE).
