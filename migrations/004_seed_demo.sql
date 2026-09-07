-- =========================================================
-- 004 — Datos de demo: usuarios, solicitudes, historial y calificaciones
--
-- 5 clientes + 5 profesionales, 20 solicitudes con su historial completo de
-- seguimiento y 5 calificaciones.
--
-- Todas las cuentas usan la misma contraseña: testeo123
--
-- Idempotente: se puede correr varias veces.
-- =========================================================

BEGIN;

-- =========================================================
-- CUENTA
-- =========================================================

INSERT INTO cuenta (username, password_hash, activo)
VALUES
    ('juan.perez',          '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('sofia.garcia',        '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('martin.lopez',        '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('valentina.romero',    '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('lucas.fernandez',     '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),

    ('carlos.electricista', '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('diego.plomero',       '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('mariano.gasista',     '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('pablo.pintor',        '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE),
    ('federico.tecnico',    '$2b$12$6bfXAXHM/YtR0BpoQB1IdeOl0cSDkZfAi45wgRwUOe1AwlxgLhiXu', TRUE)
ON CONFLICT (username) DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    activo = EXCLUDED.activo;


-- =========================================================
-- USUARIO
-- =========================================================

INSERT INTO usuario (id_cuenta, nombre, apellido, email, telefono)
SELECT c.id_cuenta, v.nombre, v.apellido, v.email, v.telefono
FROM (
    VALUES
        ('juan.perez',          'Juan',      'Pérez',     'juan.perez@example.com',          '+54 11 5555-1001'),
        ('sofia.garcia',        'Sofía',     'García',    'sofia.garcia@example.com',        '+54 11 5555-1002'),
        ('martin.lopez',        'Martín',    'López',     'martin.lopez@example.com',        '+54 11 5555-1003'),
        ('valentina.romero',    'Valentina', 'Romero',    'valentina.romero@example.com',    '+54 11 5555-1004'),
        ('lucas.fernandez',     'Lucas',     'Fernández', 'lucas.fernandez@example.com',     '+54 11 5555-1005'),
        ('carlos.electricista', 'Carlos',    'Gómez',     'carlos.gomez@example.com',        '+54 11 5555-2001'),
        ('diego.plomero',       'Diego',     'Martínez',  'diego.martinez@example.com',      '+54 11 5555-2002'),
        ('mariano.gasista',     'Mariano',   'Rodríguez', 'mariano.rodriguez@example.com',   '+54 11 5555-2003'),
        ('pablo.pintor',        'Pablo',     'Sánchez',   'pablo.sanchez@example.com',       '+54 11 5555-2004'),
        ('federico.tecnico',    'Federico',  'Torres',    'federico.torres@example.com',     '+54 11 5555-2005')
) AS v (username, nombre, apellido, email, telefono)
JOIN cuenta c ON c.username = v.username
ON CONFLICT (email) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    apellido = EXCLUDED.apellido,
    telefono = EXCLUDED.telefono;


-- =========================================================
-- CLIENTE — los primeros 5
-- =========================================================

INSERT INTO cliente (id_usuario)
SELECT id_usuario FROM usuario
WHERE email IN (
    'juan.perez@example.com',
    'sofia.garcia@example.com',
    'martin.lopez@example.com',
    'valentina.romero@example.com',
    'lucas.fernandez@example.com'
)
ON CONFLICT (id_usuario) DO NOTHING;


-- =========================================================
-- PROFESIONAL — los últimos 5
-- =========================================================

INSERT INTO profesional (id_usuario, descripcion, disponible)
SELECT u.id_usuario, v.descripcion, TRUE
FROM (
    VALUES
        ('carlos.gomez@example.com',      'Electricista matriculado. Instalaciones eléctricas, reparación de cortocircuitos, tableros, térmicas, disyuntores y luminarias.'),
        ('diego.martinez@example.com',    'Plomero con experiencia en pérdidas de agua, grifería, cañerías, destapaciones y reparación de sanitarios.'),
        ('mariano.rodriguez@example.com', 'Gasista especializado en instalación, mantenimiento y reparación de calefones, termotanques y cocinas.'),
        ('pablo.sanchez@example.com',     'Pintor de interiores y exteriores. Preparación de paredes, pintura, enduido, impermeabilización y terminaciones.'),
        ('federico.torres@example.com',   'Técnico especializado en aire acondicionado, refrigeración y mantenimiento general de equipos domiciliarios.')
) AS v (email, descripcion)
JOIN usuario u ON u.email = v.email
ON CONFLICT (id_usuario) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    disponible = EXCLUDED.disponible;


-- =========================================================
-- PROFESIONAL_CATEGORIA
-- =========================================================

INSERT INTO profesional_categoria (id_profesional, id_categoria)
SELECT u.id_usuario, c.id_categoria
FROM (
    VALUES
        ('carlos.gomez@example.com',      'Electricidad'),
        ('carlos.gomez@example.com',      'Domótica y hogar inteligente'),
        ('carlos.gomez@example.com',      'Instalación de alarmas y cámaras'),
        ('diego.martinez@example.com',    'Plomería'),
        ('diego.martinez@example.com',    'Tratamiento de humedad'),
        ('mariano.rodriguez@example.com', 'Gas'),
        ('mariano.rodriguez@example.com', 'Aire acondicionado y climatización'),
        ('pablo.sanchez@example.com',     'Pintura'),
        ('pablo.sanchez@example.com',     'Yesería y durlock'),
        ('pablo.sanchez@example.com',     'Impermeabilización de techos'),
        ('pablo.sanchez@example.com',     'Tratamiento de humedad'),
        ('federico.torres@example.com',   'Aire acondicionado y climatización'),
        ('federico.torres@example.com',   'Reparación de electrodomésticos'),
        ('federico.torres@example.com',   'Técnico en computación y redes'),
        ('federico.torres@example.com',   'Instalación de TV y home theater')
) AS v (email, categoria)
JOIN usuario u ON u.email = v.email
JOIN profesional p ON p.id_usuario = u.id_usuario
JOIN categoria c ON c.nombre = v.categoria
ON CONFLICT (id_profesional, id_categoria) DO NOTHING;

COMMIT;


-- =========================================================
-- SOLICITUD
-- =========================================================

BEGIN;

WITH datos_solicitud (email_cliente, categoria, urgencia, zona, titulo, descripcion, direccion) AS (
    VALUES
    ('juan.perez@example.com', 'Plomería', 'ALTA', 'Palermo',
     'Pérdida de agua debajo de la pileta',
     'Hay una pérdida constante debajo de la pileta de la cocina. Parece venir de una de las conexiones del desagüe y está mojando el mueble.',
     'Av. Córdoba 4850, Palermo'),
    ('juan.perez@example.com', 'Electricidad', 'ALTA', 'Palermo',
     'Salta la térmica al encender el horno',
     'Cada vez que enciendo el horno eléctrico se corta la luz del departamento y salta la térmica del tablero.',
     'Gorriti 4250, Palermo'),
    ('juan.perez@example.com', 'Aire acondicionado y climatización', 'MEDIA', 'Villa Crespo',
     'Aire acondicionado no enfría',
     'El equipo enciende normalmente pero después de varios minutos sigue tirando aire a temperatura ambiente.',
     'Malabia 850, Villa Crespo'),
    ('juan.perez@example.com', 'Armado de muebles', 'BAJA', 'Caballito',
     'Armado de escritorio y biblioteca',
     'Necesito armar un escritorio nuevo y una biblioteca de seis estantes comprados desarmados.',
     'Av. Rivadavia 5300, Caballito'),

    ('sofia.garcia@example.com', 'Gas', 'ALTA', 'Belgrano',
     'Calefón se apaga durante el uso',
     'El calefón enciende pero después de unos minutos se apaga solo. Necesito revisión por un profesional.',
     'Mendoza 2150, Belgrano'),
    ('sofia.garcia@example.com', 'Pintura', 'BAJA', 'Belgrano',
     'Pintar living y comedor',
     'Quiero pintar living y comedor. Las paredes están en buen estado pero hay que cubrir algunos agujeros pequeños antes de pintar.',
     'Amenábar 1800, Belgrano'),
    ('sofia.garcia@example.com', 'Cerrajería', 'ALTA', 'Núñez',
     'Llave trabada en cerradura',
     'La llave quedó trabada dentro de la cerradura de la puerta principal y no puedo retirarla.',
     'Av. Cabildo 3400, Núñez'),
    ('sofia.garcia@example.com', 'Limpieza de tapizados y alfombras', 'BAJA', 'Recoleta',
     'Limpieza profunda de sillón',
     'Necesito limpiar un sillón de tres cuerpos y dos almohadones. Tiene algunas manchas de uso y polvo acumulado.',
     'Juncal 1850, Recoleta'),

    ('martin.lopez@example.com', 'Reparación de electrodomésticos', 'MEDIA', 'Almagro',
     'Lavarropas no centrifuga',
     'El lavarropas completa el lavado pero no realiza correctamente el centrifugado y queda agua dentro del tambor.',
     'Medrano 750, Almagro'),
    ('martin.lopez@example.com', 'Técnico en computación y redes', 'MEDIA', 'Almagro',
     'WiFi con cortes frecuentes',
     'La conexión WiFi se corta varias veces por día. Necesito revisar el router y la cobertura dentro del departamento.',
     'Av. Corrientes 3900, Almagro'),
    ('martin.lopez@example.com', 'Colocación de pisos y cerámicos', 'MEDIA', 'Boedo',
     'Reemplazar cerámicos rotos del baño',
     'Tengo aproximadamente ocho cerámicos del piso del baño rotos y necesito retirarlos y colocar los nuevos.',
     'Av. Boedo 1150, Boedo'),
    ('martin.lopez@example.com', 'Instalación de TV y home theater', 'BAJA', 'Caballito',
     'Colgar TV de 55 pulgadas',
     'Necesito instalar un soporte articulado en la pared y colocar un televisor de 55 pulgadas.',
     'José María Moreno 450, Caballito'),

    ('valentina.romero@example.com', 'Tratamiento de humedad', 'MEDIA', 'Flores',
     'Humedad en pared del dormitorio',
     'Apareció una mancha grande de humedad en una pared del dormitorio. Quiero identificar el origen y reparar la zona afectada.',
     'Av. Directorio 2450, Flores'),
    ('valentina.romero@example.com', 'Impermeabilización de techos', 'ALTA', 'Villa Devoto',
     'Filtración de agua por el techo',
     'Cuando llueve entra agua por una esquina del techo. La filtración aumentó durante las últimas lluvias.',
     'Nueva York 3900, Villa Devoto'),
    ('valentina.romero@example.com', 'Colocación de cortinas y cuadros', 'BAJA', 'Villa Urquiza',
     'Instalar barrales y cortinas',
     'Necesito colocar tres barrales para cortinas y colgar dos cuadros grandes en el living.',
     'Olazábal 5100, Villa Urquiza'),
    ('valentina.romero@example.com', 'Fumigación y control de plagas', 'ALTA', 'Villa Urquiza',
     'Problema de cucarachas en cocina',
     'Durante la última semana aparecieron varias cucarachas pequeñas principalmente durante la noche en la cocina.',
     'Monroe 4800, Villa Urquiza'),

    ('lucas.fernandez@example.com', 'Herrería', 'MEDIA', 'Mataderos',
     'Reparar portón de entrada',
     'El portón metálico de entrada está desalineado y roza contra el piso. También necesita revisar una de las bisagras.',
     'Av. Emilio Castro 6500, Mataderos'),
    ('lucas.fernandez@example.com', 'Carpintería', 'BAJA', 'Villa Luro',
     'Reparar puerta de placard',
     'Una puerta corrediza del placard se salió de la guía y otra tiene una bisagra floja.',
     'Av. Rivadavia 9800, Villa Luro'),
    ('lucas.fernandez@example.com', 'Jardinería y paisajismo', 'BAJA', 'Saavedra',
     'Poda y mantenimiento de jardín',
     'Necesito podar dos árboles pequeños, cortar el césped y hacer mantenimiento general del jardín.',
     'Ramallo 3700, Saavedra'),
    ('lucas.fernandez@example.com', 'Instalación de alarmas y cámaras', 'MEDIA', 'Villa Pueyrredón',
     'Instalar cámaras de seguridad',
     'Quiero instalar cuatro cámaras de seguridad exteriores con grabación y acceso desde el celular.',
     'Artigas 4800, Villa Pueyrredón')
)
INSERT INTO solicitud (
    id_cliente, id_categoria, id_urgencia, id_zona,
    titulo, descripcion, direccion,
    cancelada_por_cliente, fecha_cancelacion_cliente
)
SELECT u.id_usuario, c.id_categoria, ur.id_urgencia, z.id_zona,
       d.titulo, d.descripcion, d.direccion, FALSE, NULL
FROM datos_solicitud d
JOIN usuario u   ON u.email = d.email_cliente
JOIN cliente cl  ON cl.id_usuario = u.id_usuario
JOIN categoria c ON c.nombre = d.categoria
JOIN urgencia ur ON ur.nombre = d.urgencia
JOIN zona z      ON z.nombre = d.zona
WHERE NOT EXISTS (
    SELECT 1 FROM solicitud s
    WHERE s.id_cliente = u.id_usuario AND s.titulo = d.titulo
);


-- Historial: se borra y se regenera para que el seed sea repetible.
DELETE FROM seguimiento_solicitud
WHERE id_solicitud IN (
    SELECT id_solicitud FROM solicitud WHERE titulo IN (
        'Pérdida de agua debajo de la pileta', 'Salta la térmica al encender el horno',
        'Aire acondicionado no enfría', 'Armado de escritorio y biblioteca',
        'Calefón se apaga durante el uso', 'Pintar living y comedor',
        'Llave trabada en cerradura', 'Limpieza profunda de sillón',
        'Lavarropas no centrifuga', 'WiFi con cortes frecuentes',
        'Reemplazar cerámicos rotos del baño', 'Colgar TV de 55 pulgadas',
        'Humedad en pared del dormitorio', 'Filtración de agua por el techo',
        'Instalar barrales y cortinas', 'Problema de cucarachas en cocina',
        'Reparar portón de entrada', 'Reparar puerta de placard',
        'Poda y mantenimiento de jardín', 'Instalar cámaras de seguridad'
    )
);

-- Fechas históricas para que los cambios de estado sean coherentes.
UPDATE solicitud
SET fecha_creacion = CURRENT_TIMESTAMP - INTERVAL '10 days',
    cancelada_por_cliente = FALSE,
    fecha_cancelacion_cliente = NULL
WHERE titulo IN (
    'Pérdida de agua debajo de la pileta', 'Salta la térmica al encender el horno',
    'Aire acondicionado no enfría', 'Armado de escritorio y biblioteca',
    'Calefón se apaga durante el uso', 'Pintar living y comedor',
    'Llave trabada en cerradura', 'Limpieza profunda de sillón',
    'Lavarropas no centrifuga', 'WiFi con cortes frecuentes',
    'Reemplazar cerámicos rotos del baño', 'Colgar TV de 55 pulgadas',
    'Humedad en pared del dormitorio', 'Filtración de agua por el techo',
    'Instalar barrales y cortinas', 'Problema de cucarachas en cocina',
    'Reparar portón de entrada', 'Reparar puerta de placard',
    'Poda y mantenimiento de jardín', 'Instalar cámaras de seguridad'
);

-- Cancelaciones reales del cliente. El CHECK exige flag y fecha juntos.
UPDATE solicitud
SET cancelada_por_cliente = TRUE,
    fecha_cancelacion_cliente = fecha_creacion + INTERVAL '8 hours'
WHERE titulo IN ('Problema de cucarachas en cocina', 'Reparar portón de entrada');


-- =========================================================
-- SEGUIMIENTO_SOLICITUD
--
-- Incluye dos casos de profesional que se libera (ASIGNADO -> PENDIENTE):
-- 'Aire acondicionado no enfría' y 'Humedad en pared del dormitorio'.
-- =========================================================

WITH historial (titulo, estado, profesional_email, actor_email, offset_desde, offset_hasta, motivo) AS (
    VALUES
    -- 1. RESUELTA — Diego Martínez
    ('Pérdida de agua debajo de la pileta', 'PENDIENTE',   NULL,                          'juan.perez@example.com',       INTERVAL '0 hours', INTERVAL '2 hours', 'Solicitud publicada por el cliente'),
    ('Pérdida de agua debajo de la pileta', 'ASIGNADO',    'diego.martinez@example.com',  'diego.martinez@example.com',   INTERVAL '2 hours', INTERVAL '1 day',   'Diego Martínez aceptó la solicitud'),
    ('Pérdida de agua debajo de la pileta', 'EN_PROGRESO', 'diego.martinez@example.com',  'diego.martinez@example.com',   INTERVAL '1 day',   INTERVAL '2 days',  'El profesional comenzó el trabajo'),
    ('Pérdida de agua debajo de la pileta', 'RESUELTO',    'diego.martinez@example.com',  'diego.martinez@example.com',   INTERVAL '2 days',  NULL,               'Pérdida reparada correctamente'),

    -- 2. RESUELTA — Carlos Gómez
    ('Salta la térmica al encender el horno', 'PENDIENTE',   NULL,                        'juan.perez@example.com',       INTERVAL '0 hours',  INTERVAL '3 hours',  'Solicitud publicada por el cliente'),
    ('Salta la térmica al encender el horno', 'ASIGNADO',    'carlos.gomez@example.com',  'carlos.gomez@example.com',     INTERVAL '3 hours',  INTERVAL '10 hours', 'Carlos Gómez aceptó la solicitud'),
    ('Salta la térmica al encender el horno', 'EN_PROGRESO', 'carlos.gomez@example.com',  'carlos.gomez@example.com',     INTERVAL '10 hours', INTERVAL '1 day',    'El profesional inició la revisión eléctrica'),
    ('Salta la térmica al encender el horno', 'RESUELTO',    'carlos.gomez@example.com',  'carlos.gomez@example.com',     INTERVAL '1 day',    NULL,                'Se reparó la falla que provocaba el corte'),

    -- 3. El profesional se libera y otro la toma. Actual: EN_PROGRESO
    ('Aire acondicionado no enfría', 'PENDIENTE',   NULL,                             'juan.perez@example.com',         INTERVAL '0 hours', INTERVAL '2 hours', 'Solicitud publicada por el cliente'),
    ('Aire acondicionado no enfría', 'ASIGNADO',    'federico.torres@example.com',    'federico.torres@example.com',    INTERVAL '2 hours', INTERVAL '8 hours', 'Federico Torres aceptó la solicitud'),
    ('Aire acondicionado no enfría', 'PENDIENTE',   NULL,                             'federico.torres@example.com',    INTERVAL '8 hours', INTERVAL '1 day',   'Federico Torres canceló la asignación. La solicitud vuelve a estar disponible'),
    ('Aire acondicionado no enfría', 'ASIGNADO',    'mariano.rodriguez@example.com',  'mariano.rodriguez@example.com',  INTERVAL '1 day',   INTERVAL '2 days',  'Mariano Rodríguez aceptó la solicitud'),
    ('Aire acondicionado no enfría', 'EN_PROGRESO', 'mariano.rodriguez@example.com',  'mariano.rodriguez@example.com',  INTERVAL '2 days',  NULL,               'El profesional está realizando el diagnóstico del equipo'),

    -- 4. PENDIENTE
    ('Armado de escritorio y biblioteca', 'PENDIENTE', NULL, 'juan.perez@example.com', INTERVAL '0 hours', NULL, 'Solicitud publicada y esperando profesional'),

    -- 5. RESUELTA — Mariano Rodríguez
    ('Calefón se apaga durante el uso', 'PENDIENTE',   NULL,                            'sofia.garcia@example.com',      INTERVAL '0 hours', INTERVAL '1 hour',  'Solicitud publicada por el cliente'),
    ('Calefón se apaga durante el uso', 'ASIGNADO',    'mariano.rodriguez@example.com', 'mariano.rodriguez@example.com', INTERVAL '1 hour',  INTERVAL '6 hours', 'Mariano Rodríguez aceptó la solicitud'),
    ('Calefón se apaga durante el uso', 'EN_PROGRESO', 'mariano.rodriguez@example.com', 'mariano.rodriguez@example.com', INTERVAL '6 hours', INTERVAL '1 day',   'Comenzó la revisión del calefón'),
    ('Calefón se apaga durante el uso', 'RESUELTO',    'mariano.rodriguez@example.com', 'mariano.rodriguez@example.com', INTERVAL '1 day',   NULL,               'Calefón reparado y probado correctamente'),

    -- 6. RESUELTA — Pablo Sánchez
    ('Pintar living y comedor', 'PENDIENTE',   NULL,                         'sofia.garcia@example.com',  INTERVAL '0 hours', INTERVAL '5 hours', 'Solicitud publicada por el cliente'),
    ('Pintar living y comedor', 'ASIGNADO',    'pablo.sanchez@example.com',  'pablo.sanchez@example.com', INTERVAL '5 hours', INTERVAL '1 day',   'Pablo Sánchez aceptó el trabajo'),
    ('Pintar living y comedor', 'EN_PROGRESO', 'pablo.sanchez@example.com',  'pablo.sanchez@example.com', INTERVAL '1 day',   INTERVAL '4 days',  'Trabajo de pintura iniciado'),
    ('Pintar living y comedor', 'RESUELTO',    'pablo.sanchez@example.com',  'pablo.sanchez@example.com', INTERVAL '4 days',  NULL,               'Living y comedor terminados'),

    -- 7 y 8. PENDIENTES
    ('Llave trabada en cerradura',   'PENDIENTE', NULL, 'sofia.garcia@example.com', INTERVAL '0 hours', NULL, 'Solicitud pendiente de profesional'),
    ('Limpieza profunda de sillón',  'PENDIENTE', NULL, 'sofia.garcia@example.com', INTERVAL '0 hours', NULL, 'Solicitud pendiente de profesional'),

    -- 9. RESUELTA — Federico Torres
    ('Lavarropas no centrifuga', 'PENDIENTE',   NULL,                           'martin.lopez@example.com',    INTERVAL '0 hours', INTERVAL '4 hours', 'Solicitud publicada por el cliente'),
    ('Lavarropas no centrifuga', 'ASIGNADO',    'federico.torres@example.com',  'federico.torres@example.com', INTERVAL '4 hours', INTERVAL '1 day',   'Federico Torres aceptó la solicitud'),
    ('Lavarropas no centrifuga', 'EN_PROGRESO', 'federico.torres@example.com',  'federico.torres@example.com', INTERVAL '1 day',   INTERVAL '2 days',  'Se inició el diagnóstico del lavarropas'),
    ('Lavarropas no centrifuga', 'RESUELTO',    'federico.torres@example.com',  'federico.torres@example.com', INTERVAL '2 days',  NULL,               'Lavarropas reparado correctamente'),

    -- 10. EN PROGRESO
    ('WiFi con cortes frecuentes', 'PENDIENTE',   NULL,                          'martin.lopez@example.com',    INTERVAL '0 hours', INTERVAL '3 hours', 'Solicitud publicada por el cliente'),
    ('WiFi con cortes frecuentes', 'ASIGNADO',    'federico.torres@example.com', 'federico.torres@example.com', INTERVAL '3 hours', INTERVAL '1 day',   'Federico Torres aceptó la solicitud'),
    ('WiFi con cortes frecuentes', 'EN_PROGRESO', 'federico.torres@example.com', 'federico.torres@example.com', INTERVAL '1 day',   NULL,               'Se está revisando router, interferencias y cobertura'),

    -- 11. PENDIENTE
    ('Reemplazar cerámicos rotos del baño', 'PENDIENTE', NULL, 'martin.lopez@example.com', INTERVAL '0 hours', NULL, 'Esperando profesional'),

    -- 12. ASIGNADA
    ('Colgar TV de 55 pulgadas', 'PENDIENTE', NULL,                          'martin.lopez@example.com',    INTERVAL '0 hours', INTERVAL '7 hours', 'Solicitud publicada'),
    ('Colgar TV de 55 pulgadas', 'ASIGNADO',  'federico.torres@example.com', 'federico.torres@example.com', INTERVAL '7 hours', NULL,               'Federico Torres aceptó la instalación'),

    -- 13. El profesional se liberó. Actual: PENDIENTE
    ('Humedad en pared del dormitorio', 'PENDIENTE', NULL,                        'valentina.romero@example.com', INTERVAL '0 hours',  INTERVAL '4 hours',  'Solicitud publicada'),
    ('Humedad en pared del dormitorio', 'ASIGNADO',  'pablo.sanchez@example.com', 'pablo.sanchez@example.com',    INTERVAL '4 hours',  INTERVAL '12 hours', 'Pablo Sánchez aceptó la solicitud'),
    ('Humedad en pared del dormitorio', 'PENDIENTE', NULL,                        'pablo.sanchez@example.com',    INTERVAL '12 hours', NULL,                'Pablo Sánchez canceló la asignación. La solicitud vuelve a estar disponible'),

    -- 14. EN PROGRESO
    ('Filtración de agua por el techo', 'PENDIENTE',   NULL,                        'valentina.romero@example.com', INTERVAL '0 hours', INTERVAL '2 hours', 'Solicitud publicada'),
    ('Filtración de agua por el techo', 'ASIGNADO',    'pablo.sanchez@example.com', 'pablo.sanchez@example.com',    INTERVAL '2 hours', INTERVAL '1 day',   'Pablo Sánchez aceptó el trabajo'),
    ('Filtración de agua por el techo', 'EN_PROGRESO', 'pablo.sanchez@example.com', 'pablo.sanchez@example.com',    INTERVAL '1 day',   NULL,               'Impermeabilización en proceso'),

    -- 15. PENDIENTE
    ('Instalar barrales y cortinas', 'PENDIENTE', NULL, 'valentina.romero@example.com', INTERVAL '0 hours', NULL, 'Esperando profesional'),

    -- 16 y 17. CANCELADAS POR EL CLIENTE
    ('Problema de cucarachas en cocina', 'PENDIENTE', NULL, 'valentina.romero@example.com', INTERVAL '0 hours', INTERVAL '8 hours', 'Solicitud publicada'),
    ('Problema de cucarachas en cocina', 'CANCELADO', NULL, 'valentina.romero@example.com', INTERVAL '8 hours', NULL,               'La cliente canceló la solicitud'),
    ('Reparar portón de entrada',        'PENDIENTE', NULL, 'lucas.fernandez@example.com',  INTERVAL '0 hours', INTERVAL '8 hours', 'Solicitud publicada'),
    ('Reparar portón de entrada',        'CANCELADO', NULL, 'lucas.fernandez@example.com',  INTERVAL '8 hours', NULL,               'El cliente decidió cancelar la solicitud'),

    -- 18 y 19. PENDIENTES
    ('Reparar puerta de placard',     'PENDIENTE', NULL, 'lucas.fernandez@example.com', INTERVAL '0 hours', NULL, 'Esperando profesional'),
    ('Poda y mantenimiento de jardín','PENDIENTE', NULL, 'lucas.fernandez@example.com', INTERVAL '0 hours', NULL, 'Esperando profesional'),

    -- 20. EN PROGRESO
    ('Instalar cámaras de seguridad', 'PENDIENTE',   NULL,                       'lucas.fernandez@example.com', INTERVAL '0 hours', INTERVAL '5 hours', 'Solicitud publicada'),
    ('Instalar cámaras de seguridad', 'ASIGNADO',    'carlos.gomez@example.com', 'carlos.gomez@example.com',    INTERVAL '5 hours', INTERVAL '1 day',   'Carlos Gómez aceptó la instalación'),
    ('Instalar cámaras de seguridad', 'EN_PROGRESO', 'carlos.gomez@example.com', 'carlos.gomez@example.com',    INTERVAL '1 day',   NULL,               'Instalación de cámaras en curso')
)
INSERT INTO seguimiento_solicitud (
    id_solicitud, id_estado, id_profesional, id_usuario_actor,
    fecha_desde, fecha_hasta, motivo
)
SELECT
    s.id_solicitud,
    e.id_estado,
    prof.id_usuario,
    actor.id_usuario,
    s.fecha_creacion + h.offset_desde,
    CASE WHEN h.offset_hasta IS NULL THEN NULL ELSE s.fecha_creacion + h.offset_hasta END,
    h.motivo
FROM historial h
JOIN solicitud s ON s.titulo = h.titulo
JOIN estado e    ON e.nombre = h.estado
LEFT JOIN usuario up      ON up.email = h.profesional_email
LEFT JOIN profesional prof ON prof.id_usuario = up.id_usuario
LEFT JOIN usuario actor    ON actor.email = h.actor_email;

COMMIT;


-- =========================================================
-- CALIFICACION — solo para solicitudes RESUELTAS
-- =========================================================

INSERT INTO calificacion (id_solicitud, puntuacion, comentario, fecha_calificacion)
SELECT s.id_solicitud, v.puntuacion, v.comentario, ss.fecha_desde + INTERVAL '6 hours'
FROM (
    VALUES
        ('Pérdida de agua debajo de la pileta',    5::SMALLINT, 'Excelente trabajo. Llegó puntual, encontró la pérdida rápido y dejó todo funcionando perfectamente.'),
        ('Salta la térmica al encender el horno',  5::SMALLINT, 'Muy buen servicio. Detectó el problema enseguida y explicó claramente qué estaba fallando.'),
        ('Calefón se apaga durante el uso',        4::SMALLINT, 'Buen trabajo y buena atención. El calefón quedó funcionando correctamente.'),
        ('Pintar living y comedor',                5::SMALLINT, 'Quedó excelente. Muy prolijo con las terminaciones y dejó todo limpio al terminar.'),
        ('Lavarropas no centrifuga',               4::SMALLINT, 'El lavarropas volvió a funcionar bien. Buen servicio y explicación clara del problema.')
) AS v (titulo, puntuacion, comentario)
JOIN solicitud s ON s.titulo = v.titulo
JOIN seguimiento_solicitud ss ON ss.id_solicitud = s.id_solicitud
JOIN estado e ON e.id_estado = ss.id_estado AND e.nombre = 'RESUELTO'
ON CONFLICT (id_solicitud) DO UPDATE SET
    puntuacion = EXCLUDED.puntuacion,
    comentario = EXCLUDED.comentario,
    fecha_calificacion = EXCLUDED.fecha_calificacion;
