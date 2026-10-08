import pytest

from app.measurements import measure, utm_crs_for
from shapely.geometry import GeometryCollection, Point, Polygon

EXPECTED_AREA = 1_099_000
EXPECTED_LENGTH = 1_105


def upload(client, path, name=None):
    with path.open("rb") as handle:
        return client.post("/api/files/", files={"file": (name or path.name, handle)})


def by_type(measurements):
    return {item["geometry_type"]: item for item in measurements}


@pytest.mark.parametrize("fixture_name", ["kml_path", "shapefile_zip_path"])
def test_upload_and_measure(client, request, fixture_name):
    path = request.getfixturevalue(fixture_name)

    response = upload(client, path)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"

    info = client.get(f"/api/files/{body['id']}/")
    assert info.status_code == 200
    assert info.json()["filename"] == path.name

    measurements = client.get(f"/api/files/{body['id']}/measurements/").json()
    items = by_type(measurements["measurements"])
    assert items["Polygon"]["area_sq_m"] == pytest.approx(EXPECTED_AREA, rel=0.01)
    assert items["LineString"]["length_m"] == pytest.approx(EXPECTED_LENGTH, rel=0.01)
    assert items["Polygon"]["projected_crs"] == "EPSG:32643"
    assert items["Point"]["area_sq_m"] is None
    assert items["Point"]["length_m"] is None
    assert measurements["total_area_sq_m"] == pytest.approx(items["Polygon"]["area_sq_m"])


def test_features_endpoint(client, kml_path):
    file_id = upload(client, kml_path).json()["id"]

    page = client.get(f"/api/files/{file_id}/features/", params={"limit": 2}).json()

    assert page["total"] == 3
    assert len(page["features"]) == 2
    feature = page["features"][0]
    assert {"index", "geometry_type", "geometry", "crs", "properties"} <= feature.keys()
    assert feature["crs"] == "EPSG:4326"


def test_rejects_unknown_extension(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    assert upload(client, path).status_code == 400


def test_invalid_zip_is_reported_as_failed(client, tmp_path):
    path = tmp_path / "broken.zip"
    path.write_bytes(b"not a zip")

    response = upload(client, path)

    assert response.status_code == 422
    assert response.json()["status"] == "FAILED"
    assert client.get(f"/api/files/{response.json()['id']}/").json()["status"] == "FAILED"


def test_unknown_file_returns_404(client):
    assert client.get("/api/files/missing/").status_code == 404
    assert client.get("/api/files/missing/measurements/").status_code == 404


def test_unsupported_geometry_is_handled_gracefully():
    collection = GeometryCollection([Point(75.8, 26.9)])

    result = measure(collection)

    assert result.supported is False
    assert result.area_sq_m is None
    assert measure(None).supported is False


def test_utm_zone_selection():
    assert utm_crs_for(Point(75.8, 26.9)) == "EPSG:32643"
    assert utm_crs_for(Point(-70.0, -33.0)) == "EPSG:32719"


def test_polygon_area_in_southern_hemisphere():
    square = Polygon([(18.40, -33.90), (18.41, -33.90), (18.41, -33.91), (18.40, -33.91)])

    result = measure(square)

    assert result.projected_crs == "EPSG:32734"
    assert result.area_sq_m == pytest.approx(1_020_000, rel=0.02)
