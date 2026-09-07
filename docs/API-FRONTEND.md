# BarrioFix API — guía para el frontend

> **Contrato v2 (RDS + autenticación).** Reemplaza por completo la versión con datos
> en memoria. Nada de lo anterior sigue vigente: cambiaron los ids, los estados, las
> rutas y ahora todo pide token.

---

## 1. Base URL

```
http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com
```

> ⚠️ Hay un segundo ALB, `barriofix-alb-1097909841`, **muerto**: devuelve `503` en
> todo, incluido `/health`. Un `503` lo genera el ALB, no la app, así que sale sin
> headers CORS y el browser lo reporta como **"CORS error"**. Si ves eso, mirá primero
> el status del preflight antes de tocar nada de CORS.

Solo HTTP, puerto 80. No hay listener 443.

---

## 2. Qué cambió respecto de la versión anterior

| | Antes | Ahora |
|---|---|---|
| Ids | `"BF-1042"` | enteros (`42`) |
| Autenticación | ninguna | **JWT obligatorio** en casi todo |
| Estados | `pendiente`, `en_progreso`, `completado` | `PENDIENTE`, `ASIGNADO`, `EN_PROGRESO`, `RESUELTO`, `CANCELADO` |
| Cliente | string libre (`"Marisol Peña"`) | usuario real, sale del token |
| Zona | no existía | **obligatoria** al crear |
| Categoría / urgencia | string (`"Plomería"`) | id numérico contra catálogo |
| Ruta de solicitudes | `/api/requests` | `/api/solicitudes` |
| Trabajos | `/api/jobs` | `/api/trabajos` |
| Fotos | `/api/media` sobre el bucket entero | `/api/solicitudes/{id}/fotos`, ligadas a una solicitud |

---

## 3. Autenticación

### Registro

```
POST /api/auth/registro
```

```json
{
  "username": "anagomez",
  "password": "mínimo 8 caracteres",
  "nombre": "Ana",
  "apellido": "Gómez",
  "email": "ana@ejemplo.com",
  "telefono": "11 5555 5555",
  "como_cliente": true,
  "como_profesional": false,
  "descripcion_profesional": null,
  "categorias": []
}
```

Un usuario puede ser cliente **y** profesional a la vez. Si `como_profesional` es
`true`, `categorias` es la lista de ids de especialidades.

### Login

```
POST /api/auth/login     → { username, password }        (el que usa el front)
POST /api/auth/token     → form-urlencoded               (para el Authorize de /docs)
```

Los dos devuelven:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "usuario": { "id_usuario": 1, "nombre": "Ana", "es_cliente": true, "es_profesional": false, "es_admin": false, ... }
}
```

### Usar el token

```
Authorization: Bearer <access_token>
```

Dura **12 horas** por defecto. Cuando vence, la API responde `401`: el cliente borra
el token y manda al login.

**Endpoints sin token:** `/health`, `/health/db`, `/`, `/api/auth/registro`,
`/api/auth/login`, `/api/auth/token`, los catálogos (`GET /api/categorias`, `/api/zonas`,
`/api/urgencias`, `/api/estados`) y `GET /api/fotos/{id}/contenido`.

Los catálogos son públicos a propósito: el formulario de registro necesita la lista de
categorías antes de que exista un token. Y el binario de las fotos también, porque el
browser no manda `Authorization` en un `<img src>`.

---

## 4. Máquina de estados

```
PENDIENTE ──aceptar──> ASIGNADO ──iniciar──> EN_PROGRESO ──resolver──> RESUELTO
    │                     │                       │
    └─────────────────────┴───────cancelar────────┴──────────────> CANCELADO
```

| Endpoint | Transición | Quién |
|---|---|---|
| `POST /api/solicitudes/{id}/aceptar` | `PENDIENTE → ASIGNADO` | profesional |
| `POST /api/solicitudes/{id}/iniciar` | `ASIGNADO → EN_PROGRESO` | el profesional asignado |
| `POST /api/solicitudes/{id}/resolver` | `EN_PROGRESO → RESUELTO` | el profesional asignado |
| `POST /api/solicitudes/{id}/cancelar` | `* → CANCELADO` | el cliente dueño |

Body opcional: `{ "motivo": "texto" }`. Todos devuelven la **solicitud completa
actualizada** — usala directo para actualizar el estado local en vez de refetchear.

Una transición inválida devuelve **`409`** con el motivo. `409` al aceptar es normal y
esperable: otro profesional la tomó primero.

---

## 5. Endpoints del flujo de usuario

### Catálogos (para llenar los selects)

```
GET /api/categorias?activo=true     → [{ id_categoria, nombre, descripcion, activo }]
GET /api/zonas?activo=true          → [{ id_zona, nombre, ... }]
GET /api/urgencias?activo=true      → [{ id_urgencia, nombre, orden_prioridad, ... }]
```

### Solicitudes

```
GET    /api/solicitudes?estado=&id_categoria=&id_zona=&id_urgencia=&mias=&asignadas=
GET    /api/solicitudes/{id}
POST   /api/solicitudes                        → 201
PUT    /api/solicitudes/{id}                   → solo mientras esté PENDIENTE
GET    /api/solicitudes/{id}/seguimiento       → historial completo
```

`mias=true` filtra las que creaste como cliente; `asignadas=true`, las que tenés como
profesional.

Body de `POST` / `PUT`:

```json
{
  "titulo": "Pérdida de agua bajo la pileta",
  "descripcion": "Gotea cada vez que se usa.",
  "direccion": "Los Aromos 214",
  "id_categoria": 1,
  "id_urgencia": 3,
  "id_zona": 1
}
```

### Trabajos disponibles (profesional)

```
GET /api/trabajos?id_zona=&id_urgencia=&todas_las_categorias=
```

Devuelve las `PENDIENTE` **filtradas por las especialidades del profesional**.
`todas_las_categorias=true` levanta ese filtro.

### Fotos

```
GET    /api/solicitudes/{id}/fotos
POST   /api/solicitudes/{id}/fotos     multipart: archivo, tipo_foto, descripcion
GET    /api/fotos/{id}/contenido       binario, sin token → va en <img src>
PATCH  /api/fotos/{id}
DELETE /api/fotos/{id}                 borra la fila Y el objeto de S3
```

`tipo_foto` ∈ `ANTES` · `DESPUES` · `OTRA`. Máximo 10 MB.

**No armes la URL a mano** con `s3_key`: usá `/api/fotos/{id}/contenido`. El campo `url`
de la respuesta ya trae esa ruta.

### Calificación

```
GET  /api/solicitudes/{id}/calificacion
POST /api/solicitudes/{id}/calificacion    { puntuacion: 1-5, comentario }
PUT  /api/calificaciones/{id}
GET  /api/profesionales/{id}/calificaciones
```

Solo el cliente dueño, solo si está `RESUELTO`, y **una sola vez** (`409` si ya existe).

### Perfil y profesionales

```
GET   /api/auth/me
PUT   /api/auth/me
PATCH /api/auth/me/password
POST  /api/usuarios/{id}/profesional          alta como profesional
GET   /api/profesionales?id_categoria=&disponible=
GET   /api/profesionales/{id}                 incluye promedio y trabajos resueltos
PUT   /api/profesionales/{id}
PATCH /api/profesionales/{id}/disponible
GET   /api/profesionales/{id}/categorias
PUT   /api/profesionales/{id}/categorias      reemplaza el set completo
```

---

## 6. Forma de una solicitud

```ts
type Solicitud = {
  id_solicitud: number
  titulo: string
  descripcion: string
  direccion: string
  fecha_creacion: string          // ISO 8601 con timezone
  cancelada_por_cliente: boolean
  fecha_cancelacion_cliente: string | null

  categoria: { id_categoria: number; nombre: string; descripcion: string | null; activo: boolean }
  urgencia:  { id_urgencia: number; nombre: string; orden_prioridad: number; activo: boolean }
  zona:      { id_zona: number; nombre: string; descripcion: string | null; activo: boolean }
  cliente:   { id_usuario: number; nombre: string; apellido: string }

  // Derivados del seguimiento abierto, no son columnas de la tabla.
  estado:      { id_estado: number; nombre: string; es_inicial: boolean; es_final: boolean; activo: boolean }
  profesional: { id_usuario: number; nombre: string; apellido: string } | null

  calificacion: { id_calificacion: number; puntuacion: number; comentario: string | null; fecha_calificacion: string } | null
  fotos: Array<{ id_foto: number; tipo_foto: string; s3_key: string; nombre_archivo: string; url: string; ... }>
}
```

`estado` y `profesional` vienen como **objetos anidados**, no strings. Para mostrar el
estado usá `solicitud.estado.nombre`.

---

## 7. Errores

```json
{ "detail": "La solicitud ya esta en estado final (RESUELTO)" }
```

En los `422` de validación, `detail` es un **array** de objetos Pydantic, no un string.
Hay que contemplar los dos casos al mostrar el mensaje.

| Status | Cuándo |
|---|---|
| `401` | falta el token, o venció → borrar token y mandar al login |
| `403` | autenticado pero sin permiso (rol equivocado, recurso de otro) |
| `404` | no existe |
| `409` | choca con una regla de negocio: transición inválida, ya calificada, trabajo ya tomado, catálogo en uso |
| `413` | foto de más de 10 MB |
| `422` | body inválido |
| `502` | el backend no pudo hablar con S3 |
| `503` | **no llegaste a la app**: el ALB no tiene targets healthy |

---

## 8. Trampas

**No hay más estado en memoria compartido entre instancias.** Con RDS, las dos
instancias del ASG ven exactamente lo mismo. El problema de "creo algo y no aparece" de
la versión anterior desapareció.

**`zona` es obligatoria.** El formulario tiene que pedirla o el `POST` devuelve `422`.

**La barra final sigue rompiendo.** `/api/solicitudes/` devuelve `307`. Nunca la pongas.

**Los ids son números.** Si el front hace `String(id)` o los usa como clave de objeto,
funciona igual; si los compara con `===` contra un string, no.

---

## 9. Docs interactiva

```
http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com/docs
```

El botón **Authorize** funciona: usa `POST /api/auth/token`. Es la forma más rápida de
probar el flujo completo sin escribir una línea de código, y sirve para la demo.
