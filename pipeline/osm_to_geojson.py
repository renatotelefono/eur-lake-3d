"""
osm_to_geojson.py
------------------
Logica "pura" (nessuna chiamata di rete) che trasforma gli elementi grezzi
restituiti da Overpass API (formato Overpass JSON con `out geom;`) in
FeatureCollection GeoJSON separate per layer, con coordinate gia' convertite
nel sistema locale in metri definito da coords.py.

Tenuta separata da fetch_osm.py (che fa solo I/O di rete) cosi' puo' essere
testata offline con dati finti: vedi tests/test_osm_to_geojson.py.

NOTA IMPORTANTE sul formato: i file .geojson prodotti qui NON sono GeoJSON
standard (che richiede coordinate lon/lat in gradi, EPSG:4326). Le
coordinate sono invece [x, z] in metri nel sistema locale del progetto
(vedi coords.py e maps/eur/origin.json). Usiamo comunque la struttura
GeoJSON perche' e' un formato comodo, ben supportato dagli strumenti di
parsing e leggibile da Blender; un campo "crs" nella FeatureCollection lo
segnala esplicitamente.
"""

from __future__ import annotations

import re
from typing import Any

from coords import CoordinateConverter

CARRIAGEWAY_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "service", "living_street",
}
PEDESTRIAN_HIGHWAYS = {
    "footway", "path", "pedestrian", "cycleway", "steps", "track",
}
GREEN_LEISURE = {"park", "garden", "nature_reserve"}
GREEN_LANDUSE = {"grass", "forest", "meadow", "recreation_ground", "village_green"}

_HEIGHT_RE = re.compile(r"[-+]?\d*\.?\d+")


def _parse_height_tag(value: str | None) -> float | None:
    """Estrae un numero (metri) da un tag height OSM tipo '12', '12 m', '12m'."""
    if not value:
        return None
    match = _HEIGHT_RE.search(value)
    return float(match.group()) if match else None


def _building_height_m(tags: dict, defaults: dict) -> float:
    height = _parse_height_tag(tags.get("height"))
    if height is not None:
        return height

    levels = tags.get("building:levels")
    if levels is not None:
        try:
            return float(levels) * defaults.get("height_per_level_m", 3.0)
        except ValueError:
            pass

    return defaults.get("default_height_m", 9.0)


def _road_width_m(tags: dict, defaults: dict, is_footway: bool) -> float:
    width = _parse_height_tag(tags.get("width"))
    if width is not None:
        return width

    if is_footway:
        return defaults.get("footway_width_m", 2.0)

    lanes = tags.get("lanes")
    if lanes is not None:
        try:
            return float(lanes) * defaults.get("width_per_lane_m", 3.25)
        except ValueError:
            pass

    return defaults.get("default_width_m", 6.0)


def _way_ring_local(element: dict, converter: CoordinateConverter) -> list[list[float]]:
    geometry = element.get("geometry") or []
    ring = [(pt["lon"], pt["lat"]) for pt in geometry if pt is not None]
    local = converter.convert_ring(ring)
    return [[round(x, 3), round(z, 3)] for x, z in local]


def _is_closed(ring: list[list[float]]) -> bool:
    if len(ring) < 3:
        return False
    return ring[0] == ring[-1]


def _new_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "crs": {"type": "local-meters", "note": "coordinate [x, z] in metri, vedi coords.py"},
        "features": [],
    }


def convert_elements(elements: list[dict], config: dict) -> dict[str, dict]:
    """Converte una lista di elementi Overpass (formato `out geom;`) nelle
    FeatureCollection per layer: buildings, roads, paths, water, green, poi.

    Ritorna un dict {layer_name: geojson_feature_collection}.
    """
    origin = config["origin"]
    converter = CoordinateConverter(origin["lat"], origin["lon"])
    building_defaults = config.get("building_defaults", {})
    road_defaults = config.get("road_defaults", {})

    layers = {
        "buildings": _new_collection(),
        "roads": _new_collection(),
        "paths": _new_collection(),
        "water": _new_collection(),
        "green": _new_collection(),
        "poi": _new_collection(),
    }

    for element in elements:
        tags = element.get("tags", {}) or {}
        el_type = element.get("type")

        if el_type == "node":
            _handle_poi(element, tags, converter, layers["poi"])
            continue

        if el_type != "way":
            # Le relation multipolygon (es. acqua complessa) non sono
            # gestite in questa versione MVP: i loro member "way" chiusi
            # vengono comunque inclusi separatamente da Overpass come way
            # a se stanti solo se matchano un filtro sopra; altrimenti sono
            # ignorati qui. Limite noto, documentato nel README.
            continue

        ring = _way_ring_local(element, converter)
        if len(ring) < 2:
            continue

        if "building" in tags:
            _handle_building(element, tags, ring, building_defaults, layers["buildings"])
        elif tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            _handle_area(element, tags, ring, layers["water"], area_kind="water")
        elif (
            tags.get("leisure") in GREEN_LEISURE
            or tags.get("landuse") in GREEN_LANDUSE
            or tags.get("natural") == "wood"
        ):
            _handle_area(element, tags, ring, layers["green"], area_kind="green")
        elif tags.get("highway") in CARRIAGEWAY_HIGHWAYS:
            _handle_line(element, tags, ring, road_defaults, layers["roads"], is_footway=False)
        elif tags.get("highway") in PEDESTRIAN_HIGHWAYS:
            _handle_line(element, tags, ring, road_defaults, layers["paths"], is_footway=True)

    return layers


def _handle_building(element, tags, ring, defaults, collection):
    height_m = _building_height_m(tags, defaults)
    geometry = (
        {"type": "Polygon", "coordinates": [ring]}
        if _is_closed(ring)
        else {"type": "LineString", "coordinates": ring}
    )
    collection["features"].append({
        "type": "Feature",
        "id": element.get("id"),
        "geometry": geometry,
        "properties": {
            "osm_id": element.get("id"),
            "name": tags.get("name"),
            "building": tags.get("building"),
            "height_m": round(height_m, 2),
            "levels": tags.get("building:levels"),
        },
    })


def _handle_area(element, tags, ring, collection, area_kind):
    geometry = (
        {"type": "Polygon", "coordinates": [ring]}
        if _is_closed(ring)
        else {"type": "LineString", "coordinates": ring}
    )
    collection["features"].append({
        "type": "Feature",
        "id": element.get("id"),
        "geometry": geometry,
        "properties": {
            "osm_id": element.get("id"),
            "name": tags.get("name"),
            "kind": area_kind,
            "natural": tags.get("natural"),
            "leisure": tags.get("leisure"),
            "landuse": tags.get("landuse"),
        },
    })


def _handle_line(element, tags, ring, defaults, collection, is_footway):
    width_m = _road_width_m(tags, defaults, is_footway)
    collection["features"].append({
        "type": "Feature",
        "id": element.get("id"),
        "geometry": {"type": "LineString", "coordinates": ring},
        "properties": {
            "osm_id": element.get("id"),
            "name": tags.get("name"),
            "highway": tags.get("highway"),
            "lanes": tags.get("lanes"),
            "width_m": round(width_m, 2),
            "surface": tags.get("surface"),
            "maxspeed": tags.get("maxspeed"),
        },
    })


def _handle_poi(element, tags, converter, collection):
    lon, lat = element.get("lon"), element.get("lat")
    if lon is None or lat is None:
        return
    x, z = converter.lonlat_to_local(lon, lat)
    category = tags.get("amenity") or tags.get("tourism") or tags.get("leisure") or "poi"
    collection["features"].append({
        "type": "Feature",
        "id": element.get("id"),
        "geometry": {"type": "Point", "coordinates": [round(x, 3), round(z, 3)]},
        "properties": {
            "osm_id": element.get("id"),
            "name": tags.get("name"),
            "category": category,
        },
    })
