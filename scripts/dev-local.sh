#!/usr/bin/env bash
#
# Levanta BarrioFix contra una base PostgreSQL local.
#
#   bash scripts/dev-local.sh
#
# Requiere: un PostgreSQL escuchando en localhost y el venv ya creado
# (python -m venv venv && venv/Scripts/pip install -r requirements.txt).
#
# NO usa la base de RDS: esta en subred privada y no se llega desde afuera
# de la VPC. La idea es probar el flujo completo sin tocar AWS.

set -euo pipefail
cd "$(dirname "$0")/.."

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
PGDATABASE="${PGDATABASE:-barriofix}"
export PGPASSWORD

# En Windows el ejecutable del venv esta en Scripts/, en Linux/macOS en bin/.
if [ -x "venv/Scripts/python.exe" ]; then
  PY="venv/Scripts/python.exe"
elif [ -x "venv/bin/python" ]; then
  PY="venv/bin/python"
else
  echo "No encuentro el venv. Corré primero:" >&2
  echo "  python -m venv venv && venv/Scripts/pip install -r requirements.txt" >&2
  exit 1
fi

echo "==> Creando la base '$PGDATABASE' si no existe"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" | grep -q 1 \
  || createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$PGDATABASE"

echo "==> Aplicando migraciones en orden"
for f in migrations/*.sql; do
  echo "    - $f"
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -q -v ON_ERROR_STOP=1 -f "$f"
done

echo "==> Estado de los catalogos"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c \
  "SELECT 'estado' t, count(*) FROM estado
   UNION ALL SELECT 'urgencia', count(*) FROM urgencia
   UNION ALL SELECT 'categoria', count(*) FROM categoria
   UNION ALL SELECT 'zona', count(*) FROM zona;"

export DATABASE_URL="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE"
# Fijo, no aleatorio: si cambia en cada arranque, los tokens de la sesion
# anterior dejan de validar y parece un bug.
export JWT_SECRET="${JWT_SECRET:-dev-secret-local-no-usar-en-aws}"
# El front de Vite corre en 5173; el default "*" tambien serviria, pero asi
# probamos la misma configuracion que va a AWS.
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"

echo
echo "==> Backend en http://localhost:8080  (docs en /docs)"
echo "    Frontend:  cd ../barriofix-front && npm run dev"
echo
exec "$PY" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
