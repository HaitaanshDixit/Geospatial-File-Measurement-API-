from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str
    error: str | None = None
    created_at: datetime


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str
    geometry: dict | None
    crs: str
    properties: dict
    supported: bool


class FeaturesPage(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    features: list[FeatureOut]


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str
    supported: bool
    projected_crs: str | None
    area_sq_m: float | None
    length_m: float | None


class MeasurementsPage(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    total_area_sq_m: float
    total_length_m: float
    measurements: list[MeasurementOut]
