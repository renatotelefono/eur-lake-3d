"""
test_osm_to_geojson.py
-----------------------
Validazione OFFLINE della pipeline di conversione, senza contattare Overpass
API. Necessaria perche' l'ambiente cloud usato per scrivere questo progetto
non ha accesso di rete verso overpass-api.de (policy di rete
dell'organizzazione blocca l'host) -- vedi README, sezione "Limiti noti".

Il dataset qui sotto ha la stessa forma esatta della risposta Overpass con
`out geom;` (vedi pipeline/overpass_query.py) ma con coordinate scelte a
mano attorno all'origine reale del Laghetto dell'EUR, per rappresentare in
modo plausibile: un edificio, una strada, un sentiero, il lago stesso, un
parco e un punto di interesse.

Esegui con:  python3 tests/test_osm_to_geojson.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from osm_to_geojson import convert_elements  # noqa: E402

ORIGIN_LAT = 41.828447
ORIGIN_LON = 12.466024

# Offset approssimativi in gradi per posizionare gli elementi finti attorno
# all'origine (non serve precisione qui, e' solo per validare la logica).
D_LAT = 0.0004  # ~44 m
D_LON = 0.0006  # ~50 m a questa latitudine

FAKE_ELEMENTS = [
    # Edificio: footprint rettangolare chiuso, con altezza esplicita
    {
        "type": "way",
        "id": 1001,
        "tags": {"building": "yes", "name": "Edificio di test", "height": "12 m"},
        "geometry": [
            {"lat": ORIGIN_LAT + D_LAT, "lon": ORIGIN_LON + D_LON},
            {"lat": ORIGIN_LAT + D_LAT, "lon": ORIGIN_LON + D_LON + 0.0002},
            {"lat": ORIGIN_LAT + D_LAT + 0.00015, "lon": ORIGIN_LON + D_LON + 0.0002},
            {"lat": ORIGIN_LAT + D_LAT + 0.00015, "lon": ORIGIN_LON + D_LON},
            {"lat": ORIGIN_LAT + D_LAT, "lon": ORIGIN_LON + D_LON},
        ],
    },
    # Edificio senza height esplicita ma con building:levels
    {
        "type": "way",
        "id": 1002,
        "tags": {"building": "residential", "building:levels": "4"},
        "geometry": [
            {"lat": ORIGIN_LAT - D_LAT, "lon": ORIGIN_LON - D_LON},
            {"lat": ORIGIN_LAT - D_LAT, "lon": ORIGIN_LON - D_LON + 0.00015},
            {"lat": ORIGIN_LAT - D_LAT - 0.0001, "lon": ORIGIN_LON - D_LON + 0.00015},
            {"lat": ORIGIN_LAT - D_LAT - 0.0001, "lon": ORIGIN_LON - D_LON},
            {"lat": ORIGIN_LAT - D_LAT, "lon": ORIGIN_LON - D_LON},
        ],
    },
    # Strada carrabile
    {
        "type": "way",
        "id": 2001,
        "tags": {"highway": "residential", "name": "Via di Prova", "lanes": "2", "surface": "asphalt"},
        "geometry": [
            {"lat": ORIGIN_LAT - 0.0006, "lon": ORIGIN_LON + 0.0003},
            {"lat": ORIGIN_LAT - 0.0002, "lon": ORIGIN_LON + 0.0003},
            {"lat": ORIGIN_LAT + 0.0002, "lon": ORIGIN_LON + 0.0003},
            {"lat": ORIGIN_LAT + 0.0006, "lon": ORIGIN_LON + 0.0003},
        ],
    },
    # Sentiero pedonale attorno al lago
    {
        "type": "way",
        "id": 2002,
        "tags": {"highway": "footway", "name": "Passeggiata del Giappone"},
        "geometry": [
            {"lat": ORIGIN_LAT + 0.0005, "lon": ORIGIN_LON - 0.0005},
            {"lat": ORIGIN_LAT + 0.0003, "lon": ORIGIN_LON},
            {"lat": ORIGIN_LAT + 0.0005, "lon": ORIGIN_LON + 0.0005},
        ],
    },
    # Il laghetto stesso (poligono chiuso, natural=water)
    {
        "type": "way",
        "id": 3001,
        "tags": {"natural": "water", "name": "Laghetto dell'EUR"},
        "geometry": [
            {"lat": ORIGIN_LAT + 0.0003, "lon": ORIGIN_LON - 0.0004},
            {"lat": ORIGIN_LAT + 0.0004, "lon": ORIGIN_LON},
            {"lat": ORIGIN_LAT + 0.0003, "lon": ORIGIN_LON + 0.0004},
            {"lat": ORIGIN_LAT - 0.0003, "lon": ORIGIN_LON + 0.0002},
            {"lat": ORIGIN_LAT - 0.0004, "lon": ORIGIN_LON - 0.0002},
            {"lat": ORIGIN_LAT + 0.0003, "lon": ORIGIN_LON - 0.0004},
        ],
    },
    # Area verde / parco
    {
        "type": "way",
        "id": 4001,
        "tags": {"leisure": "park", "name": "Parco Centrale del Lago"},
        "geometry": [
            {"lat": ORIGIN_LAT + 0.0008, "lon": ORIGIN_LON - 0.0008},
            {"lat": ORIGIN_LAT + 0.0009, "lon": ORIGIN_LON - 0.0003},
            {"lat": ORIGIN_LAT + 0.0006, "lon": ORIGIN_LON - 0.0002},
            {"lat": ORIGIN_LAT + 0.0005, "lon": ORIGIN_LON - 0.0007},
            {"lat": ORIGIN_LAT + 0.0008, "lon": ORIGIN_LON - 0.0008},
        ],
    },
    # Punto di interesse
    {
        "type": "node",
        "id": 5001,
        "tags": {"amenity": "cafe", "name": "Bar del Laghetto"},
        "lat": ORIGIN_LAT + 0.0001,
        "lon": ORIGIN_LON - 0.0001,
    },
    # Elemento da ignorare (nessun tag rilevante)
    {
        "type": "way",
        "id": 9999,
        "tags": {"barrier": "fence"},
        "geometry": [
            {"lat": ORIGIN_LAT, "lon": ORIGIN_LON},
            {"lat": ORIGIN_LAT + 0.0001, "lon": ORIGIN_LON + 0.0001},
        ],
    },
]

CONFIG = {
    "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON},
    "building_defaults": {"default_height_m": 9.0, "height_per_level_m": 3.0},
    "road_defaults": {"default_width_m": 6.0, "width_per_lane_m": 3.25, "footway_width_m": 2.0},
}


def run() -> None:
    layers = convert_elements(FAKE_ELEMENTS, CONFIG)

    counts = {name: len(fc["features"]) for name, fc in layers.items()}
    print("Conteggio feature per layer:", counts)

    assert counts["buildings"] == 2, counts
    assert counts["roads"] == 1, counts
    assert counts["paths"] == 1, counts
    assert counts["water"] == 1, counts
    assert counts["green"] == 1, counts
    assert counts["poi"] == 1, counts

    buildings = layers["buildings"]["features"]
    b1 = next(f for f in buildings if f["properties"]["name"] == "Edificio di test")
    assert b1["properties"]["height_m"] == 12.0, b1["properties"]

    b2 = next(f for f in buildings if f["properties"].get("building") == "residential")
    assert b2["properties"]["height_m"] == 12.0, b2["properties"]  # 4 livelli * 3.0m

    assert b1["geometry"]["type"] == "Polygon"
    ring = b1["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1], "il poligono deve essere chiuso"

    road = layers["roads"]["features"][0]
    assert road["properties"]["width_m"] == 6.5  # 2 corsie * 3.25m
    assert road["geometry"]["type"] == "LineString"

    water = layers["water"]["features"][0]
    assert water["geometry"]["type"] == "Polygon"
    assert water["properties"]["name"] == "Laghetto dell'EUR"

    poi = layers["poi"]["features"][0]
    assert poi["properties"]["category"] == "cafe"
    assert poi["geometry"]["type"] == "Point"

    # Le coordinate devono essere numeri "piccoli" (metri, non gradi):
    # un edificio a poche decine di metri dall'origine deve avere |x|,|z| < 200
    for x, z in ring:
        assert abs(x) < 200 and abs(z) < 200, (x, z)

    print("Tutti i controlli sono passati: la conversione OSM -> GeoJSON locale funziona correttamente.")

    # Scrive anche i file di esempio in data/osm/, cosi' il progetto consegnato
    # include GeoJSON di esempio pronti per essere aperti da blender_import.py
    # anche prima di eseguire fetch_osm.py con una connessione reale.
    out_dir = Path(__file__).resolve().parent.parent / "data" / "osm"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, collection in layers.items():
        (out_dir / f"{name}.geojson").write_text(json.dumps(collection, indent=2), encoding="utf-8")
    print(f"GeoJSON di esempio scritti in {out_dir}")


if __name__ == "__main__":
    run()
