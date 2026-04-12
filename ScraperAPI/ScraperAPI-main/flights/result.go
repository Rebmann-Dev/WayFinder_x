package flights

import "fmt"

// PriceLevel represents Google's assessment of the current price environment.
type PriceLevel string

const (
	PriceLow     PriceLevel = "low"
	PriceTypical PriceLevel = "typical"
	PriceHigh    PriceLevel = "high"
	PriceUnknown PriceLevel = "unknown"
)

// Result is the top-level response from GetFlights.
type Result struct {
	// CurrentPrice is Google's assessment of current price levels.
	CurrentPrice PriceLevel `json:"current_price"`

	// Flights is the list of scraped flight options.
	Flights []Flight `json:"flights"`
}

// String returns a multi-line, human-readable summary of the Result
// suitable for log output or debugging. Each flight is rendered using
// Flight.String on its own line. It satisfies fmt.Stringer.
func (r Result) String() string {
	out := fmt.Sprintf("Result{CurrentPrice: %s, Flights: [\n", r.CurrentPrice)
	for _, f := range r.Flights {
		out += "  " + f.String() + "\n"
	}
	out += "]}"
	return out
}
