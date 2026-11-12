"""The housekeeping schedule — shipped by the library.

Wire it in the settings module itself::

    from stapel_courses.beat import get_courses_beat_schedule

    CELERY_BEAT_SCHEDULE = {**get_courses_beat_schedule(), ...}

One pass: enrollments past ``expires_at`` become ``expired`` (every 15
minutes). Imports nothing at module level, so it is safe from a settings
module. Celery is optional: ``manage.py courses_housekeeping`` runs the same
pass from any scheduler.
"""
from __future__ import annotations

EXPIRE_TASK_NAME = "stapel_courses.beat.expire_enrollments"
EXPIRE_BEAT_KEY = "courses-expire-enrollments"
EXPIRE_INTERVAL_SECONDS = 15 * 60


def expire_enrollments() -> int:
    """One expiry pass. A plain callable for hosts without Celery."""
    from .services.enrollments import expire_due

    return expire_due()


def get_courses_beat_schedule() -> dict:
    """Beat entries. Add to ``CELERY_BEAT_SCHEDULE``."""
    return {
        EXPIRE_BEAT_KEY: {"task": EXPIRE_TASK_NAME, "schedule": float(EXPIRE_INTERVAL_SECONDS)},
    }


try:  # pragma: no cover - exercised by whichever profile the host installs
    from celery import shared_task
except ImportError:
    pass
else:
    expire_enrollments = shared_task(name=EXPIRE_TASK_NAME)(expire_enrollments)


__all__ = [
    "EXPIRE_BEAT_KEY",
    "EXPIRE_TASK_NAME",
    "expire_enrollments",
    "get_courses_beat_schedule",
]
