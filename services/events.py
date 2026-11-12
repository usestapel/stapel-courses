"""Facts and courtesies stapel-courses sends: emits and notifications.

Emits go through the caller's ``mutate_and_emit`` emitter, so the outbox row
commits with the mutation. Only ids, statuses and instants ride the bus — no
names, no answers. Notifications are best-effort and leave after commit.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

EVENT_ENROLLMENT_ACTIVATED = "courses.enrollment.activated"
EVENT_ENROLLMENT_STATUS_CHANGED = "courses.enrollment.status_changed"
EVENT_COURSE_COMPLETED = "courses.course.completed"
EVENT_CERTIFICATE_ISSUED = "courses.certificate.issued"

EMITS = (
    EVENT_ENROLLMENT_ACTIVATED,
    EVENT_ENROLLMENT_STATUS_CHANGED,
    EVENT_COURSE_COMPLETED,
    EVENT_CERTIFICATE_ISSUED,
)

NOTIFY_ENROLLMENT_ACTIVATED = "courses.enrollment_activated"
NOTIFY_COMPLETED = "courses.completed"
NOTIFY_CERTIFICATE_ISSUED = "courses.certificate_issued"


def _iso(value):
    return value.isoformat() if value is not None else None


def enrollment_activated(emit, enrollment) -> None:
    emit(  # emit-check: ok — emit is always a caller's mutate_and_emit emitter
        EVENT_ENROLLMENT_ACTIVATED,
        {
            "enrollment_id": str(enrollment.pk),
            "course_id": str(enrollment.course_id),
            "course_slug": enrollment.course.slug,
            "user_id": enrollment.user_id,
            "source": enrollment.source,
            "order_id": enrollment.order_id or None,
            "expires_at": _iso(enrollment.expires_at),
        },
        key=str(enrollment.pk),
    )
    notify_after_commit(NOTIFY_ENROLLMENT_ACTIVATED, enrollment.user_id, enrollment.course)


def enrollment_status_changed(emit, enrollment, from_status: str, actor: str, reason: str = "") -> None:
    payload = {
        "enrollment_id": str(enrollment.pk),
        "course_id": str(enrollment.course_id),
        "user_id": enrollment.user_id,
        "from": from_status,
        "to": enrollment.status,
        "actor": actor,
    }
    if reason:
        payload["reason"] = reason[:200]
    emit(  # emit-check: ok — emit is always a caller's mutate_and_emit emitter
        EVENT_ENROLLMENT_STATUS_CHANGED, payload, key=str(enrollment.pk)
    )


def course_completed(emit, enrollment) -> None:
    emit(  # emit-check: ok — emit is always a caller's mutate_and_emit emitter
        EVENT_COURSE_COMPLETED,
        {
            "enrollment_id": str(enrollment.pk),
            "course_id": str(enrollment.course_id),
            "course_slug": enrollment.course.slug,
            "user_id": enrollment.user_id,
            "completed_at": _iso(enrollment.completed_at),
        },
        key=str(enrollment.pk),
    )
    notify_after_commit(NOTIFY_COMPLETED, enrollment.user_id, enrollment.course)


def certificate_issued(emit, certificate) -> None:
    emit(  # emit-check: ok — emit is always a caller's mutate_and_emit emitter
        EVENT_CERTIFICATE_ISSUED,
        {
            "certificate_id": str(certificate.pk),
            "number": certificate.number,
            "course_id": str(certificate.course_id),
            "user_id": certificate.user_id,
            "issued_at": _iso(certificate.issued_at),
        },
        key=str(certificate.pk),
    )
    notify_after_commit(
        NOTIFY_CERTIFICATE_ISSUED, certificate.user_id, certificate.course,
        certificate_number=certificate.number,
        certificate_url=_format(
            "CERTIFICATE_URL_TEMPLATE", number=certificate.number, course_id=certificate.course_id,
            slug=certificate.course.slug,
        ),
    )


def _format(setting: str, **values) -> str:
    from ..conf import courses_settings

    template = getattr(courses_settings, setting) or ""
    if not template:
        return ""
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        logger.warning("%s %r cannot be formatted", setting, template)
        return ""


def variables(course, **extra) -> dict:
    return {
        "course_id": str(course.pk),
        "course_slug": course.slug,
        "course_title": course.title,
        "course_url": _format("COURSE_URL_TEMPLATE", slug=course.slug, course_id=course.pk),
        **extra,
    }


def notify(notification_type: str, user_id: str, data: dict) -> bool:
    """Send one notification now (best-effort). Returns whether it was queued."""
    from ..conf import courses_settings

    if not courses_settings.NOTIFY or not user_id:
        return False
    try:
        from stapel_core.notifications.publish import request_notification

        return bool(request_notification(
            notification_type, user_id=user_id, variables=data, source_service="courses",
        ))
    except Exception:
        logger.warning(
            "courses: %s notification for course %s not sent",
            notification_type, data.get("course_id"), exc_info=True,
        )
        return False


def notify_after_commit(notification_type: str, user_id: str, course, **extra) -> None:
    from ..conf import courses_settings

    if not courses_settings.NOTIFY or not user_id:
        return
    data = variables(course, **extra)
    transaction.on_commit(lambda: notify(notification_type, user_id, data))
