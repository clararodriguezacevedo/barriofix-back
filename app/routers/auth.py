"""Registro, login y perfil propio."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_usuario, get_db, usuario_out
from app.models import Categoria, Cliente, Cuenta, Profesional, ProfesionalCategoria, Usuario
from app.schemas import (
    LoginIn,
    PasswordUpdateIn,
    RegistroIn,
    TokenOut,
    UsuarioOut,
    UsuarioUpdateIn,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_para(usuario: Usuario) -> dict:
    return {
        "access_token": create_access_token(
            usuario.id_usuario, usuario.cuenta.username, usuario.cuenta.es_admin
        ),
        "token_type": "bearer",
        "usuario": usuario_out(usuario),
    }


@router.post("/registro", response_model=TokenOut, status_code=201)
def registro(payload: RegistroIn, db: Session = Depends(get_db)):
    """Alta completa en una sola transaccion: cuenta + usuario + subtipos.

    Si algo falla a mitad de camino no queda una cuenta sin usuario ni un
    usuario sin rol: o entra todo o no entra nada.
    """
    # El schema garantiza rol in {CLIENTE, PROFESIONAL}. No hay validacion
    # extra aca: elegir uno es obligatorio y no se pueden combinar.

    cuenta = Cuenta(
        username=payload.username,
        password_hash=hash_password(payload.password),
        activo=True,
        es_admin=False,
    )
    db.add(cuenta)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El nombre de usuario ya esta en uso")

    usuario = Usuario(
        id_cuenta=cuenta.id_cuenta,
        nombre=payload.nombre,
        apellido=payload.apellido,
        email=str(payload.email),
        telefono=payload.telefono,
    )
    db.add(usuario)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ese email ya esta registrado")

    if payload.rol == "CLIENTE":
        db.add(Cliente(id_usuario=usuario.id_usuario))

    if payload.rol == "PROFESIONAL":
        db.add(
            Profesional(
                id_usuario=usuario.id_usuario,
                descripcion=payload.descripcion_profesional,
                disponible=True,
            )
        )
        db.flush()

        if payload.categorias:
            existentes = db.execute(
                select(Categoria.id_categoria).where(
                    Categoria.id_categoria.in_(payload.categorias)
                )
            ).scalars().all()
            faltantes = set(payload.categorias) - set(existentes)
            if faltantes:
                db.rollback()
                raise HTTPException(
                    status_code=422, detail=f"Categorias inexistentes: {sorted(faltantes)}"
                )
            for id_categoria in set(payload.categorias):
                db.add(
                    ProfesionalCategoria(
                        id_profesional=usuario.id_usuario, id_categoria=id_categoria
                    )
                )

    db.commit()
    db.refresh(usuario)
    return _token_para(usuario)


def _autenticar(db: Session, username: str, password: str) -> Usuario:
    cuenta = db.execute(select(Cuenta).where(Cuenta.username == username)).scalar_one_or_none()

    # Mismo mensaje para usuario inexistente y contraseña incorrecta: no le
    # regalamos a nadie la confirmacion de que un usuario existe.
    if cuenta is None or not verify_password(password, cuenta.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    if not cuenta.activo:
        raise HTTPException(status_code=403, detail="La cuenta esta desactivada")

    if cuenta.usuario is None:
        raise HTTPException(status_code=500, detail="La cuenta no tiene usuario asociado")

    return cuenta.usuario


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    """Login con JSON: el que usa el frontend."""
    return _token_para(_autenticar(db, payload.username, payload.password))


@router.post("/token", response_model=TokenOut, include_in_schema=True)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Mismo login pero con form-urlencoded.

    Existe para que el boton "Authorize" de /docs funcione, que es lo que hace
    demostrable la parte de seguridad sin escribir codigo.
    """
    return _token_para(_autenticar(db, form.username, form.password))


@router.get("/me", response_model=UsuarioOut)
def me(usuario: Usuario = Depends(get_current_usuario)):
    return usuario_out(usuario)


@router.put("/me", response_model=UsuarioOut)
def actualizar_me(
    payload: UsuarioUpdateIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    usuario.nombre = payload.nombre
    usuario.apellido = payload.apellido
    usuario.email = str(payload.email)
    usuario.telefono = payload.telefono
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ese email ya es de otro usuario")
    db.refresh(usuario)
    return usuario_out(usuario)


@router.patch("/me/password", status_code=204)
def cambiar_password(
    payload: PasswordUpdateIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password_actual, usuario.cuenta.password_hash):
        raise HTTPException(status_code=403, detail="La contraseña actual no coincide")
    usuario.cuenta.password_hash = hash_password(payload.password_nueva)
    db.commit()
