"""FastAPI application entry point."""

from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="Pond Catchment Analysis API",
    description=(
        "Upload a contour map (KML/KMZ), get back the ideal pond site "
        "and its catchment area as structured JSON."
    ),
    version="1.0.0",
)

app.include_router(router)
