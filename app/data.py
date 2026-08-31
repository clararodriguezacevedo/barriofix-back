"""Hardcoded in-memory data. No database yet — this is a lab/demo backend."""

CATEGORIES = ["Plomería", "Electricidad", "Carpintería", "Pintura", "Albañilería", "Otro"]
URGENCIAS = ["Baja", "Media", "Alta"]

STATUS_PENDIENTE = "pendiente"
STATUS_EN_PROGRESO = "en_progreso"
STATUS_COMPLETADO = "completado"

REQUESTS = [
    {
        "id": "BF-1042",
        "titulo": "Pérdida de agua bajo la pileta de cocina",
        "categoria": "Plomería",
        "direccion": "Calle Los Aromos 214, Villa Alegre",
        "descripcion": "Gotea agua debajo de la bacha de la cocina cada vez que se usa.",
        "urgencia": "Alta",
        "cliente": "Marisol Peña",
        "profesional": None,
        "estado": STATUS_PENDIENTE,
        "creado": "2026-08-24",
        "rating": None,
        "comentario": "",
        "fotos": [],
    },
    {
        "id": "BF-1039",
        "titulo": "Instalación de tomacorrientes en living",
        "categoria": "Electricidad",
        "direccion": "Pasaje Belgrano 88, Villa Alegre",
        "descripcion": "Necesito agregar dos tomas nuevas cerca del televisor.",
        "urgencia": "Media",
        "cliente": "Diego Farías",
        "profesional": "Nico Sartori",
        "estado": STATUS_EN_PROGRESO,
        "creado": "2026-08-20",
        "rating": None,
        "comentario": "",
        "fotos": [],
    },
    {
        "id": "BF-1031",
        "titulo": "Reparación de puerta de placard descolgada",
        "categoria": "Carpintería",
        "direccion": "Av. San Martín 1350, Villa Alegre",
        "descripcion": "La puerta corrediza se salió del riel superior y no cierra bien.",
        "urgencia": "Baja",
        "cliente": "Marisol Peña",
        "profesional": "Estela Rojas",
        "estado": STATUS_COMPLETADO,
        "creado": "2026-08-10",
        "rating": 5,
        "comentario": "Llegó puntual y dejó todo funcionando mejor que antes.",
        "fotos": [],
    },
]
