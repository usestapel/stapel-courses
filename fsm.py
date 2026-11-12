"""The two lifecycles of stapel-courses as tables (spec §2, §3).

``TRANSITIONS`` is the enrollment table: ``{from: {to, ...}}``. Every move
goes through :func:`check`; ``tests/test_fsm.py`` walks every pair, so an
edge added here without a test, or a test without an edge, is red.
"""
from __future__ import annotations

from .models import CourseStatus, EnrollmentStatus

P, A, C, X, N = (
    EnrollmentStatus.PENDING,
    EnrollmentStatus.ACTIVE,
    EnrollmentStatus.COMPLETED,
    EnrollmentStatus.EXPIRED,
    EnrollmentStatus.CANCELLED,
)

TRANSITIONS: dict[str, frozenset[str]] = {
    P: frozenset({A, N}),
    A: frozenset({C, X, N}),
    C: frozenset({X, N}),
    X: frozenset({A, P}),
    N: frozenset({A, P}),
}

#: What staff may set by hand (``POST author/enrollments/{id}/transition/``).
STAFF_TARGETS = (A, X, N)

COURSE_TRANSITIONS: dict[str, frozenset[str]] = {
    CourseStatus.DRAFT: frozenset({CourseStatus.PUBLISHED}),
    CourseStatus.PUBLISHED: frozenset({CourseStatus.ARCHIVED}),
    CourseStatus.ARCHIVED: frozenset({CourseStatus.PUBLISHED}),
}


class TransitionInvalid(Exception):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"{from_status} -> {to_status}")


def allowed(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def check(from_status: str, to_status: str) -> None:
    if not allowed(from_status, to_status):
        raise TransitionInvalid(from_status, to_status)


def course_allowed(from_status: str, to_status: str) -> bool:
    return to_status in COURSE_TRANSITIONS.get(from_status, frozenset())
