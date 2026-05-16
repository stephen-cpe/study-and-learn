"""
SQLAlchemy models for Study-and-Learn — PostgreSQL-only.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime
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
        return f"<User {self.username} ({self.email}) admin={self.is_admin}>"
