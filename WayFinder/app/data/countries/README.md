# Country JSON Files

Structured travel data for WayFinder country profiles.

## Schema Structure

Each country JSON file follows a consistent schema with these top-level sections:

| Section | Description |
|---|---|
| `meta` | Last updated date, confidence score, sources |
| `identity` | Country name, ISO codes, capital, flag, timezones |
| `language_and_money` | Languages, currency, payment methods, tipping |
| `entry_and_border` | Visa requirements, passport rules, customs |
| `health` | Vaccines, disease risks, medical care, water safety |
| `safety` | Travel advisories, crime, scams, emergency numbers |
| `weather_and_seasonality` | Climate zones, seasons, best times to visit |
| `transport` | Airports, buses, ride-hailing, road conditions |
| `budget` | Daily costs for backpacker, midrange, comfort |
| `connectivity` | SIM cards, wifi, power outlets, remote work |
| `accommodation` | Best areas, surf towns, eco-lodges |
| `culture` | Customs, holidays, photography etiquette |
| `food` | Signature dishes, street food, regional specialties |
| `outdoors` | National parks, hikes, surf spots, wildlife zones |
| `sports_and_activities` | Surfing, trekking, rafting, birdwatching |
| `trip_styles` | Backpacking, luxury, family, solo, digital nomad |
| `destinations` | Top cities, towns, regions, sample itineraries |
| `practical_info` | Arrival tips, useful apps, helpful phrases |
| `laws` | Drug laws, drone rules, camping, LGBTQ+ status |
| `family_travel` | Kid-friendly activities, car seat rules |
| `accessibility` | Wheelchair access, accessible transport |
| `gear` | What to bring, gear rental, outdoor shops |

## Adding a New Country

1. Copy the schema template from `/home/user/workspace/country_json_spec.md`
2. Name the file `{country_name_lowercase}.json` (e.g., `colombia.json`)
3. Fill every field you can with accurate, verifiable data
4. Set fields you cannot verify to `null` — do NOT guess
5. Be especially careful with visa rules, vaccine requirements, and safety advisories
6. Surf spots, hikes, and wildlife zones must be real places with accurate information
7. Pull any existing data from `WayFinder/app/ui/chat_page.py` and `WayFinder/app/models/safety/submodels/`

## Null Fields

Fields set to `null` are candidates for enrichment via Tavily web search. The enrichment pipeline will attempt to fill these with verified data from web sources.

## Last Updated

- Ecuador: 2026-04-12
- Peru: 2026-04-12
