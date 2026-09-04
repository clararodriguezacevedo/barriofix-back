# BarrioFix Backend

API en FastAPI para el TP de Cloud Computing. Corre en un ASG detrás de un ALB, con las
instancias en **subredes privadas sin acceso a internet**: el código se baja de S3 al
arrancar, a través de un Gateway VPC Endpoint.

Todavía no hay base de datos. Las solicitudes y los trabajos viven **en memoria de cada
proceso** (`app/data.py`), así que se pierden en cada redeploy y no se comparten entre
instancias.

---

## Arranque rápido

### Correr localmente

```bash
python -m venv venv
```

```bash
venv/Scripts/pip install -r requirements.txt
```

(en Linux/macOS es `venv/bin/pip`)

```bash
cp .env.example .env
```

```bash
venv/Scripts/uvicorn app.main:app --reload --port 8080
```

Abrí `http://localhost:8080/docs` para la documentación interactiva de Swagger.

> Nota: correr local **no lee el `.env` automáticamente** — el código usa `os.environ`
> directo, sin `python-dotenv`. Para probar los endpoints de media necesitás exportar las
> variables a mano, o credenciales de AWS válidas en tu entorno. El resto de los endpoints
> anda sin nada configurado.

### Desplegar a AWS

Ver **[docs/DEPLOY-AWS.md](docs/DEPLOY-AWS.md)** — la guía completa paso a paso por consola.
El resumen del flujo, una vez que la infra ya existe:

```bash
tar --exclude=__pycache__ --exclude=venv -czf app.tar.gz app
```

Después: subir `app.tar.gz` a `barriofix-artifacts-clara` (pisando el anterior) y reciclar
las instancias del ASG **de a una**, esperando que cada reemplazo quede `healthy` en el
Target Group antes de terminar la siguiente. Si las dos quedan afuera a la vez, el ALB
devuelve `503`.

### Consumir la API desde el frontend

Ver **[docs/API-FRONTEND.md](docs/API-FRONTEND.md)** — URL base, contrato de cada endpoint,
modelo de datos y las trampas verificadas.

---

## Configuración

Todos los valores que dependen de AWS están documentados en
**[`.env.example`](.env.example)**, con instrucciones de cómo obtener cada uno.

El backend lee exactamente tres variables:

| Variable | Default | Qué es |
|---|---|---|
| `AWS_REGION` | `us-east-1` | Región de todo el proyecto |
| `MEDIA_BUCKET` | `barriofix-media-clara` | Bucket de S3 que sirve `/api/media` |
| `CORS_ORIGINS` | `*` | Orígenes permitidos, separados por coma |

> ⚠️ **En EC2 no se lee ningún archivo `.env`.** Estas variables viven en el `Environment=`
> del systemd unit, horneado dentro de la AMI. Cambiarlas requiere rehacer la AMI
> (docs/DEPLOY-AWS.md, Fase 3.3). El `.env` local es solo para desarrollo.

Las credenciales de AWS nunca se configuran a mano: `boto3` las toma del rol IAM de la
instancia (`LabInstanceProfile`) vía el servicio de metadata.

---

## Endpoints

| Método | Path | Qué hace |
|---|---|---|
| `GET` | `/health` | `{"status":"ok"}` — lo usa el health check del Target Group |
| `GET` | `/` | Mensaje de estado |
| `GET` | `/api/requests?categoria=&estado=` | Lista de solicitudes |
| `GET` | `/api/requests/{id}` | Una solicitud |
| `POST` | `/api/requests` | Crea una solicitud (responde **201**) |
| `PATCH` | `/api/requests/{id}/accept` | Asigna profesional y pasa a `en_progreso` |
| `PATCH` | `/api/requests/{id}/status` | Cambia el estado |
| `POST` | `/api/requests/{id}/rate` | Califica un trabajo completado |
| `GET` | `/api/jobs?categoria=&urgencia=` | Solicitudes pendientes disponibles |
| `GET` | `/api/media?prefix=` | Lista objetos del bucket de medios |
| `GET` | `/api/media/{key}` | Descarga un objeto del bucket de medios |

El contrato detallado (bodies, forma de los errores, encoding de las keys de media) está en
[docs/API-FRONTEND.md](docs/API-FRONTEND.md).

---

## Arquitectura

```
Browser
   │
   ├──> S3 static website  (frontend)
   │
   └──> ALB :80  ──>  Target Group :8080  ──>  ASG (2 × EC2, subred privada)
                                                     │
                                                     │  al arrancar: User Data
                                                     │  baja app.tar.gz de S3
                                                     ▼
                                            S3 Gateway VPC Endpoint
                                                     │
                                          ┌──────────┴──────────┐
                                          ▼                     ▼
                                 artifacts bucket        media bucket
                                  (app.tar.gz)            (/api/media)
```

Las instancias **no tienen salida a internet** (no hay NAT Gateway). Todo el tráfico a S3
sale por el Gateway VPC Endpoint. Por eso las dependencias de Python vienen pre-instaladas
en la AMI: en el arranque no se puede llegar a PyPI.

---

## Limitaciones conocidas

- **Sin base de datos.** El estado vive en memoria de cada proceso. Un `POST` cae en una
  sola de las dos instancias, así que un `GET` posterior puede o no reflejarlo según a cuál
  lo mande el ALB. El frontend debe usar la respuesta del `POST`/`PATCH` en vez de
  refetchear la lista.
- **Sin autenticación.** Todos los endpoints son públicos.
- **Solo HTTP.** El ALB no tiene certificado; no hay listener 443.
- **Sin validación de dominio.** `categoria`, `urgencia` y `estado` son strings libres: el
  backend acepta cualquier valor aunque no esté en la lista de `app/data.py`.
