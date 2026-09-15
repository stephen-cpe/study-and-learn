"""
SQLAlchemy models for Study-and-Learn — PostgreSQL-only.
"""
import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from werkzeug.security import check_password_hash, generate_password_hash

from src import db
from src.services.settings_service import (
    DEFAULT_DIFFICULTY,
    DEFAULT_TTS_SPEAKER,
)


def _utcnow():
    return datetime.now(timezone.utc)


# ── StudyPath status lifecycle ─────────────────────────────────────────
# Canonical status values for StudyPath.status. Queries and route
# handlers must use these constants so a typo cannot silently match
# nothing (e.g. 'actve').
PATH_STATUS_ACTIVE = 'active'
PATH_STATUS_COMPLETED = 'completed'
PATH_STATUS_CANCELLED = 'cancelled'
PATH_STATUSES = (PATH_STATUS_ACTIVE, PATH_STATUS_COMPLETED, PATH_STATUS_CANCELLED)


class User(db.Model, UserMixin):
    """Application user with Flask-Login integration."""
    __tablename__ = 'users'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    username = db.Column(String(80), unique=True, index=True, nullable=False)
    nickname = db.Column(String(40), nullable=True)
    full_name = db.Column(String(80), nullable=True)
    email = db.Column(String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(String(255), nullable=False)
    is_admin = db.Column(Boolean, default=False, nullable=False)
    can_generate_lessons = db.Column(Boolean, default=False, nullable=False)
    avatar = db.Column(String(32), nullable=False, default='avatar-0.png')
    tts_enabled = db.Column(Boolean, nullable=False, default=False)
    tts_speaker = db.Column(String(16), nullable=False, default=DEFAULT_TTS_SPEAKER)
    lesson_difficulty = db.Column(String(8), nullable=False, default=DEFAULT_DIFFICULTY)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    def set_password(self, password: str) -> None:
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return True if *password* matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email}) admin={self.is_admin} gen={self.can_generate_lessons}>"

    @property
    def display_name(self) -> str:
        """Friendly name for UI/TTS: nickname if set, else full_name, else username.

        Used by the navbar, dashboard greeting, mascot speech bubble, and
        TTS narration prompt so the learner is addressed by a name they
        chose rather than their login handle.
        """
        return self.nickname or self.full_name or self.username

    @property
    def active_lesson_count(self) -> int:
        """Return the number of active StudyPath records for this user."""
        return StudyPath.query.filter_by(user_id=self.id, status=PATH_STATUS_ACTIVE).count()

    def can_start_new_lesson(self) -> bool:
        """Return True if the user has fewer than 3 active lessons."""
        return self.active_lesson_count < 3


class StudyPath(db.Model):
    """A study path created from a learning goal and uploaded materials."""
    __tablename__ = 'study_paths'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(String(200), nullable=False)
    learning_goal = db.Column(Text, nullable=False)
    status = db.Column(String(20), default=PATH_STATUS_ACTIVE, nullable=False)
    content_data = db.Column(db.Text, nullable=True)
    extracted_texts = db.Column(db.Text, nullable=True)
    file_hashes = db.Column(db.Text, nullable=True)
    file_names = db.Column(db.Text, nullable=True)
    # Full-coverage map-reduce digest of every extracted chunk, stored at
    # processing time and reused by lesson generation so the LLM is grounded
    # in the entire document rather than only the retrieved chunks.  Cleared
    # after lesson generation (same lifecycle as extracted_texts).
    content_digest = db.Column(db.Text, nullable=True)
    # Durable study-plan snapshot for post-generation features (suggest-next):
    # the planned modules, the document summary, and the relevance verdict.
    # Unlike extracted_texts/content_digest these are NEVER cleared — they
    # are small and needed long after generation (session data expires).
    modules_json = db.Column(db.Text, nullable=True)
    summary_text = db.Column(db.Text, nullable=True)
    relevance_json = db.Column(db.Text, nullable=True)
    generation_completed_at = db.Column(DateTime, nullable=True)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship('User', backref=db.backref('study_paths', lazy='dynamic'))

    def __repr__(self) -> str:
        return f"<StudyPath {self.title} status={self.status}>"


class ContentRegistry(db.Model):
    __tablename__ = 'content_registry'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    file_hash = db.Column(String(64), unique=True, index=True, nullable=False)
    chroma_collection = db.Column(String(128), unique=True, nullable=False)
    extracted_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<ContentRegistry hash={self.file_hash} collection={self.chroma_collection}>"


class LessonProgress(db.Model):
    """Progress tracking for an individual module within a study path."""
    __tablename__ = 'lesson_progress'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    study_path_id = db.Column(String(36), db.ForeignKey('study_paths.id'), nullable=False, index=True)
    module_index = db.Column(Integer, nullable=False)
    score = db.Column(Integer, nullable=True)
    passed = db.Column(Boolean, default=False, nullable=False)
    completed = db.Column(Boolean, default=False, nullable=False)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    study_path = db.relationship('StudyPath', backref=db.backref('lessons', lazy='dynamic'))

    def __repr__(self) -> str:
        return f"<LessonProgress module={self.module_index} score={self.score} passed={self.passed}>"


class MascotMemory(db.Model):
    """Long-term per-learner memory for the mascot's personality engine.

    Three memory types (mirrors the Eternal Fusion Pavilion pattern):
    * ``semantic`` — stable preferences ("prefers Hard difficulty")
    * ``episodic`` — events ("finished module 3 of Cell Biology")
    * ``procedural`` — how-to ("likes to be called Bobby")

    The mascot's line generator retrieves these at speak time and injects
    them into the LLM context as a ``[Learner Profile]`` block so the
    generated line can reference past activity.
    """
    __tablename__ = 'mascot_memory'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    memory_type = db.Column(String(20), nullable=False)
    content = db.Column(Text, nullable=False)
    created_at = db.Column(DateTime, default=_utcnow)

    VALID_TYPES = ('semantic', 'episodic', 'procedural')

    def __repr__(self) -> str:
        return f"<MascotMemory type={self.memory_type} content={self.content[:60]!r}>"


SUGGESTION_STATUS_PENDING = 'pending'
SUGGESTION_STATUS_ACCEPTED = 'accepted'
SUGGESTION_STATUS_DISMISSED = 'dismissed'
SUGGESTION_STATUS_COMPLETED = 'completed'


class Suggestion(db.Model):
    """A suggested next topic for a study path (suggest-next feature).

    Suggestions are computed from document coverage (unpassed modules +
    LLM diff of taught vs planned topics) and shown on the lessons page.
    Accepting one generates a full module via the standard lesson
    machinery; dismissing hides it permanently. ``status`` is one of
    pending/accepted/dismissed/completed.
    """
    __tablename__ = 'suggestion'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    study_path_id = db.Column(String(36), db.ForeignKey('study_paths.id'), nullable=False, index=True)
    title = db.Column(String(200), nullable=False)
    reason = db.Column(Text, nullable=True)
    source_refs = db.Column(Text, nullable=True)
    status = db.Column(String(20), default=SUGGESTION_STATUS_PENDING, nullable=False)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    VALID_STATUSES = (
        SUGGESTION_STATUS_PENDING,
        SUGGESTION_STATUS_ACCEPTED,
        SUGGESTION_STATUS_DISMISSED,
        SUGGESTION_STATUS_COMPLETED,
    )

    user = db.relationship('User', backref=db.backref('suggestions', lazy='dynamic'))
    study_path = db.relationship('StudyPath', backref=db.backref('suggestions', lazy='dynamic'))

    def __repr__(self) -> str:
        return f"<Suggestion {self.title} status={self.status}>"


TASK_KIND_PROCESS = 'process'
TASK_KIND_GENERATE = 'generate'
TASK_STATUS_RUNNING = 'running'
TASK_STATUS_READY = 'ready'
TASK_STATUS_FAILED = 'failed'


class BackgroundTask(db.Model):
    """Durable cross-tab record for long-running user tasks (bell UX).

    ``task_id`` is the client-generated UUID (also used as the
    progress_tracker key). While the in-page 2s poller gives live detail,
    this row is the durable cross-tab signal: any tab polls ``/tasks`` and
    deep-links via ``result_url`` once ``status`` flips to ready/failed.
    ``read`` drives the navbar bell badge (unread finished tasks).
    """
    __tablename__ = 'background_task'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    task_id = db.Column(String(64), unique=True, index=True, nullable=False)
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    kind = db.Column(String(20), default=TASK_KIND_PROCESS, nullable=False)
    status = db.Column(String(20), default=TASK_STATUS_RUNNING, nullable=False)
    pct = db.Column(Integer, nullable=True)
    label = db.Column(String(200), nullable=True)
    path_id = db.Column(String(36), nullable=True)
    result_url = db.Column(String(500), nullable=True)
    error = db.Column(Text, nullable=True)
    read = db.Column(Boolean, default=False, nullable=False)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    VALID_KINDS = (TASK_KIND_PROCESS, TASK_KIND_GENERATE)
    VALID_STATUSES = (TASK_STATUS_RUNNING, TASK_STATUS_READY, TASK_STATUS_FAILED)

    user = db.relationship('User', backref=db.backref('background_tasks', lazy='dynamic'))

    def __repr__(self) -> str:
        return f"<BackgroundTask {self.kind} status={self.status}>"
