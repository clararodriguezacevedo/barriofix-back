"""Schemas Pydantic: contrato de entrada y salida de la API.

Los ids son enteros (los de la base). El formato viejo "BF-1042" no existe mas.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- catalogos


class CategoriaOut(ORMModel):
    id_categoria: int
    nombre: str
    descripcion: Optional[str] = None
    activo: bool


class CategoriaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: Optional[str] = None
    activo: bool = True


class ZonaOut(ORMModel):
    id_zona: int
    nombre: str
    descripcion: Optional[str] = None
    activo: bool


class ZonaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: Optional[str] = None
    activo: bool = True


class UrgenciaOut(ORMModel):
    id_urgencia: int
    nombre: str
    orden_prioridad: int
    activo: bool


class UrgenciaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    orden_prioridad: int = Field(gt=0)
    activo: bool = True


class EstadoOut(ORMModel):
    id_estado: int
    nombre: str
    descripcion: Optional[str] = None
    es_inicial: bool
    es_final: bool
    activo: bool


class EstadoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    descripcion: Optional[str] = None
    es_inicial: bool = False
    es_final: bool = False
    activo: bool = True


class ActivoIn(BaseModel):
    activo: bool


# ---------------------------------------------------------------- usuarios


class UsuarioBreve(ORMModel):
    id_usuario: int
    nombre: str
    apellido: str


class UsuarioOut(ORMModel):
    id_usuario: int
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str] = None
    fecha_registro: datetime
    es_cliente: bool = False
    es_profesional: bool = False
    es_admin: bool = False
    activo: bool = True


class RegistroIn(BaseModel):
    """Alta de cuenta + usuario + subtipo, todo en una transaccion.

    Un usuario es CLIENTE o PROFESIONAL, no las dos cosas: la app no permite
    tener ambos roles activos al mismo tiempo. Los flags viejos
    (como_cliente/como_profesional) se reemplazaron por un unico campo `rol`.
    """

    username: str = Field(min_length=3, max_length=100)
    # bcrypt no acepta mas de 72 bytes.
    password: str = Field(min_length=8, max_length=72)
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    email: EmailStr
    telefono: Optional[str] = Field(default=None, max_length=30)
    rol: Literal["CLIENTE", "PROFESIONAL"] = "CLIENTE"
    # Solo se usan cuando rol == "PROFESIONAL".
    descripcion_profesional: Optional[str] = None
    categorias: List[int] = Field(default_factory=list)


class UsuarioUpdateIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    email: EmailStr
    telefono: Optional[str] = Field(default=None, max_length=30)


class PasswordUpdateIn(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


# ---------------------------------------------------------------- profesional


class ProfesionalOut(ORMModel):
    id_usuario: int
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str] = None
    descripcion: Optional[str] = None
    disponible: bool
    categorias: List[CategoriaOut] = Field(default_factory=list)
    calificacion_promedio: Optional[float] = None
    trabajos_resueltos: int = 0


class ProfesionalUpdateIn(BaseModel):
    descripcion: Optional[str] = None


class DisponibleIn(BaseModel):
    disponible: bool


class CategoriasIn(BaseModel):
    categorias: List[int]


# ---------------------------------------------------------------- solicitud


class SeguimientoOut(ORMModel):
    id_seguimiento: int
    estado: EstadoOut
    profesional: Optional[UsuarioBreve] = None
    actor: Optional[UsuarioBreve] = None
    fecha_desde: datetime
    fecha_hasta: Optional[datetime] = None
    motivo: Optional[str] = None


class FotoOut(ORMModel):
    id_foto: int
    id_solicitud: int
    tipo_foto: str
    s3_key: str
    nombre_archivo: str
    fecha_subida: datetime
    descripcion: Optional[str] = None
    url: Optional[str] = None


class CalificacionOut(ORMModel):
    id_calificacion: int
    id_solicitud: int
    puntuacion: int
    comentario: Optional[str] = None
    fecha_calificacion: datetime


class SolicitudOut(ORMModel):
    id_solicitud: int
    titulo: str
    descripcion: str
    direccion: str
    fecha_creacion: datetime
    cancelada_por_cliente: bool
    fecha_cancelacion_cliente: Optional[datetime] = None

    categoria: CategoriaOut
    urgencia: UrgenciaOut
    zona: ZonaOut
    cliente: UsuarioBreve

    # Derivados de la fila abierta de seguimiento_solicitud.
    estado: EstadoOut
    profesional: Optional[UsuarioBreve] = None

    calificacion: Optional[CalificacionOut] = None
    fotos: List[FotoOut] = Field(default_factory=list)


class SolicitudIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=150)
    descripcion: str = Field(min_length=1)
    direccion: str = Field(min_length=1, max_length=255)
    id_categoria: int
    id_urgencia: int
    id_zona: int


class AceptarIn(BaseModel):
    motivo: Optional[str] = None


class TransicionIn(BaseModel):
    motivo: Optional[str] = None


class EstadoForzadoIn(BaseModel):
    """Solo admin: transicion arbitraria para arreglar datos."""

    id_estado: int
    id_profesional: Optional[int] = None
    motivo: Optional[str] = None


class CalificacionIn(BaseModel):
    puntuacion: int = Field(ge=1, le=5)
    comentario: Optional[str] = None


class FotoUpdateIn(BaseModel):
    # tipo_foto no esta: lo determina el rol de quien sube la foto.
    descripcion: Optional[str] = None
