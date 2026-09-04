# BarrioFix API — guía para el frontend

Todo lo de acá está verificado contra el backend desplegado el 2026-09-04.

---

## 1. Base URL

```
http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com
```

> ⚠️ **Hay un segundo ALB, `barriofix-alb-1097909841`, que está MUERTO.**
> Devuelve `503` en absolutamente todo, incluido `/health`. Si el frontend le pega a ese,
> el browser muestra **"CORS error"** en la consola — pero el problema no es CORS: un `503`
> lo genera el ALB, no la app, así que la respuesta sale sin headers CORS y el browser lo
> etiqueta mal. Si ves "CORS error", **lo primero es mirar el status del preflight**.
>
> Regla rápida para distinguirlos: el ALB vivo termina en `793636717`.

Verificación de un vistazo:

```bash
curl.exe http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com/health
```

Tiene que devolver `{"status":"ok"}`. Si devuelve `503`, el problema es de infra
(targets unhealthy), no del frontend — no toques el código, avisá.

### HTTP, no HTTPS

El ALB solo escucha en **puerto 80 / HTTP**. No hay certificado.
Como el frontend también se sirve por HTTP desde el website endpoint de S3, no hay
problema de *mixed content*. Pero si algún día el frontend pasa a HTTPS (CloudFront,
por ejemplo), el browser va a bloquear todas estas llamadas por ser HTTP.

---

## 2. CORS

El backend acepta requests **solo** desde este origen exacto:

```
http://barriofix-frontend-clara.s3-website-us-east-1.amazonaws.com
```

Implicancias prácticas:

- Abrir el frontend desde `localhost` **no va a funcionar** contra este backend.
  Si lo necesitás para desarrollo, pedí que agreguen tu origen a la lista.
- La URL tiene que coincidir **carácter por carácter** con la barra del browser.
  `s3-website-us-east-1` (con guión) y `s3-website.us-east-1` (con punto) son
  ambas válidas en AWS pero son **orígenes distintos** para CORS. Usá la que te
  muestra la consola de S3.
- `allow_credentials` está en `true`, así que podés mandar cookies si alguna vez hace
  falta. Hoy no hay autenticación, así que no mandes `credentials: "include"` sin motivo.

---

## 3. Endpoints

Todas las respuestas son JSON. No hay autenticación: no mandes `Authorization`.

### Salud

| Método | Path | Respuesta |
|---|---|---|
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/` | `{"message":"BarrioFix Backend - Servidor funcionando correctamente"}` |

`/health` lo usa el Target Group del ALB. No lo uses para lógica de negocio.

### Solicitudes

| Método | Path | Body | Devuelve |
|---|---|---|---|
| `GET` | `/api/requests` | — | array de solicitudes |
| `GET` | `/api/requests?categoria=X&estado=Y` | — | array filtrado |
| `GET` | `/api/requests/{id}` | — | una solicitud, o `404` |
| `POST` | `/api/requests` | `NewRequest` | la solicitud creada, **`201`** |
| `PATCH` | `/api/requests/{id}/accept` | `{"profesional": "..."}` | la solicitud actualizada |
| `PATCH` | `/api/requests/{id}/status` | `{"estado": "..."}` | la solicitud actualizada |
| `POST` | `/api/requests/{id}/rate` | `{"rating": 5, "comentario": "..."}` | la solicitud actualizada |

`POST /api/requests` devuelve **201**, no 200. Si chequeás `res.status === 200` te va a
fallar. Usá `res.ok`.

Body de `NewRequest` — los seis campos son **obligatorios**, si falta uno devuelve `422`:

```json
{
  "titulo": "Pérdida de agua bajo la pileta",
  "categoria": "Plomería",
  "direccion": "Calle Los Aromos 214, Villa Alegre",
  "descripcion": "Gotea agua debajo de la bacha.",
  "urgencia": "Alta",
  "cliente": "Marisol Peña"
}
```

El backend le agrega solo: `id`, `profesional` (`null`), `estado` (`"pendiente"`),
`rating` (`null`), `comentario` (`""`), `creado`, `fotos` (`[]`).

`PATCH .../accept` además de asignar el profesional pone `estado` en `"en_progreso"`
automáticamente. No hace falta llamar a `/status` después.

`comentario` en `rate` es opcional (default `""`); `rating` es obligatorio y es un entero.

### Trabajos disponibles

| Método | Path | Devuelve |
|---|---|---|
| `GET` | `/api/jobs` | solicitudes con `estado == "pendiente"` |
| `GET` | `/api/jobs?categoria=X&urgencia=Y` | ídem, filtrado |

Es una vista de solo lectura sobre las mismas solicitudes — no es una entidad aparte.
`GET /api/jobs` ≡ `GET /api/requests?estado=pendiente`.

### Media (S3)

| Método | Path | Devuelve |
|---|---|---|
| `GET` | `/api/media` | array de `{key, size, last_modified}` |
| `GET` | `/api/media?prefix=fotos/` | ídem, filtrado por prefijo |
| `GET` | `/api/media/{key}` | el archivo binario, con su `Content-Type` |

Respuesta real del bucket hoy:

```json
[
  {"key":"WhatsApp Image 2020-12-09 at 10.13.55 PM.jpeg","size":169695,"last_modified":"2026-09-04T05:32:28+00:00"},
  {"key":"WhatsApp Image 2020-12-15 at 12.05.22 AM.jpeg","size":163999,"last_modified":"2026-09-04T05:32:29+00:00"}
]
```

> ⚠️ **Las keys tienen espacios.** Hay que encodearlas o el request falla:
>
> ```js
> const url = `${API}/api/media/${encodeURIComponent(item.key)}`;
> ```
>
> Verificado: con la key encodeada devuelve `200 image/jpeg 169695 bytes`.

Para mostrar una imagen podés usar esa URL directo en un `<img src>` — el endpoint
devuelve el binario con el `Content-Type` correcto.

---

## 4. Modelo de datos

```ts
type Solicitud = {
  id: string;            // "BF-1042"
  titulo: string;
  categoria: string;
  direccion: string;
  descripcion: string;
  urgencia: string;
  cliente: string;
  profesional: string | null;
  estado: "pendiente" | "en_progreso" | "completado";
  creado: string;        // "2026-08-24"
  rating: number | null;
  comentario: string;
  fotos: string[];
};
```

Valores válidos (el backend **no los valida**, son convención):

- `categoria`: `Plomería`, `Electricidad`, `Carpintería`, `Pintura`, `Albañilería`, `Otro`
- `urgencia`: `Baja`, `Media`, `Alta`
- `estado`: `pendiente`, `en_progreso`, `completado`

Los filtros por query string son **case-sensitive y con acentos**:
`?categoria=Plomería` funciona, `?categoria=plomeria` devuelve `[]`.

---

## 5. Errores

Todos los errores vienen con esta forma:

```json
{"detail": "Solicitud no encontrada"}
```

| Status | Cuándo |
|---|---|
| `404` | id inexistente (`{"detail":"Solicitud no encontrada"}`) |
| `422` | body inválido o campo faltante — `detail` es un array de errores de Pydantic |
| `502` | el backend no pudo hablar con S3 (solo endpoints de media) |
| `503` | **no llegaste a la app**: el ALB no tiene targets healthy |

---

## 6. Trampas verificadas

### La barra final rompe el request

`/api/requests/` (con barra) devuelve **`307` redirect** a `/api/requests`.
En un `fetch` con CORS, el redirect del preflight puede fallar de formas confusas.
**Nunca pongas barra final.**

Verificado:

```
/api/requests   -> 200
/api/requests/  -> 307
```

### El estado NO se comparte entre instancias

Hay **2 instancias** detrás del ALB y los datos viven **en memoria de cada proceso**.
No hay base de datos. Un `POST` cae en una sola instancia; los `GET` siguientes
alternan entre las dos.

Esto es lo que pasó en una prueba real: creé una solicitud y después hice 6 `GET` seguidos:

```
GET 1: no aparece
GET 2: no aparece
GET 3: SÍ aparece
GET 4: no aparece
GET 5: SÍ aparece
GET 6: SÍ aparece
```

**Consecuencias para el frontend:**

- Después de un `POST`/`PATCH`, **no refetchees la lista** esperando ver el cambio.
  Usá la respuesta del propio `POST`/`PATCH` (devuelve el objeto completo) para
  actualizar el estado local.
- Cualquier cosa creada se pierde en el próximo redeploy. Para la demo, apoyate en
  los 3 registros hardcodeados (`BF-1042`, `BF-1039`, `BF-1031`).
- Si en una demo en vivo algo "desaparece y reaparece", es esto, no un bug del frontend.

> Hoy hay un registro basura `BF-1043 "PRUEBA smoke test"` en una de las dos instancias,
> de un test de verificación. Desaparece solo en el próximo redeploy.

---

## 7. Snippet de arranque

```js
const API = "http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com";

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (res.status === 503) {
    throw new Error("Backend caído (ALB sin targets healthy) — no es un bug del front");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// Uso
const solicitudes = await api("/api/requests");
const pendientes  = await api("/api/jobs");
const creada      = await api("/api/requests", {
  method: "POST",
  body: JSON.stringify({
    titulo: "…", categoria: "Plomería", direccion: "…",
    descripcion: "…", urgencia: "Alta", cliente: "…",
  }),
});
// Usá `creada` directo para actualizar el estado local — NO refetchees la lista.
```

---

## 8. Docs interactiva

FastAPI expone Swagger UI, útil para probar sin escribir código:

```
http://barriofix-alb-793636717.us-east-1.elb.amazonaws.com/docs
```
