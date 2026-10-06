# Geospatial File Measurement API

A FastAPI service that accepts a zipped Shapefile or a KML file, extracts every feature, and returns area and length measurements calculated in a projected coordinate system.

## API

### Upload a file

`POST /api/files/` with multipart form field `file` (`.kml`, or `.zip` containing one or more `.shp` datasets).

```bash
curl -F "file=@survey.kml" http://localhost:8000/api/files/
```

```json
{
  "id": "560653b627ef43768f3614c28ea7a596",
  "filename": "survey.kml",
  "feature_count": 2,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error": null,
  "created_at": "2026-10-06T13:22:59.500803"
}
```

| Status | Meaning |
|---|---|
| `201` | File processed |
| `400` | Unsupported file extension |
| `413` | File larger than `MAX_UPLOAD_MB` |
| `422` | File could not be processed. The body is the file record with `status: FAILED` and an `error` message |

### File information

`GET /api/files/{id}/` returns the same object as the upload response. Returns `404` for an unknown id.

### Features

`GET /api/files/{id}/features/?limit=100&offset=0`

```json
{
  "file_id": "560653b627ef43768f3614c28ea7a596",
  "total": 2,
  "limit": 100,
  "offset": 0,
  "features": [
    {
      "index": 1,
      "geometry_type": "LineString",
      "geometry": {"type": "LineString", "coordinates": [[75.8, 26.9, 0.0], [75.8, 26.91, 0.0]]},
      "crs": "EPSG:4326",
      "properties": {"Name": "B"},
      "supported": true
    }
  ]
}
```

Geometry is returned as GeoJSON in the file's original CRS.

### Measurements

`GET /api/files/{id}/measurements/?limit=100&offset=0`

```json
{
  "file_id": "560653b627ef43768f3614c28ea7a596",
  "total": 2,
  "limit": 100,
  "offset": 0,
  "total_area_sq_m": 0.0,
  "total_length_m": 1107.66,
  "measurements": [
    {"index": 0, "geometry_type": "Point", "supported": true, "projected_crs": null, "area_sq_m": null, "length_m": null},
    {"index": 1, "geometry_type": "LineString", "supported": true, "projected_crs": "EPSG:32643", "area_sq_m": null, "length_m": 1107.66}
  ]
}
```

`total_area_sq_m` and `total_length_m` cover the whole file, not just the current page.

| Geometry | Result |
|---|---|
| Polygon, MultiPolygon | `area_sq_m` |
| LineString, MultiLineString | `length_m` |
| Point, MultiPoint | `supported: true`, no measurement |
| Anything else (empty, null, geometry collections) | `supported: false`, no measurement |

## Architecture

```
app/
  main.py          app creation and startup
  routes.py        HTTP endpoints
  processing.py    reads files and turns them into feature records
  measurements.py  CRS selection and area/length calculation
  models.py        SQLAlchemy tables (files, features)
  schemas.py       response models
  database.py      engine and session
  config.py        environment configuration
tests/             API and measurement tests
```

### File-processing flow

1. The route validates the extension and streams the upload to a temporary directory, enforcing the size limit.
2. `process_upload` finds the data sources: the KML itself, or every `.shp` extracted from the zip.
3. Each source is read layer by layer with GeoPandas (a KML folder becomes a layer).
4. Every feature gets a running index, its geometry as GeoJSON, its original CRS, its properties, and its measurement.
5. The route stores the file and its features in one transaction and returns the file record. Any `ProcessingError` is stored as a `FAILED` file with a message.

### Measurement flow

For each feature the geometry is converted to WGS84, a UTM zone is chosen from its centroid, the geometry is projected to that zone, and Shapely computes `area` or `length` in metres. The results are stored with the feature, so the measurements endpoint is a plain database read.

### CRS handling

- The CRS comes from the file (`.prj` for shapefiles, always WGS84 for KML). A file without one is rejected rather than guessed.
- Measurements never use degrees. A geometry is converted to EPSG:4326 only to pick the UTM zone, then projected to `EPSG:326xx` (north) or `EPSG:327xx` (south).
- The zone is chosen per feature, so a file spanning several zones is still measured accurately feature by feature.
- Features keep their original CRS and original coordinates in the response. The projected CRS used is reported with each measurement.

## Design Decisions

- **FastAPI over Django.** The task is a small API with no admin or auth needs. FastAPI gives validation, response models and OpenAPI docs with very little code.
- **GeoPandas for reading.** One call reads shapefiles and KML, exposes the CRS, and serialises properties to JSON safely (dates, NaN). The alternative, `fastkml` plus `pyshp`, means two parsers and manual attribute handling.
- **UTM per feature instead of one projection per file.** It is simple and accurate for features within a zone. Alternatives I considered: a single equal-area projection (good for area, poor for length), and geodesic calculation with `pyproj.Geod` (most accurate, but it skips the projected-CRS step the task asks for).
- **Measure at upload time.** Reading a file is the expensive step. Computing once and storing the numbers keeps GET endpoints fast and cheap.
- **Synchronous processing.** Files up to the size limit process in seconds, so a task queue would add moving parts without clear benefit. The endpoint is a plain `def`, so FastAPI runs it in a worker thread and the event loop is not blocked.
- **SQLite with SQLAlchemy.** Zero setup for a reviewer, and switching to PostgreSQL only needs a different `DATABASE_URL`.
- **Failures are stored.** A bad upload returns `422` but is saved as `FAILED`, so there is a record of what happened.
- **Unsupported geometries return `supported: false`.** The upload still succeeds and the other features are measured.

## Learnings

- Shapefiles hold one geometry type each, so a realistic upload is often several `.shp` sets in one zip.
- KML folders show up as separate layers, and a reader that only opens the first layer silently drops data.
- KML geometries carry Z values; area and length are calculated in 2D and ignore elevation.
- Choosing the CRS is the core of the problem. Degrees are not metres, and one degree of longitude shrinks with latitude.