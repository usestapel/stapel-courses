"""Service layer of stapel-courses: catalog, authoring, enrollment, progress,
quizzes, certificates and the orders facts.

Views and comm handlers call these; nothing here knows about HTTP beyond the
status a refusal carries. A refusal is a :class:`CoursesError` (a
``StapelServiceError``), which the fleet exception handler renders as the
error envelope.
"""
from __future__ import annotations

from stapel_core.django.api.errors import StapelServiceError


class CoursesError(StapelServiceError):
    """A domain refusal with its HTTP status, i18n error key and params."""

    @property
    def status(self) -> int:
        return self.http_status

    @property
    def key(self) -> str:
        return self.error_key

    @property
    def params(self) -> dict:
        return self.error_params


def user_id_of(user) -> str | None:
    """``str(user.pk)`` for an authenticated user (a guest row included), else None."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return str(user.pk)


def is_guest(user) -> bool:
    """A stapel-auth guest row: authenticated, flagged anonymous."""
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_anonymous", False))


def is_staff(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


__all__ = ["CoursesError", "user_id_of", "is_guest", "is_staff"]
