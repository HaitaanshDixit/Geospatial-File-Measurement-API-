import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from pyogrio import list_layers
from pyogrio.errors import DataLayerError, DataSourceError

from app.measurements import measure


class ProcessingError(Exception):
    pass


def describe_crs(crs):
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.to_string()


def find_sources(upload_path, workdir):
    if upload_path.suffix.lower() == ".kml":
        return [upload_path]

    try:
        with zipfile.ZipFile(upload_path) as archive:
            archive.extractall(workdir)
    except zipfile.BadZipFile as exc:
        raise ProcessingError("Upload is not a valid zip archive") from exc

    shapefiles = [path for path in sorted(workdir.rglob("*.shp")) if not path.name.startswith("._")]
    if not shapefiles:
        raise ProcessingError("Zip archive does not contain a .shp file")
    return shapefiles


def read_frames(source):
    try:
        layer_names = list_layers(source)[:, 0]
        return [gpd.read_file(source, layer=name) for name in layer_names]
    except (DataSourceError, DataLayerError, ValueError) as exc:
        raise ProcessingError(f"Could not read {source.name}: {exc}") from exc


def frame_to_features(frame, source_name, start_index):
    if frame.crs is None:
        raise ProcessingError(f"{source_name} has no coordinate reference system")

    crs = describe_crs(frame.crs)
    wgs84_geometries = frame.geometry.to_crs(4326)
    items = json.loads(frame.to_json())["features"]

    features = []
    for offset, (item, wgs84_geometry) in enumerate(zip(items, wgs84_geometries)):
        measurement = measure(wgs84_geometry)
        geometry_type = "None" if wgs84_geometry is None else wgs84_geometry.geom_type
        features.append(
            {
                "index": start_index + offset,
                "geometry_type": geometry_type,
                "geometry": item["geometry"],
                "crs": crs,
                "properties": item["properties"],
                "supported": measurement.supported,
                "projected_crs": measurement.projected_crs,
                "area_sq_m": measurement.area_sq_m,
                "length_m": measurement.length_m,
            }
        )
    return features


def process_upload(upload_path):
    features = []

    with tempfile.TemporaryDirectory() as workdir:
        for source in find_sources(upload_path, Path(workdir)):
            for frame in read_frames(source):
                if frame.empty:
                    continue
                features.extend(frame_to_features(frame, source.name, len(features)))

    if not features:
        raise ProcessingError("File contains no features")

    crs_values = {feature["crs"] for feature in features}
    file_crs = crs_values.pop() if len(crs_values) == 1 else "MIXED"
    return file_crs, features
