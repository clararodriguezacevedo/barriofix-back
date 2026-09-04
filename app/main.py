import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import jobs, media, requests

app = FastAPI(title="BarrioFix API")

# Origenes permitidos, separados por coma. El default "*" acepta cualquiera.
# En produccion se setea al website endpoint de S3 del frontend (ver .env.example).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requests.router)
app.include_router(jobs.router)
app.include_router(media.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "BarrioFix Backend - Servidor funcionando correctamente"}
