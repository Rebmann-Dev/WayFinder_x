package server

import (
	"net/http"

	"github.com/ai-wayfinder/scraperAPI/handlers"
	"github.com/gorilla/mux"
)

// SetupRouter builds the application's gorilla/mux router, installs the
// logging middleware chain, and registers every HTTP route the service
// exposes. It is the single place to look up the service's URL surface.
func SetupRouter() *mux.Router {
	r := mux.NewRouter()

	r.Use(
		LogRequest,
		LogResponseInfo,
	)

	h := handlers.New()

	r.Path("/flights/{from}/{to}").Methods(http.MethodGet).HandlerFunc(h.GetFlights)

	return r
}
