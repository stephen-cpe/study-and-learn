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
