from typing import Optional

from fastapi import APIRouter

from app.data import REQUESTS, STATUS_PENDIENTE

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_available_jobs(categoria: Optional[str] = None, urgencia: Optional[str] = None):
    """Trabajos pendientes disponibles para que un profesional los tome."""
    results = [r for r in REQUESTS if r["estado"] == STATUS_PENDIENTE]
    if categoria:
        results = [r for r in results if r["categoria"] == categoria]
    if urgencia:
        results = [r for r in results if r["urgencia"] == urgencia]
    return results
