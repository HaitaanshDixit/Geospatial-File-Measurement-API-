from dataclasses import dataclass
from functools import lru_cache

from pyproj import Transformer
from shapely.ops import transform

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


@dataclass
class Measurement:
    supported: bool
    projected_crs: str | None = None
    area_sq_m: float | None = None
    length_m: float | None = None


@lru_cache(maxsize=128)
def transformer_to(target_crs):
    return Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)


def utm_crs_for(geometry):
    centroid = geometry.centroid
    zone = min(int((centroid.x + 180) // 6) + 1, 60)
    base = 32600 if centroid.y >= 0 else 32700
    return f"EPSG:{base + zone}"


def measure(geometry):
    if geometry is None or geometry.is_empty:
        return Measurement(supported=False)

    kind = geometry.geom_type

    if kind in POINT_TYPES:
        return Measurement(supported=True)

    if kind not in AREA_TYPES | LENGTH_TYPES:
        return Measurement(supported=False)

    target_crs = utm_crs_for(geometry)
    projected = transform(transformer_to(target_crs).transform, geometry)

    if kind in AREA_TYPES:
        return Measurement(True, target_crs, area_sq_m=projected.area)
    return Measurement(True, target_crs, length_m=projected.length)
