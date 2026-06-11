-- init_db.sql
-- Study-and-Learn complete schema + seed data (PostgreSQL)
-- Usage: psql -U postgres -d study_and_learn -f init_db.sql

-- Drop existing tables if they exist (for clean migration)
DROP TABLE IF EXISTS content_registry CASCADE;
DROP TABLE IF EXISTS lesson_progress CASCADE;
DROP TABLE IF EXISTS study_paths CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;

-- 1. users
CREATE TABLE users (
    id                     VARCHAR(36)  NOT NULL,
    username               VARCHAR(80)  NOT NULL,
    email                  VARCHAR(120) NOT NULL,
    password_hash          VARCHAR(255) NOT NULL,
    is_admin               BOOLEAN      NOT NULL DEFAULT FALSE,
    can_generate_lessons   BOOLEAN      NOT NULL DEFAULT FALSE,
    active_lessons         INTEGER      NOT NULL DEFAULT 0,
    avatar                 VARCHAR(32)  NOT NULL DEFAULT 'avatar-0.png',
    tts_enabled            BOOLEAN      NOT NULL DEFAULT FALSE,
    tts_speaker            VARCHAR(16)  NOT NULL DEFAULT 'Ava',
    lesson_difficulty      VARCHAR(8)   NOT NULL DEFAULT 'Normal',
    created_at             TIMESTAMP    NULL,
    updated_at             TIMESTAMP    NULL,
    CONSTRAINT pk_users PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE UNIQUE INDEX ix_users_email    ON users (email);

-- 2. study_paths
CREATE TABLE study_paths (
    id              VARCHAR(36)  NOT NULL,
    user_id         VARCHAR(36)  NOT NULL,
    title           VARCHAR(200) NOT NULL,
    learning_goal   TEXT         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'active',
    content_data    TEXT         NULL,
    extracted_texts TEXT         NULL,
    file_hashes     TEXT         NULL,
    file_names      TEXT         NULL,
    created_at      TIMESTAMP    NULL,
    updated_at      TIMESTAMP    NULL,
    CONSTRAINT pk_study_paths PRIMARY KEY (id),
    CONSTRAINT fk_study_paths_user
        FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX ix_study_paths_user_id ON study_paths (user_id);

-- 3. content_registry
CREATE TABLE content_registry (
    id                VARCHAR(36)  NOT NULL,
    file_hash         VARCHAR(64)  NOT NULL,
    chroma_collection VARCHAR(128) NOT NULL,
    extracted_text    TEXT         NULL,
    ocr_text          TEXT         NULL,
    created_at        TIMESTAMP    NULL,
    CONSTRAINT pk_content_registry PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_content_registry_file_hash ON content_registry (file_hash);
CREATE UNIQUE INDEX ix_content_registry_chroma_collection ON content_registry (chroma_collection);

-- 4. lesson_progress
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

-- 5. alembic_version stamp
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT pk_alembic_version PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('7477e6809a28');

-- 6. Seed users (development only -- not for production)
--
-- Passwords (plaintext for reference only; stored as scrypt hashes below):
--   admin  → ADMINpassword
--   bob    → BOBpassword
--   alice  → ALICEpassword
--
-- Roles:
--   admin  is_admin=True   can_generate_lessons=True   (admin access)
--   bob    is_admin=False  can_generate_lessons=True   (regular user, full app access)
--   alice  is_admin=False  can_generate_lessons=True   (regular user, full app access)
--   (all other signups default to can_generate_lessons=False)

INSERT INTO users (id, username, email, password_hash, is_admin, can_generate_lessons)
VALUES
(
    'aa7a8fcd-85d3-421d-851d-5c9f14ae880f',
    'admin',
    'admin@example.edu',
    'scrypt:32768:8:1$orm6oLX62gzRo2Ht$daa27569d1cd4d859f5ce99d4fed3dbaeca2bc35756508d95ecf0966f008f9581459ded546cc37a87884bd4084c300abcb8cf896dd8c192e59c3abd3c798bc56',
    TRUE,
    TRUE
),
(
    '3bf62c13-1186-40bd-a566-9d01d1772137',
    'bob',
    'bob@example.edu',
    'scrypt:32768:8:1$Nyzt1gBq2PJ2Lwr4$2fdacd585c05889c0c4e4e2519ffd9b5b46a480ba77fdb0f10197a12d41e6c2d327dac8c76b407e89ce4fc7bc55c18816c9ba6d8aec0614a981517c8e00c899b',
    FALSE,
    TRUE
),
(
    'b3849b89-f5ec-4c6a-87fc-5917f8608fe2',
    'alice',
    'alice@example.edu',
    'scrypt:32768:8:1$9cqM2CovqXel2vwf$d9cd085203ee79596568bbfcbdadc908a404dfc35e4fd8ffb62519cfffa13c2e5c1df1fb413dcf793940acc26c610903ab8475da2fbe01a07195cf849a9a6b57',
    FALSE,
    TRUE
);

-- 7. Permissions
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO study_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO study_user;
