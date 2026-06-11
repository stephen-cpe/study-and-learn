"""
User settings service — validates and applies user preference changes.

Used by the /settings route to guard the User model against arbitrary
input. Centralizes the allowed-value lists for avatars, TTS speakers, and
lesson difficulty so the route, template, and tests can all share one
source of truth.
"""
from __future__ import annotations

from typing import Tuple

ALLOWED_AVATARS = [
    'avatar-0.png',
    'avatar-1.png',
    'avatar-2.png',
    'avatar-3.png',
    'avatar-4.png',
    'avatar-5.png',
    'avatar-6.png',
    'avatar-7.png',
    'avatar-8.png',
]

DEFAULT_AVATAR = 'avatar-0.png'

TTS_SPEAKERS = ['Ava', 'Emma', 'Ryan', 'Andrew']
DEFAULT_TTS_SPEAKER = 'Ava'

DIFFICULTY_LEVELS = ['Easy', 'Normal', 'Hard']
DEFAULT_DIFFICULTY = 'Normal'


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes')


def validate_avatar(value) -> str:
    if value in ALLOWED_AVATARS:
        return value
    return DEFAULT_AVATAR


def validate_tts_speaker(value) -> str:
    if value in TTS_SPEAKERS:
        return value
    return DEFAULT_TTS_SPEAKER


def validate_difficulty(value) -> str:
    if value in DIFFICULTY_LEVELS:
        return value
    return DEFAULT_DIFFICULTY


def apply_settings(user, *, avatar=None, tts_enabled=None,
                   tts_speaker=None, lesson_difficulty=None) -> Tuple[bool, str]:
    """Apply validated settings to *user* in place.

    Returns ``(changed, message)``. ``changed`` is True when at least one
    field was actually different from the previous value; ``message`` is
    a short human-readable status suitable for flashing back to the UI.
    """
    changed = False
    messages = []

    if avatar is not None:
        new_avatar = validate_avatar(avatar)
        if new_avatar != user.avatar:
            user.avatar = new_avatar
            changed = True
            messages.append('Avatar updated.')

    if tts_enabled is not None:
        new_enabled = _coerce_bool(tts_enabled)
        if new_enabled != user.tts_enabled:
            user.tts_enabled = new_enabled
            changed = True
            messages.append('Text-to-Speech preference saved.')

    if tts_speaker is not None:
        new_speaker = validate_tts_speaker(tts_speaker)
        if new_speaker != user.tts_speaker:
            user.tts_speaker = new_speaker
            changed = True
            messages.append(f'TTS speaker set to {new_speaker}.')

    if lesson_difficulty is not None:
        new_diff = validate_difficulty(lesson_difficulty)
        if new_diff != user.lesson_difficulty:
            user.lesson_difficulty = new_diff
            changed = True
            messages.append(f'Lesson difficulty set to {new_diff}.')

    if not messages:
        messages.append('Settings are up to date.')
    return changed, ' '.join(messages)
