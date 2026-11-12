"""The entitlement question, asked of the billing Function by name.

``ENTITLEMENT_FUNCTION`` (default ``billing.check_entitlement``) answers
``{user_id, key}`` -> ``{allowed, limit, reason}``. The key is
``course.entitlement_key`` or ``ENTITLEMENT_KEY_TEMPLATE`` formatted with the
course. Answers are cached ``ENTITLEMENT_CACHE_SECONDS``. An unreachable or
malformed answer is a 503 (``error.503.entitlement_unavailable``) — access is
never granted or refused on a guess.
"""
from __future__ import annotations

import logging

from django.core.cache import cache

from ..errors import ERR_503_ENTITLEMENT_UNAVAILABLE
from . import CoursesError

logger = logging.getLogger(__name__)

CACHE_PREFIX = "stapel_courses:entitlement:"


def entitlement_key(course) -> str:
    from ..conf import courses_settings

    if course.entitlement_key:
        return course.entitlement_key
    template = courses_settings.ENTITLEMENT_KEY_TEMPLATE or "course:{slug}"
    try:
        return template.format(slug=course.slug, course_id=course.pk)
    except (KeyError, IndexError, ValueError):
        logger.warning("ENTITLEMENT_KEY_TEMPLATE %r cannot be formatted", template)
        return f"course:{course.slug}"


def _unavailable(reason: str) -> CoursesError:
    logger.warning("courses: entitlement check unavailable: %s", reason)
    return CoursesError(503, ERR_503_ENTITLEMENT_UNAVAILABLE)


def entitled(user_id: str, course) -> bool:
    """Does the billing Function allow *user_id* the course's entitlement key?"""
    from stapel_core.comm import CommError, call, function_unreachable_reason

    from ..conf import courses_settings

    key = entitlement_key(course)
    cache_key = f"{CACHE_PREFIX}{user_id}:{key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)
    name = courses_settings.ENTITLEMENT_FUNCTION
    reason = function_unreachable_reason(name)
    if reason:
        raise _unavailable(f"{name}: {reason}")
    try:
        reply = call(name, {"user_id": str(user_id), "key": key})
    except CommError as exc:
        raise _unavailable(f"{name} failed: {exc}") from exc
    if not isinstance(reply, dict) or not isinstance(reply.get("allowed"), bool):
        raise _unavailable(f"{name} answered outside its contract")
    allowed = reply["allowed"]
    ttl = int(courses_settings.ENTITLEMENT_CACHE_SECONDS or 0)
    if ttl > 0:
        cache.set(cache_key, allowed, ttl)
    return allowed
