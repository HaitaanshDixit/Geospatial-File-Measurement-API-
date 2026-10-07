import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES
from app.database import get_db
from app.models import Feature, UploadedFile
from app.processing import ProcessingError, process_upload
from app.schemas import FeaturesPage, FileOut, MeasurementsPage

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_SUFFIXES = {".kml", ".zip"}


def get_file_or_404(db, file_id):
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    return record


def save_upload(upload, destination):
    size = 0
    with destination.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File is too large")
            out.write(chunk)


def list_features(db, file_id, limit, offset):
    query = (
        select(Feature)
        .where(Feature.file_id == file_id)
        .order_by(Feature.index)
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(query).all()


@router.post("/", response_model=FileOut, status_code=201)
def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .zip (shapefile) and .kml files are supported")

    record = UploadedFile(filename=filename)

    with tempfile.TemporaryDirectory() as workdir:
        upload_path = Path(workdir) / f"upload{suffix}"
        save_upload(file, upload_path)
        try:
            crs, features = process_upload(upload_path)
        except ProcessingError as exc:
            record.status = "FAILED"
            record.error = str(exc)
            db.add(record)
            db.commit()
            db.refresh(record)
            body = FileOut.model_validate(record).model_dump(mode="json")
            return JSONResponse(status_code=422, content=body)

    record.status = "COMPLETED"
    record.crs = crs
    record.feature_count = len(features)
    record.features = [Feature(**feature) for feature in features]
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{file_id}/", response_model=FileOut)
def get_file(file_id: str, db: Session = Depends(get_db)):
    return get_file_or_404(db, file_id)


@router.get("/{file_id}/features/", response_model=FeaturesPage)
def get_features(
    file_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    record = get_file_or_404(db, file_id)
    return {
        "file_id": record.id,
        "total": record.feature_count,
        "limit": limit,
        "offset": offset,
        "features": list_features(db, record.id, limit, offset),
    }


@router.get("/{file_id}/measurements/", response_model=MeasurementsPage)
def get_measurements(
    file_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    record = get_file_or_404(db, file_id)
    totals = db.execute(
        select(
            func.coalesce(func.sum(Feature.area_sq_m), 0.0),
            func.coalesce(func.sum(Feature.length_m), 0.0),
        ).where(Feature.file_id == record.id)
    ).one()
    return {
        "file_id": record.id,
        "total": record.feature_count,
        "limit": limit,
        "offset": offset,
        "total_area_sq_m": totals[0],
        "total_length_m": totals[1],
        "measurements": list_features(db, record.id, limit, offset),
    }
