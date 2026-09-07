# Guía de despliegue — BarrioFix Backend (AMI dorada + código en S3)

> **Contexto para el asistente que lea esto:** esto es un lab de AWS Academy Learner Lab.
> El objetivo es desplegar una API FastAPI en un ASG detrás de un ALB, con las instancias en
> subredes **privadas sin acceso a internet** (no hay NAT Gateway). El código de la app se baja
> de S3 en el arranque a través de un **Gateway VPC Endpoint** de S3.
> Las dependencias de Python **no se instalan en el arranque** (no hay internet para PyPI):
> vienen pre-instaladas dentro de una AMI dorada que se construye una sola vez.
> No se pueden crear roles IAM: hay que usar `LabRole` / `LabInstanceProfile`.
> Guiame paso a paso por la consola de AWS, una fase a la vez, y esperá mi confirmación
> antes de pasar a la siguiente.

---

## Fase 0 — Tabla de nombres (completar ANTES de empezar)

Lo que el **código** realmente necesita (solo esto, todo lo demás es infra):

| Variable de entorno | Valor por defecto en el código | Tu valor |
|---|---|---|
| `AWS_REGION` | `us-east-1` | `us-east-1` ✅ |
| `MEDIA_BUCKET` | `barriofix-media-clara` | `barriofix-media-clara` ✅ |
| `CORS_ORIGINS` | `*` | website endpoint del frontend ✅ |

Los tres están documentados con instrucciones de reemplazo en
[`.env.example`](../.env.example).

Contratos fijos que la infra debe respetar:

| Cosa | Valor | Por qué |
|---|---|---|
| Puerto de la app | `8080` | Uvicorn escucha en `0.0.0.0:8080` |
| Health check path | `/health` | Devuelve `{"status":"ok"}` |
| Módulo ASGI | `app.main:app` | Estructura del repo |

Recursos de infraestructura — anotá los que **ya existen** y elegí nombre para los que faltan:

| # | Recurso | Nombre / ID | ¿Ya existe? |
|---|---|---|---|
| 1 | VPC | `_____________` | ☐ |
| 2 | Subred pública AZ-a | `subnet-_________` | ☐ |
| 3 | Subred pública AZ-b | `subnet-_________` | ☐ |
| 4 | Subred privada AZ-a | `subnet-_________` | ☐ |
| 5 | Subred privada AZ-b | `subnet-_________` | ☐ |
| 6 | Route table de las privadas | `rtb-_________` | ☐ |
| 7 | Gateway VPC Endpoint de S3 | `BarrioFix-s3-endpoint` | ☐ |
| 8 | Bucket de media (ya existe) | `barriofix-media-clara` | ☐ |
| 9 | **Bucket de artefactos (NUEVO)** | `barriofix-artifacts-clara` | ☐ |
| 9b | **Bucket de logs (NUEVO)** | `barriofix-logs-clara` | ☐ |
| 10 | Instance profile | `LabInstanceProfile` | ✅ (viene del lab) |
| 11 | Key pair (para el builder) | `_____________` | ☐ |
| 12 | Security Group del ALB | `BarrioFix-alb-sg` | ☐ |
| 13 | Security Group del backend | `BarrioFix-backend-sg` | ☐ |
| 14 | AMI dorada (sale de la Fase 3) | `ami-_________` | ☐ |
| 15 | Launch Template | `BarrioFix-backend-template` | ☐ |
| 16 | Target Group | `BarrioFix-backend-tg` | ☐ |
| 17 | Application Load Balancer | `BarrioFix-alb` | ☐ |
| 18 | Auto Scaling Group | `BarrioFix-backend-asg` | ☐ |
| 19 | Tu IP pública (para SSH al builder) | `____.____.____.___/32` | ☐ |

> ⚠️ **El bucket de artefactos tiene que ser distinto al de media.** El endpoint
> `GET /api/media` hace `list_objects_v2` sobre **todo** el bucket, así que si dejás el
> `app.tar.gz` ahí, aparece listado en la API pública.

---

## Fase 1 — Bucket de artefactos

Consola → **S3** → *Create bucket*

- Name: `barriofix-artifacts-clara`
- Region: la misma que todo lo demás (`us-east-1`)
- **Block all public access: ACTIVADO** (se accede solo por el rol IAM, nunca público)
- Versioning: activado (opcional, pero permite rollbackear un deploy malo)

Y un segundo bucket para los logs, `barriofix-logs-clara`:

- **Block all public access: ACTIVADO**
- Versioning: **desactivado** (los logs no se editan; versionarlos solo ocupa lugar)
- **Management → Create lifecycle rule**: expirar objetos a los 30 días. Sin esto, un
  bucket de logs crece para siempre y en el Learner Lab el presupuesto es finito.

> Tres buckets separados a propósito: media es lo único que la API expone, artefactos
> es código, y logs es escritura constante con lifecycle propio. Mezclarlos hace que
> `GET /api/media` liste cosas que no son fotos.

---

## Fase 2 — Verificar el Gateway VPC Endpoint de S3

Esto es lo que hace que todo funcione sin internet. Si falla, la instancia arranca sin app.

Consola → **VPC** → *Endpoints* → `BarrioFix-s3-endpoint`

Verificar:

- **Type:** Gateway (NO Interface)
- **Service name:** `com.amazonaws.us-east-1.s3`
- **Route tables:** tiene que estar tildada la route table de las **subredes privadas** (#6).
  Si no está, editar y asociarla.
- **Policy:** *Full access* (o al menos `s3:GetObject` + `s3:ListBucket` sobre media y
  artefactos, **y `s3:PutObject` sobre el de logs**)

> ⚠️ Si la policy del endpoint está restringida por bucket, agregale el de logs. Si no,
> el `aws s3 cp` de logrotate falla en silencio dentro de un `postrotate` — y logrotate
> no reporta ese error a ningún lado.

Después, en **VPC → Route tables → (la privada) → Routes**, tiene que aparecer una ruta con
destino `pl-xxxxxxx (com.amazonaws.us-east-1.s3)` apuntando al endpoint.

---

## Fase 3 — Construir la AMI dorada (se hace UNA sola vez)

### 3.1 Lanzar la instancia "builder"

Consola → **EC2** → *Launch instance*

- Name: `BarrioFix-builder`
- AMI: **Amazon Linux 2023** (x86_64)
- Instance type: `t3.micro`
- Key pair: el de la tabla (#11)
- Network: la VPC del proyecto, **subred PÚBLICA** (#2), **Auto-assign public IP: Enable**
  → esta instancia SÍ necesita internet, es la única que lo va a tener
- Security group: nuevo, `BarrioFix-builder-sg`, inbound SSH (22) solo desde tu IP (#19)
- **Advanced details → IAM instance profile: `LabInstanceProfile`**

### 3.2 Conectarse e instalar todo

SSH a la instancia y correr:

```bash
sudo dnf install -y python3.11 python3.11-pip tar
```

```bash
sudo useradd -r -s /sbin/nologin barriofix || true
sudo mkdir -p /opt/barriofix
sudo python3.11 -m venv /opt/barriofix/venv
sudo /opt/barriofix/venv/bin/pip install --upgrade pip
sudo /opt/barriofix/venv/bin/pip install fastapi "uvicorn[standard]" boto3
```

Verificar que quedó bien:

```bash
/opt/barriofix/venv/bin/python -c "import fastapi, uvicorn, boto3; print('deps ok')"
```

```bash
aws --version
```

(AL2023 ya trae la CLI v2 preinstalada; el User Data la necesita para el `s3 cp`.)

### 3.3 Escribir el servicio systemd

Crear `/etc/systemd/system/barriofix-backend.service` con este contenido
(`sudo nano /etc/systemd/system/barriofix-backend.service`):

```ini
[Unit]
Description=BarrioFix Backend (FastAPI + Uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=barriofix
WorkingDirectory=/opt/barriofix
# TODAS las variables vienen de un unico archivo en S3 que el User Data baja
# al arrancar. Ver Fase 4 para crearlo y Fase 6 para el User Data. No hay
# Environment= sueltos ni valores horneados en la AMI: cambiar la password
# de la base o el JWT_SECRET es re-subir el archivo, sin rehacer la imagen.
EnvironmentFile=/opt/barriofix/backend.env
ExecStart=/opt/barriofix/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

# Ademas del journal, a un archivo que logrotate sube a S3 (paso 3.3b).
# systemd abre el archivo como root antes de bajar a User=barriofix, asi que
# no hace falta darle permisos al usuario del servicio.
StandardOutput=append:/var/log/barriofix-app.log
StandardError=append:/var/log/barriofix-app.log

[Install]
WantedBy=multi-user.target
```

Y después:

```bash
sudo systemctl daemon-reload
```

> `WorkingDirectory=/opt/barriofix` + el tarball que extrae `app/` ahí
> ⇒ `/opt/barriofix/app/main.py` ⇒ `app.main:app` resuelve. No cambiar uno sin el otro.
>
> El archivo `backend.env` no existe todavia en el disco: lo baja el User Data en
> cada arranque (Fase 6). systemd tolera que falte al hacer daemon-reload; solo se
> queja cuando el servicio arranca, y para entonces ya esta.


### 3.3b Enviar los logs a S3

Las instancias no tienen internet, asi que para mandar logs a CloudWatch habria que
crear un **Interface Endpoint** (~USD 14-15/mes por dos AZ, mas el ingestion). Para S3
ya tenemos el **Gateway Endpoint gratis** funcionando. Con presupuesto de Learner Lab,
S3 gana.

El precio de esa decision: hasta 15 minutos de logs perdidos si una instancia muere de
golpe, y para buscar hay que bajar los archivos y grepear (o montar Athena encima).

| | S3 directo (lo que hacemos) | CloudWatch Logs |
|---|---|---|
| Endpoint necesario | Gateway (**gratis**, ya existe) | Interface (**~USD 14-15/mes** en 2 AZ) |
| Costo de datos | ~USD 0,023/GB/mes de storage | Storage + ingestion |
| Perdida si la instancia muere | Hasta el intervalo del timer (15 min) | Practicamente nula |
| Buscar y filtrar | Bajar y grepear, o Athena | Nativo: Logs Insights, alarmas |
| Implementacion | logrotate + timer (manual) | El agente lo resuelve solo |

> Para el informe: CloudWatch es lo recomendado en produccion real, pero aca el
> Interface Endpoint cuesta mas por mes que todo el resto de la infraestructura junta
> y no lo necesitamos para ninguna otra cosa. Es una decision de costo justificada por
> la topologia de red, no una simplificacion por comodidad.

#### El script de subida

Va en un archivo aparte y no inline en el `postrotate`, porque necesita varias lineas
y logrotate no reporta errores de esos scripts a ningun lado.

```bash
sudo tee /usr/local/bin/barriofix-subir-logs.sh > /dev/null <<'EOF'
#!/bin/bash
set -euo pipefail

LOGS_BUCKET="barriofix-logs-clara"
REGION="us-east-1"
ARCHIVO="/var/log/barriofix-app.log.1.gz"

[ -s "$ARCHIVO" ] || exit 0

# IMDSv2: Amazon Linux 2023 exige el token. Sin el, el curl devuelve 401,
# INSTANCE_ID queda vacio y TODAS las instancias suben a la misma key,
# pisandose entre si — justo lo que el prefijo por instancia evita.
TOKEN=$(curl -sf -X PUT "http://169.254.169.254/latest/api/token"     -H "X-aws-ec2-metadata-token-ttl-seconds: 60") || TOKEN=""
INSTANCE_ID=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN"     "http://169.254.169.254/latest/meta-data/instance-id") || INSTANCE_ID="desconocida"

DESTINO="s3://${LOGS_BUCKET}/${INSTANCE_ID}/$(date -u +%Y/%m/%d/%H%M%S).log.gz"

if aws s3 cp "$ARCHIVO" "$DESTINO" --region "$REGION"; then
    rm -f "$ARCHIVO"
else
    # Se deja el archivo: el proximo ciclo lo reintenta en vez de perderlo.
    logger -t barriofix-logs "Fallo la subida de $ARCHIVO a $DESTINO"
    exit 1
fi
EOF

sudo chmod 755 /usr/local/bin/barriofix-subir-logs.sh
```

#### La configuracion de logrotate

```bash
sudo tee /etc/logrotate.d/barriofix > /dev/null <<'EOF'
/var/log/barriofix-app.log {
    hourly
    rotate 1
    missingok
    notifempty
    compress

    # CRITICO: systemd mantiene abierto el descriptor del archivo por el
    # StandardOutput=append. Con la rotacion normal (renombrar y crear uno
    # nuevo) uvicorn seguiria escribiendo al archivo VIEJO y el nuevo quedaria
    # vacio para siempre. copytruncate copia y vacia en el lugar, asi que el
    # descriptor sigue siendo valido.
    copytruncate

    postrotate
        /usr/local/bin/barriofix-subir-logs.sh || true
    endscript
}
EOF
```

> `rotate 1`, no `rotate 0`: con `0` logrotate borra el archivo rotado en el mismo
> ciclo y el `.1.gz` puede no existir cuando corre el `postrotate`. Con `1` sobrevive
> hasta que el script lo sube y lo borra el mismo.

#### El timer

logrotate corre una vez por dia por defecto. Para una ventana de 15 minutos:

```bash
sudo tee /etc/systemd/system/barriofix-logs.service > /dev/null <<'EOF'
[Unit]
Description=Rotar y subir a S3 los logs de BarrioFix

[Service]
Type=oneshot
# -f fuerza la rotacion ignorando el "hourly" del archivo de config; sin esto
# logrotate rotaria una vez por hora aunque el timer corra cada 15 minutos.
# notifempty se sigue respetando, asi que un log vacio no sube nada.
ExecStart=/usr/sbin/logrotate -f /etc/logrotate.d/barriofix
EOF

sudo tee /etc/systemd/system/barriofix-logs.timer > /dev/null <<'EOF'
[Unit]
Description=Subir los logs de BarrioFix a S3 cada 15 minutos

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable barriofix-logs.timer
```

> El timer **si** se deja habilitado en la AMI (a diferencia del servicio de la app):
> no depende del codigo, solo del archivo de log, asi que arranca solo en cada
> instancia nueva sin que el User Data haga nada.

#### Probarlo en el builder antes de sacar la foto

```bash
echo "prueba de log" | sudo tee -a /var/log/barriofix-app.log
sudo /usr/sbin/logrotate -f /etc/logrotate.d/barriofix
aws s3 ls s3://barriofix-logs-clara/ --recursive
```

Tiene que aparecer un objeto bajo `<instance-id>/YYYY/MM/DD/HHMMSS.log.gz`. Si el
prefijo dice `desconocida/`, fallo la consulta a IMDSv2 y hay que revisarlo **ahora**,
antes de hornear la AMI.

### 3.4 Limpiar antes de sacar la foto

Muy importante: la AMI **no** debe llevar código de la app ni el servicio habilitado
(el User Data se encarga de las dos cosas en cada arranque).

```bash
sudo rm -rf /opt/barriofix/app
sudo systemctl disable barriofix-backend || true

# Los logs de prueba del builder no tienen que viajar dentro de la imagen:
# apareceria la misma linea en todas las instancias que nazcan de ella.
sudo rm -f /var/log/barriofix-app.log*
```

> El timer `barriofix-logs.timer` queda **habilitado** a proposito. El unico que se
> deshabilita es `barriofix-backend`, porque ese lo enciende el User Data despues de
> bajar el codigo.

### 3.5 Crear la AMI

Consola → **EC2 → Instances** → seleccionar `BarrioFix-builder` →
*Actions → Image and templates → Create image*

- Image name: `BarrioFix-backend-ami-v1`
- Esperar a que pase de `pending` a `available` (unos minutos)
- **Anotar el `ami-xxxxxxxx`** → va a la fila #14 de la tabla

### 3.6 Terminar el builder

Ya no sirve y consume presupuesto del lab. *Instance state → Terminate*.

---

## Fase 4 — Subir el código y las variables a S3

Desde la máquina local (PowerShell en Windows ya trae `tar`), parado en la raíz del repo:

```bash
tar --exclude=__pycache__ --exclude=venv -czf app.tar.gz app
```

Verificar el contenido — las rutas tienen que empezar con `app/`, no con `./` ni con una
ruta absoluta:

```bash
tar -tzf app.tar.gz
```

Subirlo: Consola → **S3** → `barriofix-artifacts-clara` → *Upload* → `app.tar.gz`

### 4b. Un único `backend.env` con TODAS las variables

Este archivo es el unico lugar donde viven los valores que la app necesita en runtime.
Ni la AMI ni el User Data los conocen: los dos son genericos y reusables.

Copiar `.env.example` del repo, completar las cinco variables y guardarlo como
`backend.env` **sin comentarios ni lineas en blanco al principio** (systemd es tolerante
pero mejor limpio):

```bash
AWS_REGION=us-east-1
MEDIA_BUCKET=barriofix-media-clara
CORS_ORIGINS=http://barriofix-frontend-clara.s3-website-us-east-1.amazonaws.com
DATABASE_URL=postgresql://barriofix_admin:LA_PASSWORD_REAL@barriofix-db.xxxxxxxxxxxx.us-east-1.rds.amazonaws.com:5432/barriofix?sslmode=require
JWT_SECRET=<generar con: python -c "import secrets; print(secrets.token_urlsafe(48))">
```

Subirlo al MISMO bucket que el tarball:

```bash
aws s3 cp backend.env s3://barriofix-artifacts-clara/backend.env
```

> ⚠️ **NUNCA commitear este archivo.** Tiene la password de RDS y el JWT_SECRET. El
> `.gitignore` del repo ya lo cubre (`.env` esta ignorado), pero si le pusiste otro
> nombre, verifica antes de un `git add`.
>
> ⚠️ **Un solo `JWT_SECRET` para las dos instancias del ASG.** Como todas leen el mismo
> archivo de S3, esto se cumple solo. Si en algun momento manejas mas de un ambiente
> (dev/prod) usa DOS archivos distintos en el bucket (`backend.dev.env`, `backend.prod.env`)
> y el User Data elige uno.

**Rotar una variable** (cambiar la password de RDS, cambiar el JWT_SECRET, agregar un
origen a CORS): editar `backend.env`, subirlo pisando la version anterior, y reiniciar
las instancias del ASG **de a una**. No hay que rehacer la AMI ni el tarball.

---

## Fase 5 — Security Groups

Crear dos, en este orden (el segundo referencia al primero).

**`BarrioFix-alb-sg`** (para el load balancer)

- Inbound: HTTP `80` desde `0.0.0.0/0`
- Outbound: all traffic (default)

**`BarrioFix-backend-sg`** (para las instancias)

- Inbound: TCP `8080` con **source = `BarrioFix-alb-sg`** (el security group, NO un CIDR)
- Outbound: all traffic (default) — necesario para llegar a S3 por el endpoint
- **Sin regla de SSH**: están en subred privada, no hay cómo llegar igual

---

## Fase 6 — Launch Template

Consola → **EC2 → Launch Templates** → *Create launch template*

- Name: `BarrioFix-backend-template`
- AMI: **la AMI dorada** de la Fase 3.5 (#14) — buscarla en la pestaña *My AMIs*
- Instance type: `t3.micro`
- Key pair: *Don't include* (no hay acceso SSH de todos modos)
- **Subnet: "Don't include in launch template"** ← lo define el ASG
- Security groups: `BarrioFix-backend-sg`
- **Advanced details → IAM instance profile: `LabInstanceProfile`**
- **Advanced details → User data:**

```bash
#!/bin/bash
set -euxo pipefail
exec > >(tee /var/log/barriofix-userdata.log | logger -t userdata -s 2>/dev/console) 2>&1

ARTIFACTS_BUCKET="barriofix-artifacts-clara"
REGION="us-east-1"
APP_DIR="/opt/barriofix"

# Los dos archivos vienen del mismo bucket, por el Gateway VPC Endpoint de
# S3, sin salir a internet.
aws s3 cp "s3://${ARTIFACTS_BUCKET}/app.tar.gz"   /tmp/app.tar.gz  --region "${REGION}"
aws s3 cp "s3://${ARTIFACTS_BUCKET}/backend.env" "${APP_DIR}/backend.env" --region "${REGION}"

# 600 + owner barriofix: la password de RDS y el JWT_SECRET viven ahi.
chmod 600 "${APP_DIR}/backend.env"
chown barriofix:barriofix "${APP_DIR}/backend.env"

rm -rf "${APP_DIR}/app"
tar -xzf /tmp/app.tar.gz -C "${APP_DIR}"
chown -R barriofix:barriofix "${APP_DIR}/app"

systemctl enable --now barriofix-backend
```

> Cambiar `ARTIFACTS_BUCKET` y `REGION` si tus nombres son otros. Si el `s3 cp` de
> `backend.env` falla (bucket sin permiso, archivo inexistente), la instancia arranca
> pero uvicorn se estrella al intentar leer las variables. Aparece como target unhealthy
> en el ALB.

---

## Fase 7 — Target Group

Consola → **EC2 → Target Groups** → *Create target group*

- Target type: **Instances**
- Name: `BarrioFix-backend-tg`
- Protocol / Port: **HTTP / 8080**
- VPC: la del proyecto
- **Health checks:**
  - Protocol: HTTP
  - Path: **`/health`**
  - Advanced: Port `traffic port`, Healthy threshold `2`, Unhealthy threshold `3`,
    Timeout `5`, Interval `15`, Success codes `200`
- **No registrar targets a mano** — los agrega el ASG

---

## Fase 8 — Application Load Balancer

Consola → **EC2 → Load Balancers** → *Create* → **Application Load Balancer**

- Name: `BarrioFix-alb`
- Scheme: **Internet-facing**
- IP address type: IPv4
- VPC: la del proyecto
- Mappings: las **dos subredes PÚBLICAS** (#2 y #3) — tiene que haber 2 AZ distintas
- Security group: `BarrioFix-alb-sg` (quitar el `default` si aparece)
- Listener: **HTTP : 80** → *Forward to* → `BarrioFix-backend-tg`

**Anotar el DNS name** (`BarrioFix-alb-1234567890.us-east-1.elb.amazonaws.com`).

---

## Fase 9 — Auto Scaling Group

Consola → **EC2 → Auto Scaling Groups** → *Create*

- Name: `BarrioFix-backend-asg`
- Launch template: `BarrioFix-backend-template` (Version: `Latest`)
- VPC: la del proyecto
- **Availability Zones and subnets: las dos subredes PRIVADAS** (#4 y #5)
- *Attach to an existing load balancer* → *Choose from your load balancer target groups*
  → `BarrioFix-backend-tg`
- **Turn on Elastic Load Balancing health checks** ✅
- **Health check grace period: `180` segundos** (le da tiempo al User Data a bajar y arrancar)
- Group size: Desired `2`, Minimum `2`, Maximum `4`
- Scaling policy: *Target tracking*, `Average CPU utilization`, target `50` (opcional)

---

## Fase 10 — Verificar

Esperar ~3 minutos y chequear que el Target Group muestre los targets en **healthy**.
Después, desde tu máquina (reemplazando el DNS del ALB):

```bash
curl http://BarrioFix-alb-XXXX.us-east-1.elb.amazonaws.com/health
```

Esperado: `{"status":"ok"}`

```bash
curl http://BarrioFix-alb-XXXX.us-east-1.elb.amazonaws.com/api/requests
```

Esperado: la lista de solicitudes hardcodeadas.

```bash
curl http://BarrioFix-alb-XXXX.us-east-1.elb.amazonaws.com/api/media
```

Esperado: la lista de objetos del bucket de media. **Este es el test que valida el
Gateway VPC Endpoint** — si devuelve `502 No se pudo listar el bucket`, el endpoint
o los permisos de `LabRole` están mal.

> Ojo: `POST /api/requests` guarda **en memoria**. Con 2 instancias detrás del ALB,
> lo que creás en una no lo ve la otra. Es esperado — todavía no hay base de datos.

---

## Redeploy (el loop de todos los días)

1. `tar --exclude=__pycache__ --exclude=venv -czf app.tar.gz app`
2. Subir `app.tar.gz` a `barriofix-artifacts-clara` (pisa el anterior)
3. **EC2 → Auto Scaling Groups → `BarrioFix-backend-asg` → Instance refresh → Start**
   - Minimum healthy percentage: `50`

Solo hay que rehacer la AMI (Fase 3) si **cambian las dependencias** de `requirements.txt`.

---

## Troubleshooting

**Los targets quedan `unhealthy` / la instancia arranca sin app**

Las instancias están en subred privada sin SSH, así que no se puede entrar a mirar.
Opciones, de menos a más trabajo:

1. **System log:** EC2 → la instancia → *Actions → Monitor and troubleshoot → Get system log*.
   El User Data loguea a la consola (`2>/dev/console`), así que los errores del
   `aws s3 cp` aparecen ahí.
2. **Reproducir en público:** lanzar una instancia suelta con la misma AMI y el mismo User Data
   pero en subred **pública** con IP pública y SSH. Si ahí funciona y en privada no,
   el problema es el VPC Endpoint.
3. Dentro de una instancia a la que sí puedas entrar:
   ```bash
   sudo cat /var/log/cloud-init-output.log
   sudo journalctl -u barriofix-backend -n 50 --no-pager
   curl localhost:8080/health
   ```

**Causas más comunes, en orden:**

| Síntoma | Causa probable |
|---|---|
| El User Data cuelga y timeoutea en `aws s3 cp` | El endpoint no está asociado a la route table de las privadas (Fase 2) |
| `AccessDenied` en el `s3 cp` | `LabRole` sin `s3:GetObject` sobre el bucket de artefactos |
| TG unhealthy pero la app corre | El SG del backend no permite `8080` desde el SG del ALB |
| TG unhealthy, health check 404 | Path del health check mal escrito (es `/health`, sin barra final) |
| `ModuleNotFoundError: app` | El tarball se armó desde adentro de `app/` en vez de la raíz del repo |
| `502` en `/api/media` | El endpoint funciona para artefactos pero falta permiso sobre el bucket de media |
| El bucket de logs queda vacio | La policy del Gateway Endpoint no permite `s3:PutObject` ahi, o `LabRole` no tiene permiso |
| Los logs suben bajo el prefijo `desconocida/` | Fallo IMDSv2: revisar el token en `barriofix-subir-logs.sh` |
| `barriofix-app.log` deja de crecer despues de la primera rotacion | Falta `copytruncate`: systemd sigue escribiendo al archivo viejo |

**Session Manager (SSM) para entrar a las privadas:** solo funciona si creás *interface*
endpoints para `ssm`, `ssmmessages` y `ec2messages`. En el Learner Lab eso suma costo y
puede no estar permitido — por eso la guía asume que no hay acceso interactivo a las
instancias de producción.
