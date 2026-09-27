"""
coords.py
---------
Conversione tra coordinate geografiche (lat/lon, WGS84) e coordinate locali
in metri, centrate su un punto origine e allineate agli assi usati in Godot.

Perche' una proiezione locale e non lat/lon diretti:
- Gradi di lat/lon NON sono metri: 1 grado di longitudine a Roma (~41.8N) vale
  circa 82.7 km, mentre 1 grado di latitudine vale circa 111.3 km. Usarli
  direttamente come coordinate del mondo 3D produrrebbe un mondo distorto
  e con numeri enormi/poco maneggevoli vicino all'origine (vedi spec: "evitare
  di utilizzare direttamente le coordinate geografiche lat/lon come
  coordinate del mondo 3D").
- Una proiezione azimutale equidistante (AEQD) centrata sull'origine mantiene
  la distanza reale (in metri) dal centro per ogni punto, con distorsione
  trascurabile entro l'area di gioco (qualche km). E' la scelta standard per
  aree locali di questa scala.

Convenzione assi (vedi anche maps/eur/origin.json):
    X = est      (+X verso est)
    Z = -nord    (+Z verso sud, -Z verso nord -> coerente con "forward = -Z"
                  di Godot, cosi' un personaggio che guarda a nord guarda
                  verso -Z)
    Y = quota    (non gestita qui: l'elevazione del terreno/edifici e'
                  responsabilita' della pipeline di generazione mesh)
"""

from __future__ import annotations

from dataclasses import dataclass

from pyproj import Transformer


@dataclass(frozen=True)
class LocalOrigin:
    lat: float
    lon: float

    def make_transformer(self) -> "CoordinateConverter":
        return CoordinateConverter(self.lat, self.lon)


class CoordinateConverter:
    """Converte lat/lon <-> coordinate locali (metri) su proiezione AEQD
    centrata su (origin_lat, origin_lon)."""

    def __init__(self, origin_lat: float, origin_lon: float):
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon

        # +proj=aeqd centrato sull'origine: unita' in metri, origine (0,0)
        # esattamente nel punto (origin_lat, origin_lon).
        proj_str = (
            f"+proj=aeqd +lat_0={origin_lat} +lon_0={origin_lon} "
            f"+ellps=WGS84 +units=m +no_defs"
        )

        self._to_local = Transformer.from_crs("EPSG:4326", proj_str, always_xy=True)
        self._to_geo = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)

    def lonlat_to_local(self, lon: float, lat: float) -> tuple[float, float]:
        """Ritorna (x, z) in metri nel sistema locale/Godot.

        AEQD da pyproj (always_xy=True) restituisce (east_m, north_m).
        Applichiamo la convenzione del progetto: x = east, z = -north.
        """
        east_m, north_m = self._to_local.transform(lon, lat)
        x = east_m
        z = -north_m
        return x, z

    def local_to_lonlat(self, x: float, z: float) -> tuple[float, float]:
        """Operazione inversa: da coordinate locali (x, z) a (lon, lat)."""
        east_m = x
        north_m = -z
        lon, lat = self._to_geo.transform(east_m, north_m)
        return lon, lat

    def convert_ring(self, ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Converte una lista di coordinate (lon, lat) in una lista di (x, z)."""
        return [self.lonlat_to_local(lon, lat) for lon, lat in ring]


def bbox_from_origin(origin_lat: float, origin_lon: float, half_size_m: float):
    """Calcola una bounding box (south, west, north, east) in gradi che
    racchiude un quadrato di lato 2*half_size_m centrato sull'origine.

    Usa la stessa proiezione AEQD per garantire coerenza con il resto della
    pipeline (piuttosto che un'approssimazione a gradi fissi)."""
    conv = CoordinateConverter(origin_lat, origin_lon)

    corners_local = [
        (-half_size_m, -half_size_m),
        (half_size_m, -half_size_m),
        (half_size_m, half_size_m),
        (-half_size_m, half_size_m),
    ]

    lats = []
    lons = []
    for x, z in corners_local:
        lon, lat = conv.local_to_lonlat(x, z)
        lats.append(lat)
        lons.append(lon)

    south, north = min(lats), max(lats)
    west, east = min(lons), max(lons)
    return south, west, north, east
