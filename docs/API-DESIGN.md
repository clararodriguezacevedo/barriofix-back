# BarrioFix — Diseño de endpoints (ABM completo sobre el esquema RDS)

Derivado del DDL de las 13 tablas. Cada endpoint indica las reglas de negocio que
tiene que hacer cumplir y quién lo consume.

**Leyenda de consumidor:**

- 🟢 **FRONT** — lo usa la app en el flujo real de un usuario
- 🔧 **ADMIN** — backoffice / carga inicial / moderación; no lo toca el usuario final
- ⚙️ **INTERNO** — lo usa otro endpoint, no se expone

---

## 0. Reglas transversales

### 0.1 La máquina de estados

```
                    ┌──────────────┐
                    │  PENDIENTE   │  (es_inicial)
                    └──────┬───────┘
                           │ aceptar (profesional)
                           ▼
                    ┌──────────────┐
                    │   ASIGNADO   │
                    └──────┬───────┘
                           │ iniciar (profesional)
                           ▼
                    ┌──────────────┐
                    │ EN_PROGRESO  │
                    └──────┬───────┘
                           │ resolver (profesional)
                           ▼
                    ┌──────────────┐
                    │   RESUELTO   │  (es_final)
                    └──────────────┘

  PENDIENTE ─┐
  ASIGNADO ──┼── cancelar (cliente) ──> CANCELADO  (es_final)
  EN_PROGRESO┘
```

Desde un estado `es_final` no sale ninguna transición. Todo endpoint que cambie de
estado tiene que rechazar con `409` si el estado actual no lo permite.

### 0.2 Las cinco transacciones atómicas

Estas operaciones tocan más de una tabla y **fallan a medias si no van en una sola
transacción**. Es el corazón de la consistencia que pide la consigna.

| Operación | Tablas que toca |
|---|---|
| Registrar usuario | `cuenta` + `usuario` + (`cliente` y/o `profesional`) |
| Crear solicitud | `solicitud` + `seguimiento_solicitud` (fila inicial) |
| Cambiar de estado | `seguimiento_solicitud` (cerrar la abierta + abrir la nueva) |
| Cancelar solicitud | `solicitud` (2 columnas) + `seguimiento_solicitud` (transición) |
| Subir foto | S3 (objeto) + `foto_solicitud` (fila) |

### 0.3 ⚠️ La trampa de `fecha_hasta > fecha_desde`

El `CHECK ck_seguimiento_fechas` exige **estrictamente mayor**. Y en PostgreSQL
`CURRENT_TIMESTAMP` devuelve el **inicio de la transacción**, no el instante actual.

Consecuencia: si en una misma transacción cerrás una fila que se creó en esa misma
transacción, `fecha_hasta` sale **igual** a `fecha_desde` y el CHECK explota.

Pasa concretamente si alguien crea una solicitud y la acepta en la misma transacción.
La solución es usar `clock_timestamp()` (instante real) en lugar de `CURRENT_TIMESTAMP`
al cerrar:

```sql
UPDATE seguimiento_solicitud
   SET fecha_hasta = clock_timestamp()
 WHERE id_solicitud = :id AND fecha_hasta IS NULL;
```

### 0.4 ⚠️ Concurrencia al aceptar un trabajo

Es el caso que justifica RDS en el documento de arquitectura: dos profesionales
aceptando la misma solicitud al mismo tiempo.

El índice parcial único `uq_seguimiento_actual_solicitud` ya impide que existan dos
filas abiertas para la misma solicitud, así que **la base rechaza al segundo** aunque
la app no haga nada. Pero el error que sale es un `UniqueViolation` feo. Para dar un
`409` limpio, tomá el lock explícito primero:

```sql
SELECT id_solicitud FROM solicitud WHERE id_solicitud = :id FOR UPDATE;
```

Con eso el segundo profesional espera, lee el estado ya actualizado y recibe
`409 "La solicitud ya fue asignada"`.

### 0.5 Borrado: `DELETE` real vs baja lógica

| Entidad | Qué hace un `DELETE` | Por qué |
|---|---|---|
| `categoria`, `zona`, `urgencia`, `estado` | `409` si está en uso | FK `ON DELETE RESTRICT` |
| `cuenta`, `usuario` | `409` si tiene solicitudes | FK `ON DELETE RESTRICT` desde `solicitud` |
| `solicitud` | Borra en cascada seguimiento, fotos y calificación | `ON DELETE CASCADE` |
| `profesional`, `cliente` | Cascada desde `usuario` | `ON DELETE CASCADE` |
| `seguimiento_solicitud` | **Nunca se borra** | Es la auditoría del trabajo |

Por eso todos los catálogos tienen `activo`: la baja normal es
`PATCH .../activo` con `false`, no `DELETE`.

> ⚠️ `DELETE /api/solicitudes/{id}` borra las filas de `foto_solicitud` en cascada
> pero **no toca S3**. Hay que borrar los objetos antes, o quedan huérfanos pagando
> almacenamiento sin que nada los referencie.

---

## 1. Catálogos

Mismo patrón para `categoria`, `zona` y `urgencia`. Abajo con `categorias`;
`zonas` y `urgencias` son idénticos salvo los campos propios.

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/categorias?activo=true` | Lista | Default `activo=true` | 🟢 FRONT |
| `GET` | `/api/categorias/{id}` | Una | `404` si no existe | 🔧 ADMIN |
| `POST` | `/api/categorias` | Crea | `409` si `nombre` repetido | 🔧 ADMIN |
| `PUT` | `/api/categorias/{id}` | Reemplaza | `409` si `nombre` colisiona | 🔧 ADMIN |
| `PATCH` | `/api/categorias/{id}/activo` | Baja/alta lógica | — | 🔧 ADMIN |
| `DELETE` | `/api/categorias/{id}` | Borra de verdad | `409` si alguna solicitud la usa | 🔧 ADMIN |

**`urgencia`** agrega: `orden_prioridad` es `UNIQUE` y `> 0`. Reordenar dos urgencias
intercambiando valores choca con el UNIQUE en el paso intermedio → hacelo en una
transacción con un valor temporal, o usá `DEFERRABLE`.

**`zona`** no tiene reglas extra.

### 1.1 `estado` — catálogo especial

Todo el ciclo de vida de la app depende de estas 5 filas. **No lo toca el front.**

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/estados` | Lista los 5 | — | 🔧 ADMIN |
| `POST` | `/api/estados` | Crea | `es_inicial` y `es_final` no pueden ser ambos `true`; solo **un** `es_inicial=true` en toda la tabla (índice parcial único) | 🔧 ADMIN |
| `PUT` | `/api/estados/{id}` | Reemplaza | Ídem; marcar uno como inicial exige desmarcar el anterior en la misma transacción | 🔧 ADMIN |
| `DELETE` | `/api/estados/{id}` | Borra | `409` casi siempre: `seguimiento` lo referencia con RESTRICT | 🔧 ADMIN |

---

## 2. Cuenta y usuario

`cuenta` 1:1 `usuario` (por el `UNIQUE(id_cuenta)`). Nunca se crean por separado.

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `POST` | `/api/usuarios` | **Registro**: crea `cuenta` + `usuario` + subtipo | Una transacción. `409` si `username` o `email` repetidos. El body dice si es cliente, profesional o ambos | 🟢 FRONT |
| `GET` | `/api/usuarios/{id}` | Perfil | Sin `password_hash` en la respuesta, nunca | 🟢 FRONT |
| `PUT` | `/api/usuarios/{id}` | Edita nombre, apellido, email, teléfono | `409` si el email ya es de otro | 🟢 FRONT |
| `PATCH` | `/api/usuarios/{id}/password` | Cambia contraseña | Pide la actual; guarda **hash**, nunca texto plano | 🟢 FRONT |
| `GET` | `/api/usuarios?rol=&activo=` | Listado con filtros | Paginado | 🔧 ADMIN |
| `PATCH` | `/api/usuarios/{id}/activo` | Baja lógica de la cuenta | Es la baja **real** que se usa: preserva el historial | 🔧 ADMIN |
| `DELETE` | `/api/usuarios/{id}` | Borra de verdad | `409` si tiene solicitudes (RESTRICT). Cascadea `cliente`/`profesional` | 🔧 ADMIN |

> Un mismo `usuario` puede ser cliente **y** profesional a la vez: el esquema no lo
> impide y las dos tablas apuntan a `usuario`. Decidí si la app lo permite.

### 2.1 Subtipos

| Método | Path | Qué hace | Consumidor |
|---|---|---|---|
| `POST` | `/api/usuarios/{id}/cliente` | Lo habilita como cliente | 🔧 ADMIN |
| `DELETE` | `/api/usuarios/{id}/cliente` | Lo deshabilita | `409` si tiene solicitudes · 🔧 ADMIN |
| `POST` | `/api/usuarios/{id}/profesional` | Alta como profesional | 🟢 FRONT |
| `DELETE` | `/api/usuarios/{id}/profesional` | Baja como profesional | `409` si tiene trabajos asignados · 🔧 ADMIN |

---

## 3. Profesional

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/profesionales?categoria=&disponible=` | Lista con filtros | Join con `profesional_categoria` | 🟢 FRONT |
| `GET` | `/api/profesionales/{id}` | Ficha: datos + categorías + promedio de calificaciones | El promedio sale de `calificacion` vía `solicitud`+`seguimiento` | 🟢 FRONT |
| `PUT` | `/api/profesionales/{id}` | Edita `descripcion` | — | 🟢 FRONT |
| `PATCH` | `/api/profesionales/{id}/disponible` | Se marca (no) disponible | No afecta trabajos ya asignados | 🟢 FRONT |

### 3.1 `profesional_categoria` (N:M)

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/profesionales/{id}/categorias` | Sus especialidades | — | 🟢 FRONT |
| `PUT` | `/api/profesionales/{id}/categorias` | **Reemplaza el set completo** | Body: array de ids. Una transacción: borra las que sobran, inserta las nuevas | 🟢 FRONT |
| `POST` | `/api/profesionales/{id}/categorias/{id_categoria}` | Agrega una | `409` si ya está (PK compuesta) | 🟢 FRONT |
| `DELETE` | `/api/profesionales/{id}/categorias/{id_categoria}` | Saca una | `404` si no la tenía | 🟢 FRONT |

> El `PUT` que reemplaza todo es el que conviene para una pantalla de perfil con
> checkboxes: una sola llamada, sin estados intermedios raros si el usuario tilda y
> destilda varias.

---

## 4. Solicitud

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/solicitudes?estado=&categoria=&zona=&urgencia=&cliente=&profesional=` | Lista | El filtro por `estado`/`profesional` va contra la fila abierta de `seguimiento` | 🟢 FRONT |
| `GET` | `/api/solicitudes/{id}` | Detalle completo con estado, profesional, fotos y calificación | — | 🟢 FRONT |
| `POST` | `/api/solicitudes` | Crea | **Transacción**: inserta `solicitud` + fila de `seguimiento` con el estado `es_inicial`. `422` si categoría/zona/urgencia no existen o están inactivas | 🟢 FRONT |
| `PUT` | `/api/solicitudes/{id}` | Edita título, descripción, dirección, categoría, urgencia, zona | **`409` si el estado actual no es `PENDIENTE`**: una vez que un profesional la aceptó, no se le puede cambiar el trabajo abajo de los pies | 🟢 FRONT |
| `DELETE` | `/api/solicitudes/{id}` | Borra de verdad | Cascadea seguimiento, fotos y calificación. **Borrar los objetos de S3 primero.** El usuario normal cancela, no borra | 🔧 ADMIN |

### 4.1 Transiciones de estado

Todas: cierran la fila abierta con `clock_timestamp()` e insertan la nueva, en una
transacción, tomando `FOR UPDATE` sobre la solicitud.

| Método | Path | Transición | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/solicitudes/{id}/seguimiento` | — | Historial completo ordenado por `fecha_desde` | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/aceptar` | `PENDIENTE → ASIGNADO` | Body: `id_profesional`. `409` si ya no está pendiente. Graba `id_profesional` en la fila nueva | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/iniciar` | `ASIGNADO → EN_PROGRESO` | `403` si lo pide otro profesional | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/resolver` | `EN_PROGRESO → RESUELTO` | Habilita la calificación | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/cancelar` | `* → CANCELADO` | **Transacción**: además setea `cancelada_por_cliente=true` **y** `fecha_cancelacion_cliente` — el CHECK exige que vayan juntos. `409` si ya está en estado final | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/estado` | Cualquiera → cualquiera | Escape hatch para arreglar datos a mano. Salteá las validaciones de la máquina de estados, pero **nunca** el índice parcial único | 🔧 ADMIN |

> No hay `DELETE` de seguimiento a propósito: es el registro de auditoría del trabajo.
> Corregir un error se hace con una transición nueva y `motivo`, no borrando historia.

### 4.2 Vista derivada: trabajos disponibles

| Método | Path | Qué hace | Consumidor |
|---|---|---|---|
| `GET` | `/api/trabajos?id_profesional=&zona=&urgencia=` | Solicitudes `PENDIENTE` filtradas por las **categorías del profesional** | 🟢 FRONT |

Es la pantalla principal del profesional. No es una tabla: es un query sobre
`solicitud` + `seguimiento` (abierto, estado inicial) + `profesional_categoria`.

---

## 5. Fotos

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/solicitudes/{id}/fotos` | Metadata de las fotos | — | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/fotos` | Sube a S3 + inserta fila | `multipart/form-data`. **Subí a S3 primero, insertá después**: si falla el insert borrás el objeto; al revés te queda una fila apuntando a nada. `tipo_foto` ∈ `ANTES`/`DESPUES`/`OTRA` | 🟢 FRONT |
| `GET` | `/api/fotos/{id}/contenido` | Devuelve el binario desde S3 | Sirve para `<img src>` | 🟢 FRONT |
| `PATCH` | `/api/fotos/{id}` | Edita `descripcion` y `tipo_foto` | El `s3_key` **no** se edita: es `UNIQUE` y apunta al objeto real | 🟢 FRONT |
| `DELETE` | `/api/fotos/{id}` | Borra fila **y objeto de S3** | Si solo borrás la fila, el objeto queda huérfano | 🟢 FRONT |

> `s3_key` es `UNIQUE`: generá la key con algo único (`solicitudes/{id}/{uuid}-{nombre}`),
> no con el nombre del archivo. Dos usuarios subiendo `foto.jpg` chocarían.

---

## 6. Calificación

| Método | Path | Qué hace | Reglas | Consumidor |
|---|---|---|---|---|
| `GET` | `/api/solicitudes/{id}/calificacion` | La calificación (o `404`) | — | 🟢 FRONT |
| `POST` | `/api/solicitudes/{id}/calificacion` | Califica | `409` si el estado actual no es `RESUELTO`. `409` si ya existe (`UNIQUE(id_solicitud)`). `puntuacion` 1–5 o `422` | 🟢 FRONT |
| `PUT` | `/api/calificaciones/{id}` | Edita puntuación y comentario | Decidí si hay ventana de tiempo | 🟢 FRONT |
| `DELETE` | `/api/calificaciones/{id}` | Borra | Moderación de comentarios abusivos | 🔧 ADMIN |
| `GET` | `/api/profesionales/{id}/calificaciones` | Todas las de un profesional + promedio | Join `calificacion`→`solicitud`→`seguimiento` | 🟢 FRONT |

> La calificación **no guarda** `id_cliente` ni `id_profesional`: salen de `solicitud`
> y de la fila de `seguimiento` donde se asignó. Ese join es obligatorio para saber a
> quién califica.

---

## 7. Resumen: qué usa el front y qué queda para admin

### 🟢 FRONT — flujo real (28 endpoints)

**Registro y perfil**

```
POST   /api/usuarios
GET    /api/usuarios/{id}
PUT    /api/usuarios/{id}
PATCH  /api/usuarios/{id}/password
POST   /api/usuarios/{id}/profesional
```

**Catálogos (para llenar los selects del formulario)**

```
GET    /api/categorias?activo=true
GET    /api/zonas?activo=true
GET    /api/urgencias?activo=true
```

**Profesional**

```
GET    /api/profesionales?categoria=&disponible=
GET    /api/profesionales/{id}
PUT    /api/profesionales/{id}
PATCH  /api/profesionales/{id}/disponible
GET    /api/profesionales/{id}/categorias
PUT    /api/profesionales/{id}/categorias
POST   /api/profesionales/{id}/categorias/{id_categoria}
DELETE /api/profesionales/{id}/categorias/{id_categoria}
GET    /api/profesionales/{id}/calificaciones
```

**Solicitudes**

```
GET    /api/solicitudes?...
GET    /api/solicitudes/{id}
POST   /api/solicitudes
PUT    /api/solicitudes/{id}
GET    /api/solicitudes/{id}/seguimiento
POST   /api/solicitudes/{id}/aceptar
POST   /api/solicitudes/{id}/iniciar
POST   /api/solicitudes/{id}/resolver
POST   /api/solicitudes/{id}/cancelar
GET    /api/trabajos?id_profesional=
```

**Fotos y calificación**

```
GET    /api/solicitudes/{id}/fotos
POST   /api/solicitudes/{id}/fotos
GET    /api/fotos/{id}/contenido
PATCH  /api/fotos/{id}
DELETE /api/fotos/{id}
GET    /api/solicitudes/{id}/calificacion
POST   /api/solicitudes/{id}/calificacion
PUT    /api/calificaciones/{id}
```

### 🔧 ADMIN — backoffice

```
# Catálogos: ABM completo × 3 (categorias, zonas, urgencias)
GET/POST/PUT/PATCH/DELETE  /api/categorias[/{id}[/activo]]
GET/POST/PUT/PATCH/DELETE  /api/zonas[/{id}[/activo]]
GET/POST/PUT/PATCH/DELETE  /api/urgencias[/{id}[/activo]]

# Estados: solo admin, nunca el front
GET/POST/PUT/DELETE        /api/estados[/{id}]

# Usuarios
GET     /api/usuarios?rol=&activo=
PATCH   /api/usuarios/{id}/activo
DELETE  /api/usuarios/{id}
POST    /api/usuarios/{id}/cliente
DELETE  /api/usuarios/{id}/cliente
DELETE  /api/usuarios/{id}/profesional

# Solicitudes: borrado real y transición forzada
DELETE  /api/solicitudes/{id}
POST    /api/solicitudes/{id}/estado

# Moderación
DELETE  /api/calificaciones/{id}
```

**El corte no es arbitrario.** Lo que queda del lado admin es exactamente lo que puede
romper consistencia si lo toca un usuario final: borrados reales que cascadean,
transiciones que saltean la máquina de estados, y los catálogos de los que dependen
todas las solicitudes existentes.

---

## 8. Lo que hay que decidir antes de implementar

Tres cosas donde el esquema nuevo no encaja con lo que el frontend manda hoy:

1. **`zona` es `NOT NULL` en `solicitud`, pero el formulario actual no la pide.**
   O se agrega el campo al form, o se crea una zona `"Sin especificar"` como fallback.

2. **`id_cliente` es una FK, pero hoy el front manda `cliente` como texto libre**
   (`"Marisol Peña"`). Sin login no hay forma de saber qué usuario es. Hace falta
   autenticación, o un cliente de demo fijo.

3. **Los ids pasan de `"BF-1042"` a enteros.** Si el front los trata como opacos no
   pasa nada; si los parsea o los muestra, hay que decidir si se sigue exponiendo el
   formato `BF-<id>` o se rompe el contrato.
