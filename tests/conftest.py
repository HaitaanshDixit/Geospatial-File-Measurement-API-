import os
import shutil
import tempfile
from pathlib import Path

DB_DIR = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{DB_DIR}/test.db"

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, Polygon

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
    shutil.rmtree(DB_DIR, ignore_errors=True)


@pytest.fixture
def sample_frame():
    return gpd.GeoDataFrame(
        {"name": ["plot", "road", "well"]},
        geometry=[
            Polygon([(75.80, 26.90), (75.81, 26.90), (75.81, 26.91), (75.80, 26.91)]),
            LineString([(75.80, 26.90), (75.80, 26.91)]),
            Point(75.805, 26.905),
        ],
        crs="EPSG:4326",
    )


@pytest.fixture
def kml_path(tmp_path, sample_frame):
    path = tmp_path / "survey.kml"
    sample_frame.to_file(path, driver="KML")
    return path


@pytest.fixture
def shapefile_zip_path(tmp_path, sample_frame):
    folder = tmp_path / "shp"
    folder.mkdir()
    for geometry_type, group in sample_frame.groupby(sample_frame.geom_type):
        group.to_file(folder / f"{geometry_type.lower()}.shp")
    archive = shutil.make_archive(str(tmp_path / "survey"), "zip", folder)
    return Path(archive)
