"""Modelos SQLAlchemy mapeados al esquema que ya existe en RDS.

Las tablas se crean con el DDL de migrations/, NUNCA con create_all(): el
esquema real tiene indices parciales unicos y CHECKs que SQLAlchemy no
reproduce. Estos modelos solo describen lo que ya esta ahi.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Cuenta(Base):
    __tablename__ = "cuenta"

    id_cuenta = Column(BigInteger, primary_key=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    # Agregada por migrations/001_add_admin_flag.sql
    es_admin = Column(Boolean, nullable=False, default=False)
    fecha_creacion = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

    usuario = relationship("Usuario", back_populates="cuenta", uselist=False)


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario = Column(BigInteger, primary_key=True)
    id_cuenta = Column(BigInteger, ForeignKey("cuenta.id_cuenta"), nullable=False, unique=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    telefono = Column(String(30))
    fecha_registro = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

    cuenta = relationship("Cuenta", back_populates="usuario")
    cliente = relationship("Cliente", back_populates="usuario", uselist=False, cascade="all, delete-orphan")
    profesional = relationship("Profesional", back_populates="usuario", uselist=False, cascade="all, delete-orphan")


class Cliente(Base):
    __tablename__ = "cliente"

    id_usuario = Column(BigInteger, ForeignKey("usuario.id_usuario"), primary_key=True)

    usuario = relationship("Usuario", back_populates="cliente")


class Profesional(Base):
    __tablename__ = "profesional"

    id_usuario = Column(BigInteger, ForeignKey("usuario.id_usuario"), primary_key=True)
    descripcion = Column(Text)
    disponible = Column(Boolean, nullable=False, default=True)

    usuario = relationship("Usuario", back_populates="profesional")
    categorias = relationship(
        "Categoria",
        secondary="profesional_categoria",
        back_populates="profesionales",
    )


class Categoria(Base):
    __tablename__ = "categoria"

    id_categoria = Column(BigInteger, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text)
    activo = Column(Boolean, nullable=False, default=True)

    profesionales = relationship(
        "Profesional",
        secondary="profesional_categoria",
        back_populates="categorias",
    )


class ProfesionalCategoria(Base):
    __tablename__ = "profesional_categoria"

    id_profesional = Column(BigInteger, ForeignKey("profesional.id_usuario"), primary_key=True)
    id_categoria = Column(BigInteger, ForeignKey("categoria.id_categoria"), primary_key=True)


class Zona(Base):
    __tablename__ = "zona"

    id_zona = Column(BigInteger, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text)
    activo = Column(Boolean, nullable=False, default=True)


class Urgencia(Base):
    __tablename__ = "urgencia"

    id_urgencia = Column(BigInteger, primary_key=True)
    nombre = Column(String(50), nullable=False, unique=True)
    orden_prioridad = Column(SmallInteger, nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)


class Estado(Base):
    __tablename__ = "estado"

    id_estado = Column(BigInteger, primary_key=True)
    nombre = Column(String(50), nullable=False, unique=True)
    descripcion = Column(Text)
    # Indice parcial unico en la base: solo UNA fila puede tener es_inicial=TRUE.
    es_inicial = Column(Boolean, nullable=False, default=False)
    es_final = Column(Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)


class Solicitud(Base):
    __tablename__ = "solicitud"

    id_solicitud = Column(BigInteger, primary_key=True)
    id_cliente = Column(BigInteger, ForeignKey("cliente.id_usuario"), nullable=False)
    id_categoria = Column(BigInteger, ForeignKey("categoria.id_categoria"), nullable=False)
    id_urgencia = Column(BigInteger, ForeignKey("urgencia.id_urgencia"), nullable=False)
    id_zona = Column(BigInteger, ForeignKey("zona.id_zona"), nullable=False)

    titulo = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=False)
    direccion = Column(String(255), nullable=False)

    fecha_creacion = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

    # El CHECK ck_solicitud_cancelacion exige que estas dos vayan siempre juntas.
    cancelada_por_cliente = Column(Boolean, nullable=False, default=False)
    fecha_cancelacion_cliente = Column(DateTime(timezone=True))

    cliente = relationship("Cliente")
    categoria = relationship("Categoria")
    urgencia = relationship("Urgencia")
    zona = relationship("Zona")
    seguimiento = relationship(
        "SeguimientoSolicitud",
        back_populates="solicitud",
        cascade="all, delete-orphan",
        order_by="SeguimientoSolicitud.fecha_desde",
    )
    fotos = relationship("FotoSolicitud", back_populates="solicitud", cascade="all, delete-orphan")
    calificacion = relationship(
        "Calificacion", back_populates="solicitud", uselist=False, cascade="all, delete-orphan"
    )


class SeguimientoSolicitud(Base):
    """Historial de estados. La fila con fecha_hasta IS NULL es el estado actual.

    Un indice parcial unico en la base garantiza que solo puede haber una fila
    abierta por solicitud: es lo que impide que dos profesionales acepten el
    mismo trabajo.
    """

    __tablename__ = "seguimiento_solicitud"

    id_seguimiento = Column(BigInteger, primary_key=True)
    id_solicitud = Column(BigInteger, ForeignKey("solicitud.id_solicitud"), nullable=False)
    id_estado = Column(BigInteger, ForeignKey("estado.id_estado"), nullable=False)

    id_profesional = Column(BigInteger, ForeignKey("profesional.id_usuario"))
    id_usuario_actor = Column(BigInteger, ForeignKey("usuario.id_usuario"))

    fecha_desde = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    fecha_hasta = Column(DateTime(timezone=True))

    motivo = Column(Text)

    solicitud = relationship("Solicitud", back_populates="seguimiento")
    estado = relationship("Estado")
    profesional = relationship("Profesional")
    actor = relationship("Usuario")


class FotoSolicitud(Base):
    __tablename__ = "foto_solicitud"

    id_foto = Column(BigInteger, primary_key=True)
    id_solicitud = Column(BigInteger, ForeignKey("solicitud.id_solicitud"), nullable=False)
    id_usuario_carga = Column(BigInteger, ForeignKey("usuario.id_usuario"), nullable=False)

    tipo_foto = Column(String(10), nullable=False)

    # El archivo real vive en S3; aca solo la referencia.
    s3_key = Column(String(1024), nullable=False, unique=True)
    nombre_archivo = Column(String(255), nullable=False)

    fecha_subida = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    descripcion = Column(Text)

    solicitud = relationship("Solicitud", back_populates="fotos")


class Calificacion(Base):
    __tablename__ = "calificacion"

    id_calificacion = Column(BigInteger, primary_key=True)
    id_solicitud = Column(BigInteger, ForeignKey("solicitud.id_solicitud"), nullable=False, unique=True)

    puntuacion = Column(SmallInteger, nullable=False)
    comentario = Column(Text)
    fecha_calificacion = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

    solicitud = relationship("Solicitud", back_populates="calificacion")
