import csv
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AirportRow:
    code: str
    name: str
    city: str
    county: str
    state: str
    city_code: str
    timezone: str
    country_id: str


def _default_csv_path() -> Path:
    env = os.getenv("AIRPORTS_CSV")
    if env:
        return Path(env)
    # WayFinder/app/services -> parents[2] = WayFinder
    wayfinder_root = Path(__file__).resolve().parents[2]
    return wayfinder_root.parent / "ScraperAPI" / "flights" / "data" / "airports.csv"


@lru_cache(maxsize=1)
def _load_airports() -> list[AirportRow]:
    path = _default_csv_path()
    if not path.is_file():
        return []
    rows: list[AirportRow] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for record in reader:
            if len(record) < 12:
                continue
            code = record[0].strip().upper()
            timezone = record[1].strip()
            name = record[2].strip()
            city_code = record[3].strip()
            country = record[4].strip()
            city = record[9].strip()
            county = record[10].strip()
            state = record[11].strip() if len(record) > 11 else ""
            if len(code) != 3:
                continue
            rows.append(
                AirportRow(
                    code=code,
                    name=name,
                    city=city,
                    county=county,
                    state=state,
                    city_code=city_code,
                    timezone=timezone,
                    country_id=country,
                )
            )
    return rows


def search_airports(query: str, limit: int = 12) -> list[dict[str, str]]:
    """Case-insensitive substring match over code, name, city, country."""
    q = query.strip().lower()
    if not q:
        return []
    lim = max(1, min(limit, 30))
    all_rows = _load_airports()
    metro_codes = {
        row.city_code
        for row in all_rows
        if row.city and row.city.lower() == q and row.city_code
    }
    scored: list[tuple[int, AirportRow]] = []
    for row in all_rows:
        hay = f"{row.code} {row.name} {row.city} {row.county} {row.state} {row.country_id}".lower()
        metro_match = bool(metro_codes and row.city_code in metro_codes)
        if q not in hay and not metro_match:
            continue
        is_intl = "international" in row.name.lower()
        name_has_q = q in row.name.lower()
        city_exact = row.city.lower() == q
        if row.code.lower() == q:
            priority = 10
        elif metro_match and is_intl:
            priority = 9
        elif metro_match:
            priority = 7
        elif city_exact and is_intl:
            priority = 8
        elif name_has_q and is_intl:
            priority = 6
        elif city_exact:
            priority = 5
        elif name_has_q:
            priority = 4
        elif row.city.lower().startswith(q):
            priority = 3 if is_intl else 2
        elif row.county.lower().startswith(q):
            priority = 1
        else:
            priority = 0
        scored.append((priority, row))
    scored.sort(key=lambda x: (-x[0], x[1].code))
    out: list[dict[str, str]] = []
    for _, row in scored[:lim]:
        display_city = row.city or row.county
        out.append(
            {
                "iata": row.code,
                "name": row.name,
                "city": display_city,
                "country": row.country_id,
            }
        )
    return out
