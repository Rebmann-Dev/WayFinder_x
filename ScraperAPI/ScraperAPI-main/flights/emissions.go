package flights

type Emissions struct {
	Current        int     `json:"current"`
	Typical        int     `json:"typical"`
	Savings        int     `json:"savings"`
	PercentageDiff float32 `json:"percentage_diff"`

	EnvironmentalRanking int `json:"environmental_ranking"`
	ContrailsImpact      int `json:"contrails_impact"`

	TravelImpactURL string `json:"travel_impact_url"`
}
