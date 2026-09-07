-- =========================================================
-- 001 — Rol de administrador
--
-- El DDL original no tiene forma de distinguir un admin: `cuenta` solo guarda
-- username, password_hash y activo, y los subtipos (cliente / profesional) son
-- roles de negocio, no de sistema.
--
-- Sin esta columna no hay manera de proteger los endpoints de backoffice
-- (ABM de catalogos, borrado real de solicitudes, transiciones forzadas).
--
-- Correr una sola vez contra la base barriofix.
-- =========================================================

ALTER TABLE cuenta
    ADD COLUMN IF NOT EXISTS es_admin BOOLEAN NOT NULL DEFAULT FALSE;


-- Promover una cuenta existente a admin (reemplazar el username):
--
--   UPDATE cuenta SET es_admin = TRUE WHERE username = 'tu_usuario';
