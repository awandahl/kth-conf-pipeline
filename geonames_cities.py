# conf/geonames_cities.py
import csv
from pathlib import Path
import pycountry  # pip install pycountry

# Build ISO alpha-2 → country name mapping at import time
ISO2_TO_COUNTRY = {
    c.alpha_2: c.name
    for c in pycountry.countries
}


def load_city_country(path: str):
    """
    Load GeoNames cities file and return:
    {normalized_city_name: set([country_name, ...])}
    Uses 'asciiname' and full country name derived from ISO-2 code.
    """
    path = Path(path).expanduser()
    city_map = {}

    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 9:
                continue
            asciiname = row[1].strip()   # asciiname
            country_code = row[8].strip()  # ISO-2 country code
            if not asciiname or not country_code:
                continue

            country = ISO2_TO_COUNTRY.get(country_code.upper(), country_code)
            key = asciiname.lower()
            city_map.setdefault(key, set()).add(country)

    return city_map
