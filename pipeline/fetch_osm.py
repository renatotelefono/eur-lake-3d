#!/usr/bin/env python3
"""
fetch_osm.py
------------
CLI che esegue il primo stadio della pipeline del progetto:

    OpenStreetMap -> Overpass API -> dati geografici -> GeoJSON locale

Uso:
    python3 pipeline/fetch_osm.py \\
        --config maps/eur/origin.json \\
        --out data/osm/

IMPORTANTE: questo script richiede accesso di rete verso gli endpoint
pubblici di Overpass API (overpass-api.de e i mirror di fallback). Se lo
esegui in un ambiente con rete ristretta (es. alcune sandbox cloud) la
richiesta fallira': eseguilo dal tuo computer, dove la rete e' normale.

Rispetto della licenza OSM (ODbL): i dati scaricati vanno usati includendo
l'attribuzione richiesta ("© OpenStreetMap contributors"), che il progetto
mostra nella UI di gioco (vedi README, sezione Licenza e attribuzione).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from coords import bbox_from_origin
from osm_to_geojson import convert_elements
from overpass_query import build_query, endpoints_from_config

USER_AGENT = "eur-lake-3d-pipeline/0.1 (progetto hobbistico, contattare via GitHub issue)"


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def query_overpass(query: str, endpoints: list[str], timeout_s: int = 90) -> dict:
    last_error: Exception | None = None
    for url in endpoints:
        try:
            print(f"[fetch_osm] Interrogo {url} ...", file=sys.stderr)
            data = query.encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "User-Agent": USER_AGENT,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read()
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"[fetch_osm] Endpoint {url} fallito: {exc}", file=sys.stderr)
            last_error = exc
            time.sleep(2)
            continue

    raise RuntimeError(
        "Impossibile contattare qualsiasi endpoint Overpass. "
        "Verifica la connessione di rete (vedi docstring del modulo)."
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="maps/eur/origin.json", help="File di configurazione area")
    parser.add_argument("--out", default="data/osm", help="Cartella di output per i GeoJSON")
    parser.add_argument("--raw-out", default=None, help="Se indicato, salva anche la risposta grezza Overpass JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(config_path)
    origin = config["origin"]
    half_size = config.get("bbox_half_size_m", 500)

    south, west, north, east = bbox_from_origin(origin["lat"], origin["lon"], half_size)
    print(f"[fetch_osm] Bounding box: south={south:.6f} west={west:.6f} north={north:.6f} east={east:.6f}")

    query = build_query(south, west, north, east)
    endpoints = endpoints_from_config(config)

    result = query_overpass(query, endpoints)
    elements = result.get("elements", [])
    print(f"[fetch_osm] Ricevuti {len(elements)} elementi da Overpass.")

    if args.raw_out:
        raw_path = Path(args.raw_out)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[fetch_osm] Risposta grezza salvata in {raw_path}")

    layers = convert_elements(elements, config)

    for name, collection in layers.items():
        out_path = out_dir / f"{name}.geojson"
        out_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
        print(f"[fetch_osm] {name}: {len(collection['features'])} feature -> {out_path}")

    print("[fetch_osm] Completato. Prossimo passo: pipeline/blender_import.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
