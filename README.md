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

La guía completa (VPC, subredes, endpoints, launch template, ASG, ALB) vive en
**[docs/DEPLOY-AWS.md](docs/DEPLOY-AWS.md)**. Este bloque es solo la operativa del backend
una vez que la infra ya está armada.

**1. Base RDS (primera vez).** Desde una consola con acceso a la subred privada de la
base (CloudShell dentro de la VPC del backend, o desde una instancia del ASG):

```bash
export DATABASE_URL='postgresql://barriofix_admin:LA_PASSWORD@barriofix-db.xxxxx.us-east-1.rds.amazonaws.com:5432/barriofix?sslmode=require'
psql "$DATABASE_URL"   -f migrations/000_schema.sql   -f migrations/001_add_admin_flag.sql   -f migrations/002_seed_catalogos.sql
# opcional: usuarios y solicitudes de demo (password de todos: testeo123)
psql "$DATABASE_URL" -f migrations/004_seed_demo.sql
```

Para promover una cuenta a admin (necesario para los endpoints de backoffice):

```bash
psql "$DATABASE_URL" -c "UPDATE cuenta SET es_admin = TRUE WHERE username = 'tu_usuario';"
```

**2. AMI dorada (primera vez y cuando cambia `requirements.txt`).** Esta versión cambia
las dependencias: hay que rehacer la imagen antes del primer deploy. Ver `docs/DEPLOY-AWS.md`
Fase 3.

**3. Variables de entorno en un único archivo.** Todas viven en `backend.env`, que va
al mismo bucket que el código. El systemd unit lo lee via `EnvironmentFile=` y el User
Data lo baja de S3 en cada arranque, así que ni la AMI ni el User Data conocen valores
sensibles. Copiar `.env.example`, completar y subir:

```bash
cp .env.example backend.env
# editar backend.env: poner la password real de RDS y generar el JWT_SECRET con:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
aws s3 cp backend.env s3://barriofix-artifacts-clara/backend.env
```

⚠️ **Nunca commitear `backend.env`** — tiene password de RDS y el JWT_SECRET. Ya está
cubierto por `.gitignore`.

**4. Deploy del código.** Empaquetar y subir al mismo bucket:

```bash
tar --exclude=__pycache__ --exclude=venv -czf app.tar.gz app
aws s3 cp app.tar.gz s3://barriofix-artifacts-clara/app.tar.gz
```

Después, reciclar las instancias del ASG **de a una**, esperando que cada reemplazo quede
`healthy` en el Target Group antes de terminar la siguiente. Si las dos quedan afuera a
la vez, el ALB devuelve `503`.

**Rotar una variable** (cambiar la password de RDS, un origen de CORS, el JWT_SECRET):
editar `backend.env`, resubirlo, reciclar las instancias. Sin rehacer la AMI ni el tarball.

**5. Verificar.** Contra el ALB:

```bash
curl http://<alb-dns>/health       # {"status":"ok"}
curl http://<alb-dns>/health/db    # {"status":"ok","version":"PostgreSQL 16.x","tablas":13}
curl -X POST http://<alb-dns>/api/auth/login   -H 'Content-Type: application/json'   -d '{"username":"juan.perez","password":"testeo123"}'
```

Si `/health` responde OK pero `/health/db` no, el problema es que las instancias no
llegan a RDS: revisar el security group de la base (inbound `5432` desde el SG del
backend) y que las route tables de las subredes privadas tengan asociado el Gateway VPC
Endpoint de S3.

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
| `MEDIA_BUCKET` | `barriofix-media-clara` | Bucket de S3 donde viven las fotos |
| `CORS_ORIGINS` | `*` | Orígenes permitidos, separados por coma |
| `DATABASE_URL` | — | Conexión a PostgreSQL en RDS (**lleva la contraseña**) |
| `JWT_SECRET` | — | Firma de los tokens (**la misma en las dos instancias**) |

> ⚠️ **En EC2 no se lee ningún archivo `.env`.** Estas variables viven en el `Environment=`
> del systemd unit, horneado dentro de la AMI. Cambiarlas requiere rehacer la AMI
> (docs/DEPLOY-AWS.md, Fase 3.3). El `.env` local es solo para desarrollo.

Las credenciales de AWS nunca se configuran a mano: `boto3` las toma del rol IAM de la
instancia (`LabInstanceProfile`) vía el servicio de metadata.

---

## Endpoints

69 endpoints en total. El contrato completo está en
[docs/API-FRONTEND.md](docs/API-FRONTEND.md) y el diseño con las reglas de negocio en
[docs/API-DESIGN.md](docs/API-DESIGN.md). Resumen:

| Grupo | Rutas |
|---|---|
| Salud | `/health`, `/health/db`, `/` |
| Auth | `/api/auth/registro`, `/login`, `/token`, `/me` |
| Catálogos | `/api/categorias`, `/api/zonas`, `/api/urgencias`, `/api/estados` |
| Usuarios | `/api/usuarios/...` (backoffice) |
| Profesionales | `/api/profesionales/...` + especialidades N:M |
| Solicitudes | `/api/solicitudes/...` + transiciones + `/api/trabajos` |
| Fotos | `/api/solicitudes/{id}/fotos`, `/api/fotos/{id}` |
| Calificaciones | `/api/solicitudes/{id}/calificacion`, `/api/calificaciones/{id}` |

Documentación interactiva en `/docs`, con el botón **Authorize** funcionando.
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

- **Solo HTTP.** El ALB no tiene certificado; no hay listener 443. Los JWT viajan en
  claro: alcanza para el lab, no para producción.
- **`sslmode=require`, no `verify-full`.** La conexión a RDS va cifrada pero sin validar
  el certificado, porque `verify-full` necesita el bundle de CAs de AWS dentro de la
  instancia y las instancias no tienen internet para bajarlo.
- **Sin refresh tokens.** Cuando el JWT vence (12 h) hay que volver a entrar.
- **Sin paginado.** `GET /api/solicitudes` devuelve todo. Con el volumen de la demo no
  molesta.
