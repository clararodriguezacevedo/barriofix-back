from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data import REQUESTS, STATUS_EN_PROGRESO, STATUS_PENDIENTE

router = APIRouter(prefix="/api/requests", tags=["requests"])


class NewRequest(BaseModel):
    titulo: str
    categoria: str
    direccion: str
    descripcion: str
    urgencia: str
    cliente: str


class AcceptRequest(BaseModel):
    profesional: str


class StatusUpdate(BaseModel):
    estado: str


class RatingUpdate(BaseModel):
    rating: int
    comentario: str = ""


def _find(request_id: str) -> dict:
    for r in REQUESTS:
        if r["id"] == request_id:
            return r
    raise HTTPException(status_code=404, detail="Solicitud no encontrada")


@router.get("")
def list_requests(categoria: Optional[str] = None, estado: Optional[str] = None):
    results = REQUESTS
    if categoria:
        results = [r for r in results if r["categoria"] == categoria]
    if estado:
        results = [r for r in results if r["estado"] == estado]
    return results


@router.get("/{request_id}")
def get_request(request_id: str):
    return _find(request_id)


@router.post("", status_code=201)
def create_request(payload: NewRequest):
    next_num = max((int(r["id"].replace("BF-", "")) for r in REQUESTS), default=1000) + 1
    nueva = {
        "id": f"BF-{next_num}",
        "profesional": None,
        "estado": STATUS_PENDIENTE,
        "rating": None,
        "comentario": "",
        "creado": "2026-08-30",
        "fotos": [],
        **payload.model_dump(),
    }
    REQUESTS.insert(0, nueva)
    return nueva


@router.patch("/{request_id}/accept")
def accept_request(request_id: str, payload: AcceptRequest):
    r = _find(request_id)
    r["estado"] = STATUS_EN_PROGRESO
    r["profesional"] = payload.profesional
    return r


@router.patch("/{request_id}/status")
def update_status(request_id: str, payload: StatusUpdate):
    r = _find(request_id)
    r["estado"] = payload.estado
    return r


@router.post("/{request_id}/rate")
def rate_request(request_id: str, payload: RatingUpdate):
    r = _find(request_id)
    r["rating"] = payload.rating
    r["comentario"] = payload.comentario
    return r
