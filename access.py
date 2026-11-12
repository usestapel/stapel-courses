"""Access gate strategies and their registry (spec §4).

``Course.access`` names a strategy. A strategy answers two questions:

- :meth:`AccessStrategy.self_enroll_source` — may this learner enroll
  themself, and with which source? Raise :class:`~.services.CoursesError`
  to refuse.
- :meth:`AccessStrategy.content_access` — does this learner (``user_id`` or
  ``None`` for an anonymous request, and their enrollment or ``None``) see
  the course's content? Answer a :class:`Decision` whose ``reason`` is a
  lock reason from :data:`LOCK_REASONS`.

Staff and the course's author always pass (the gate in
``services/gate.py`` asks before any strategy). A ``free_preview`` lesson
never reaches a strategy.

``STAPEL_COURSES["ACCESS_STRATEGIES"]`` merges ``{name: "dotted.path" |
None}`` over the built-ins; a dotted path under a built-in name replaces it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.utils.module_loading import import_string

from .models import EnrollmentSource

SIGN_IN_REQUIRED = "sign_in_required"
ENROLLMENT_REQUIRED = "enrollment_required"
PURCHASE_REQUIRED = "purchase_required"
ENTITLEMENT_REQUIRED = "entitlement_required"
ENROLLMENT_INACTIVE = "enrollment_inactive"
DRIP = "drip"
SEQUENTIAL = "sequential"

LOCK_REASONS = (
    SIGN_IN_REQUIRED,
    ENROLLMENT_REQUIRED,
    PURCHASE_REQUIRED,
    ENTITLEMENT_REQUIRED,
    ENROLLMENT_INACTIVE,
    DRIP,
    SEQUENTIAL,
)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Optional[str] = None


OPEN = Decision(True)


class AccessStrategy:
    """Base strategy: content needs an enrollment that grants access."""

    #: The reason a learner without an enrollment is shown.
    missing_reason = ENROLLMENT_REQUIRED

    def self_enroll_source(self, course, user_id: str) -> str:
        return EnrollmentSource.FREE

    def content_access(self, course, user_id: Optional[str], enrollment) -> Decision:
        if user_id is None:
            return Decision(False, SIGN_IN_REQUIRED)
        if enrollment is None:
            return Decision(False, self.missing_reason)
        if not enrollment.grants_access:
            return Decision(False, ENROLLMENT_INACTIVE)
        return OPEN


class FreeAccess(AccessStrategy):
    """Content is open to everyone; enrolling only tracks progress."""

    def content_access(self, course, user_id, enrollment) -> Decision:
        return OPEN


class EnrolledAccess(AccessStrategy):
    """Content needs an enrollment; anyone may enroll for free."""


class PurchasedAccess(AccessStrategy):
    """Content needs an enrollment from an order (or a staff grant)."""

    missing_reason = PURCHASE_REQUIRED

    def self_enroll_source(self, course, user_id: str) -> str:
        from .errors import ERR_403_PURCHASE_REQUIRED
        from .services import CoursesError

        raise CoursesError(403, ERR_403_PURCHASE_REQUIRED, {"course_id": str(course.pk)})


class EntitlementAccess(AccessStrategy):
    """Content needs an enrollment and a plan entitlement (billing Function)."""

    missing_reason = ENTITLEMENT_REQUIRED

    def self_enroll_source(self, course, user_id: str) -> str:
        from .errors import ERR_403_ENTITLEMENT_REQUIRED
        from .services import CoursesError
        from .services.entitlements import entitled

        if not entitled(user_id, course):
            raise CoursesError(403, ERR_403_ENTITLEMENT_REQUIRED, {"course_id": str(course.pk)})
        return EnrollmentSource.ENTITLEMENT

    def content_access(self, course, user_id, enrollment) -> Decision:
        decision = super().content_access(course, user_id, enrollment)
        if not decision.allowed or enrollment.source != EnrollmentSource.ENTITLEMENT:
            return decision
        from .services.entitlements import entitled

        return OPEN if entitled(user_id, course) else Decision(False, ENTITLEMENT_REQUIRED)


BUILTIN_STRATEGIES: dict[str, str] = {
    "free": "stapel_courses.access.FreeAccess",
    "enrolled": "stapel_courses.access.EnrolledAccess",
    "purchased": "stapel_courses.access.PurchasedAccess",
    "entitlement": "stapel_courses.access.EntitlementAccess",
}


def strategy_paths() -> dict[str, str]:
    """Effective registry: built-ins <- settings, live entries only."""
    from .conf import courses_settings

    merged: dict[str, Optional[str]] = dict(BUILTIN_STRATEGIES)
    configured = courses_settings.ACCESS_STRATEGIES or {}
    if isinstance(configured, dict):
        merged.update(configured)
    return {name: path for name, path in merged.items() if path}


def strategy_names() -> list[str]:
    return sorted(strategy_paths())


def get_strategy(name: str) -> AccessStrategy:
    """The strategy *name* resolves to; an unknown name gates like ``enrolled``.

    A course whose strategy was removed from the registry stays closed to
    non-enrolled learners instead of opening up (fail closed).
    """
    path = strategy_paths().get(name) or BUILTIN_STRATEGIES["enrolled"]
    return import_string(path)()
