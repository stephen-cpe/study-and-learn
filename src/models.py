"""
SQLAlchemy models for Study-and-Learn — PostgreSQL-only.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, Integer, DateTime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from src import db


def _utcnow():
    return datetime.now(timezone.utc)


class User(db.Model, UserMixin):
    """Application user with Flask-Login integration."""
    __tablename__ = 'users'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    username = db.Column(String(80), unique=True, index=True, nullable=False)
    email = db.Column(String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(String(255), nullable=False)
    is_admin = db.Column(Boolean, default=False, nullable=False)
    can_generate_lessons = db.Column(Boolean, default=False, nullable=False)
    active_lessons = db.Column(Integer, default=0, nullable=False)
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
    def active_lesson_count(self) -> int:
        """Return the number of active StudyPath records for this user."""
        return StudyPath.query.filter_by(user_id=self.id, status='active').count()

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
    status = db.Column(String(20), default='active', nullable=False)
    content_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(DateTime, default=_utcnow)
    updated_at = db.Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship('User', backref=db.backref('study_paths', lazy='dynamic'))

    def __repr__(self) -> str:
        return f"<StudyPath {self.title} status={self.status}>"


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
