-- init_db.sql
-- Study-and-Learn complete schema (PostgreSQL)
-- Usage: psql -U postgres -d study_and_learn -f init_db.sql
-- Run this after "CREATE DATABASE study_and_learn" and the GRANTs below.

-- ═══════════════════════════════════════════════════════════════════════════
-- Pre-flight (run manually in psql BEFORE loading this file):
--   CREATE DATABASE study_and_learn;
--   CREATE USER study_user WITH PASSWORD 'study_pass';
--   GRANT ALL PRIVILEGES ON DATABASE study_and_learn TO study_user;
--   GRANT CREATE ON SCHEMA public TO study_user;

BEGIN;

-- ── 1. users ───────────────────────────────────────────────────────────────
CREATE TABLE users (
    id              VARCHAR(36)  NOT NULL,
    username        VARCHAR(80)  NOT NULL,
    email           VARCHAR(120) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    is_admin        BOOLEAN      NOT NULL DEFAULT FALSE,
    can_generate_lessons BOOLEAN  NOT NULL DEFAULT FALSE,
    active_lessons  INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMP    NULL,
    updated_at      TIMESTAMP    NULL,
    CONSTRAINT pk_users PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE UNIQUE INDEX ix_users_email    ON users (email);

-- ── 2. study_paths ─────────────────────────────────────────────────────────
CREATE TABLE study_paths (
    id              VARCHAR(36)  NOT NULL,
    user_id         VARCHAR(36)  NOT NULL,
    title           VARCHAR(200) NOT NULL,
    learning_goal   TEXT         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'active',
    content_data    TEXT         NULL,
    created_at      TIMESTAMP    NULL,
    updated_at      TIMESTAMP    NULL,
    CONSTRAINT pk_study_paths PRIMARY KEY (id),
    CONSTRAINT fk_study_paths_user
        FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX ix_study_paths_user_id ON study_paths (user_id);

-- ── 3. lesson_progress ─────────────────────────────────────────────────────
CREATE TABLE lesson_progress (
    id              VARCHAR(36)  NOT NULL,
    study_path_id   VARCHAR(36)  NOT NULL,
    module_index    INTEGER      NOT NULL,
    score           INTEGER      NULL,
    passed          BOOLEAN      NOT NULL DEFAULT FALSE,
    completed       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NULL,
    updated_at      TIMESTAMP    NULL,
    CONSTRAINT pk_lesson_progress PRIMARY KEY (id),
    CONSTRAINT fk_lesson_progress_study_path
        FOREIGN KEY (study_path_id) REFERENCES study_paths (id)
);

CREATE INDEX ix_lesson_progress_study_path_id ON lesson_progress (study_path_id);

-- ── 4. alembic_version stamp ───────────────────────────────────────────────
-- Stamp to 'c1d0e553b531' so 'flask db upgrade' sees DB as current.
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT pk_alembic_version PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('c1d0e553b531');

-- ── Permissions for study_user ─────────────────────────────────────────────
-- The tables are created by the superuser, so we must explicitly grant.
ALTER TABLE users           OWNER TO study_user;
ALTER TABLE study_paths     OWNER TO study_user;
ALTER TABLE lesson_progress OWNER TO study_user;
ALTER TABLE alembic_version OWNER TO study_user;

GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO study_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO study_user;

COMMIT;
