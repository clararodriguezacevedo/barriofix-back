"""Test de humo del flujo completo contra una base PostgreSQL real.

Ejercita las reglas de negocio que no se pueden validar leyendo el codigo:
la maquina de estados, el bloqueo de concurrencia al aceptar un trabajo, los
CHECK de fechas y las restricciones de una sola calificacion por solicitud.

Uso:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/barriofix \\
    JWT_SECRET=test \\
    venv/Scripts/python.exe scripts/smoke_test.py

NO apunta a RDS: usa la base que le pases en DATABASE_URL. Crea usuarios con
nombres aleatorios, asi que se puede correr varias veces seguidas.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "smoke-test")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

ok = 0
fallos = []


def check(descripcion, condicion, detalle=""):
    global ok
    if condicion:
        ok += 1
        print(f"  [OK]    {descripcion}")
    else:
        fallos.append(descripcion)
        print(f"  [FALLA] {descripcion}  {detalle}")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def seccion(titulo):
    print(f"\n=== {titulo} ===")


sufijo = uuid.uuid4().hex[:8]

# ---------------------------------------------------------------- catalogos

seccion("Catalogos")

r = client.get("/api/categorias")
check("GET /api/categorias sin token responde 200", r.status_code == 200, r.text[:200])
categorias = r.json()
check("hay categorias cargadas", len(categorias) > 0, f"hay {len(categorias)}")

r = client.get("/api/zonas")
zonas = r.json() if r.status_code == 200 else []
check("hay zonas cargadas (sin esto no se puede crear ninguna solicitud)", len(zonas) > 0)

r = client.get("/api/urgencias")
urgencias = r.json() if r.status_code == 200 else []
check("hay urgencias cargadas", len(urgencias) > 0)

r = client.get("/api/estados")
estados = {e["nombre"]: e for e in r.json()} if r.status_code == 200 else {}
check("estan los 5 estados", len(estados) == 5, f"hay {len(estados)}: {sorted(estados)}")
check("hay exactamente un estado inicial", sum(e["es_inicial"] for e in estados.values()) == 1)

if not (categorias and zonas and urgencias and estados):
    print("\nFaltan catalogos; no tiene sentido seguir. Corre las migraciones 002 y 003.")
    sys.exit(1)

id_categoria = categorias[0]["id_categoria"]
id_zona = zonas[0]["id_zona"]
id_urgencia = urgencias[0]["id_urgencia"]

# ---------------------------------------------------------------- registro

seccion("Registro y login")

r = client.post(
    "/api/auth/registro",
    json={
        "username": f"vecina_{sufijo}",
        "password": "testeo123",
        "nombre": "Marisol",
        "apellido": "Pena",
        "email": f"marisol_{sufijo}@ejemplo.com",
        "como_cliente": True,
        "como_profesional": False,
    },
)
check("registro de cliente responde 201", r.status_code == 201, r.text[:200])
cliente_token = r.json()["access_token"]
cliente_id = r.json()["usuario"]["id_usuario"]

# Dos profesionales de la MISMA categoria: sirven para probar la concurrencia.
profesionales = []
for n in (1, 2):
    r = client.post(
        "/api/auth/registro",
        json={
            "username": f"plomero{n}_{sufijo}",
            "password": "testeo123",
            "nombre": f"Profesional{n}",
            "apellido": "Test",
            "email": f"prof{n}_{sufijo}@ejemplo.com",
            "como_cliente": False,
            "como_profesional": True,
            "categorias": [id_categoria],
        },
    )
    check(f"registro de profesional {n} responde 201", r.status_code == 201, r.text[:200])
    profesionales.append(r.json()["access_token"])

r = client.post(
    "/api/auth/registro",
    json={
        "username": f"vecina_{sufijo}",
        "password": "testeo123",
        "nombre": "Otra",
        "apellido": "Persona",
        "email": f"otra_{sufijo}@ejemplo.com",
    },
)
check("username duplicado devuelve 409", r.status_code == 409, r.text[:200])

r = client.post("/api/auth/login", json={"username": f"vecina_{sufijo}", "password": "mal"})
check("contraseña incorrecta devuelve 401", r.status_code == 401)

r = client.post("/api/auth/login", json={"username": f"vecina_{sufijo}", "password": "testeo123"})
check("login correcto devuelve 200", r.status_code == 200, r.text[:200])

# ---------------------------------------------------------------- auth

seccion("Autenticacion y permisos")

check("sin token, /api/solicitudes da 401", client.get("/api/solicitudes").status_code == 401)
check(
    "con token invalido da 401",
    client.get("/api/solicitudes", headers=auth("basura")).status_code == 401,
)
check(
    "un no-admin no puede crear categorias (403)",
    client.post(
        "/api/categorias", json={"nombre": "Hackeada"}, headers=auth(cliente_token)
    ).status_code
    == 403,
)
check(
    "un cliente puro no accede a /api/trabajos (403)",
    client.get("/api/trabajos", headers=auth(cliente_token)).status_code == 403,
)

# ---------------------------------------------------------------- solicitud

seccion("Crear solicitud")

cuerpo = {
    "titulo": "Perdida de agua bajo la pileta",
    "descripcion": "Gotea cada vez que se usa.",
    "direccion": "Los Aromos 214",
    "id_categoria": id_categoria,
    "id_urgencia": id_urgencia,
    "id_zona": id_zona,
}

r = client.post("/api/solicitudes", json=cuerpo, headers=auth(cliente_token))
check("crear solicitud responde 201", r.status_code == 201, r.text[:300])
solicitud = r.json()
sid = solicitud["id_solicitud"]

check("el id es un entero", isinstance(sid, int), f"es {type(sid).__name__}")
check(
    "arranca en el estado inicial",
    solicitud["estado"]["nombre"] == "PENDIENTE",
    solicitud["estado"]["nombre"],
)
check("no tiene profesional asignado", solicitud["profesional"] is None)
check("trae la zona anidada", solicitud["zona"]["id_zona"] == id_zona)

r = client.post(
    "/api/solicitudes",
    json={**cuerpo, "id_zona": 999999},
    headers=auth(cliente_token),
)
check("zona inexistente devuelve 422", r.status_code == 422, r.text[:200])

r = client.post(
    "/api/solicitudes", json={k: v for k, v in cuerpo.items() if k != "id_zona"},
    headers=auth(cliente_token),
)
check("sin zona devuelve 422 (es NOT NULL)", r.status_code == 422)

# ---------------------------------------------------------------- concurrencia

seccion("Aceptar: la regla de consistencia clave")

r = client.get("/api/trabajos", headers=auth(profesionales[0]))
check("el profesional ve la solicitud en sus trabajos", r.status_code == 200 and any(
    t["id_solicitud"] == sid for t in r.json()
), r.text[:200])

r = client.post(f"/api/solicitudes/{sid}/aceptar", json={}, headers=auth(profesionales[0]))
check("el primer profesional la acepta (200)", r.status_code == 200, r.text[:300])
check(
    "pasa a ASIGNADO",
    r.status_code == 200 and r.json()["estado"]["nombre"] == "ASIGNADO",
)
check("queda con profesional asignado", r.status_code == 200 and r.json()["profesional"] is not None)

r = client.post(f"/api/solicitudes/{sid}/aceptar", json={}, headers=auth(profesionales[1]))
check(
    "el SEGUNDO profesional recibe 409, no un error de base",
    r.status_code == 409,
    f"status={r.status_code} {r.text[:200]}",
)

# ---------------------------------------------------------------- maquina de estados

seccion("Maquina de estados")

r = client.post(f"/api/solicitudes/{sid}/resolver", json={}, headers=auth(profesionales[0]))
check("no se puede saltar de ASIGNADO a RESUELTO (409)", r.status_code == 409, r.text[:200])

r = client.post(f"/api/solicitudes/{sid}/iniciar", json={}, headers=auth(profesionales[1]))
check("un profesional ajeno no puede iniciar (403)", r.status_code == 403, r.text[:200])

r = client.post(f"/api/solicitudes/{sid}/iniciar", json={}, headers=auth(profesionales[0]))
check("iniciar pasa a EN_PROGRESO", r.status_code == 200 and r.json()["estado"]["nombre"] == "EN_PROGRESO", r.text[:200])

r = client.put(f"/api/solicitudes/{sid}", json=cuerpo, headers=auth(cliente_token))
check("no se puede editar una solicitud ya tomada (409)", r.status_code == 409, r.text[:200])

r = client.post(f"/api/solicitudes/{sid}/resolver", json={}, headers=auth(profesionales[0]))
check("resolver pasa a RESUELTO", r.status_code == 200 and r.json()["estado"]["nombre"] == "RESUELTO", r.text[:200])

r = client.post(f"/api/solicitudes/{sid}/cancelar", json={}, headers=auth(cliente_token))
check("no se puede cancelar algo ya finalizado (409)", r.status_code == 409, r.text[:200])

# ---------------------------------------------------------------- historial

seccion("Historial de seguimiento")

r = client.get(f"/api/solicitudes/{sid}/seguimiento", headers=auth(cliente_token))
check("el historial responde 200", r.status_code == 200, r.text[:200])
historial = r.json() if r.status_code == 200 else []
check(
    "quedaron las 4 transiciones",
    len(historial) == 4,
    f"hay {len(historial)}: {[h['estado']['nombre'] for h in historial]}",
)
check(
    "solo la ultima esta abierta (fecha_hasta NULL)",
    sum(1 for h in historial if h["fecha_hasta"] is None) == 1,
)
check(
    "las fechas no se solapan y avanzan",
    all(
        historial[i]["fecha_hasta"] == historial[i + 1]["fecha_desde"]
        for i in range(len(historial) - 1)
    ),
    "el cierre de una fila debe coincidir con la apertura de la siguiente",
)

# ---------------------------------------------------------------- calificacion

seccion("Calificacion")

r = client.post(
    f"/api/solicitudes/{sid}/calificacion",
    json={"puntuacion": 5, "comentario": "Impecable."},
    headers=auth(cliente_token),
)
check("el cliente califica un trabajo resuelto (201)", r.status_code == 201, r.text[:200])

r = client.post(
    f"/api/solicitudes/{sid}/calificacion",
    json={"puntuacion": 1},
    headers=auth(cliente_token),
)
check("no se puede calificar dos veces (409)", r.status_code == 409, r.text[:200])

r = client.post(
    f"/api/solicitudes/{sid}/calificacion",
    json={"puntuacion": 9},
    headers=auth(cliente_token),
)
check("puntuacion fuera de 1-5 da 422", r.status_code == 422)

r = client.get(f"/api/profesionales/{client.get('/api/auth/me', headers=auth(profesionales[0])).json()['id_usuario']}", headers=auth(cliente_token))
check(
    "el profesional muestra promedio y trabajos resueltos",
    r.status_code == 200
    and r.json()["calificacion_promedio"] is not None
    and r.json()["trabajos_resueltos"] >= 1,
    r.text[:200],
)

# ---------------------------------------------------------------- cancelacion

seccion("Cancelacion")

r = client.post("/api/solicitudes", json=cuerpo, headers=auth(cliente_token))
sid2 = r.json()["id_solicitud"]
r = client.post(
    f"/api/solicitudes/{sid2}/cancelar",
    json={"motivo": "Lo resolvi yo"},
    headers=auth(cliente_token),
)
check("cancelar responde 200", r.status_code == 200, r.text[:300])
if r.status_code == 200:
    s = r.json()
    check("pasa a CANCELADO", s["estado"]["nombre"] == "CANCELADO")
    # El CHECK ck_solicitud_cancelacion exige que las dos vayan juntas.
    check(
        "el flag y la fecha de cancelacion viajan juntos",
        s["cancelada_por_cliente"] is True and s["fecha_cancelacion_cliente"] is not None,
        f"flag={s['cancelada_por_cliente']} fecha={s['fecha_cancelacion_cliente']}",
    )

r = client.get("/api/trabajos", headers=auth(profesionales[0]))
check(
    "una cancelada ya no aparece en trabajos disponibles",
    r.status_code == 200 and not any(t["id_solicitud"] == sid2 for t in r.json()),
)

# ---------------------------------------------------------------- resumen

print("\n" + "=" * 60)
print(f"  {ok} checks OK, {len(fallos)} fallas")
if fallos:
    print("\n  Fallaron:")
    for f in fallos:
        print(f"    - {f}")
print("=" * 60)
sys.exit(1 if fallos else 0)
