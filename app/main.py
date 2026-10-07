from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.models import create_tables
from app.routes import router


@asynccontextmanager
async def lifespan(app):
    create_tables()
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)
app.include_router(router)
