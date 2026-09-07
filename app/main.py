import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, calificaciones, catalogos, fotos, profesionales, solicitudes, usuarios

app = FastAPI(
    title="BarrioFix API",
    description="Plataforma de reparaciones barriales. Datos en RDS PostgreSQL, fotos en S3.",
    version="2.0.0",
)

# Origenes permitidos, separados por coma. El default "*" acepta cualquiera.
# En produccion se setea al website endpoint de S3 del frontend (ver .env.example).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(catalogos.router)
app.include_router(usuarios.router)
app.include_router(profesionales.router)
app.include_router(solicitudes.router)
app.include_router(fotos.router)
app.include_router(calificaciones.router)


@app.get("/health", tags=["salud"])
def health():
    """Health check del Target Group. NO consulta la base a proposito: si RDS
    se cae, no queremos que el ALB saque de servicio a las instancias."""
    return {"status": "ok"}


@app.get("/health/db", tags=["salud"])
def health_db():
    """Conectividad con RDS. Separada de /health justamente para que un
    problema de base no baje las instancias del balanceador."""
    # Import perezoso: si la AMI todavia no tiene el driver instalado, la app
    # levanta igual y solo falla este endpoint.
    try:
        from app.db import check_connection
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Driver de base no instalado: {e}")

    try:
        return check_connection()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar a la base: {e}")


@app.get("/", tags=["salud"])
def root():
    return {"message": "BarrioFix Backend - Servidor funcionando correctamente"}
