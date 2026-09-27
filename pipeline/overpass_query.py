"""
overpass_query.py
------------------
Costruisce la query Overpass QL per estrarre dalla bounding box tutti gli
elementi geografici richiesti dalla spec del progetto:
strade, sentieri, edifici, parchi, aree verdi, acqua, punti d'interesse.

Usiamo `out geom;` cosi' Overpass restituisce direttamente la geometria
(lat/lon di ogni nodo) inline in ogni "way", evitando una seconda query per
risolvere i nodi.
"""

from __future__ import annotations


def build_query(south: float, west: float, north: float, east: float, timeout: int = 60) -> str:
    bbox = f"{south},{west},{north},{east}"

    return f"""
[out:json][timeout:{timeout}];
(
  // Edifici
  way["building"]({bbox});

  // Strade carrabili
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street)$"]({bbox});

  // Percorsi pedonali / sentieri
  way["highway"~"^(footway|path|pedestrian|cycleway|steps|track)$"]({bbox});

  // Acqua (laghi, fiumi come superficie)
  way["natural"="water"]({bbox});
  way["waterway"="riverbank"]({bbox});
  relation["natural"="water"]({bbox});

  // Aree verdi
  way["leisure"~"^(park|garden|nature_reserve)$"]({bbox});
  way["landuse"~"^(grass|forest|meadow|recreation_ground|village_green)$"]({bbox});
  way["natural"="wood"]({bbox});

  // Punti di interesse
  node["amenity"]({bbox});
  node["tourism"]({bbox});
  node["leisure"]["leisure"!="park"]({bbox});
);
out geom;
""".strip()


def endpoints_from_config(config: dict) -> list[str]:
    overpass_cfg = config.get("overpass", {})
    urls = [overpass_cfg.get("primary_endpoint", "https://overpass-api.de/api/interpreter")]
    urls.extend(overpass_cfg.get("fallback_endpoints", []))
    return urls
