"""Certificates: issue once per (course, learner), verify by number (spec §8).

The number is ``<PREFIX>-<YYYY>-<8 Crockford base32>``, unique; a collision
is retried with a fresh draw. The public verification reveals ``number`` and
``valid`` plus only the fields ``PUBLIC_VERIFY_FIELDS`` names.
"""
from __future__ import annotations

import logging
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..errors import ERR_404_CERTIFICATE_NOT_FOUND
from ..models import Certificate, HOLDER_NAME_MAX_LENGTH
from . import CoursesError, events

logger = logging.getLogger(__name__)

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
NUMBER_RANDOM_LENGTH = 8
NUMBER_DRAWS = 5


def new_number(now=None) -> str:
    from ..conf import courses_settings

    now = now or timezone.now()
    prefix = (courses_settings.CERTIFICATE_NUMBER_PREFIX or "CERT").upper()[:10]
    tail = "".join(secrets.choice(CROCKFORD) for _ in range(NUMBER_RANDOM_LENGTH))
    return f"{prefix}-{now.year:04d}-{tail}"


def default_holder_name(user_id: str) -> str:
    """The user's full name, else empty — never an e-mail or a username."""
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    if user is None:
        return ""
    full = getattr(user, "get_full_name", lambda: "")() or ""
    return str(full).strip()[:HOLDER_NAME_MAX_LENGTH]


def _holder_name(user_id: str) -> str:
    from ..conf import courses_settings

    try:
        return str(courses_settings.HOLDER_NAME_RESOLVER(user_id) or "")[:HOLDER_NAME_MAX_LENGTH]
    except Exception:
        logger.warning("courses: HOLDER_NAME_RESOLVER failed for %s", user_id, exc_info=True)
        return ""


def issue(enrollment, emit) -> Certificate | None:
    """Issue the enrollment's certificate once; ``None`` when switched off."""
    from ..conf import courses_settings

    course = enrollment.course
    if not courses_settings.CERTIFICATES or not course.certificate_enabled:
        return None
    existing = Certificate.objects.filter(course=course, user_id=enrollment.user_id).first()
    if existing is not None:
        return existing
    now = timezone.now()
    holder = _holder_name(enrollment.user_id)
    for _ in range(NUMBER_DRAWS):
        try:
            with transaction.atomic():
                certificate = Certificate.objects.create(
                    number=new_number(now), course=course, user_id=enrollment.user_id,
                    holder_name=holder, course_title=course.title, issued_at=now,
                )
        except IntegrityError:
            existing = Certificate.objects.filter(course=course, user_id=enrollment.user_id).first()
            if existing is not None:
                return existing
            continue
        events.certificate_issued(emit, certificate)
        return certificate
    raise RuntimeError("courses: no free certificate number after %d draws" % NUMBER_DRAWS)


def public_view(number: str) -> dict:
    """The verification answer for *number*; 404 when unknown."""
    from ..conf import CERTIFICATE_FIELDS, courses_settings

    certificate = (
        Certificate.objects.select_related("course").filter(number=str(number).strip().upper()).first()
    )
    if certificate is None:
        raise CoursesError(404, ERR_404_CERTIFICATE_NOT_FOUND)
    shown = set(courses_settings.PUBLIC_VERIFY_FIELDS or ()) & set(CERTIFICATE_FIELDS)
    values = {
        "holder_name": certificate.holder_name,
        "course_title": certificate.course_title,
        "course_slug": certificate.course.slug,
        "issued_at": certificate.issued_at,
    }
    view = {"number": certificate.number, "valid": certificate.valid}
    for name in CERTIFICATE_FIELDS:
        view[name] = values[name] if name in shown else None
    return view


def revoke(certificate: Certificate, reason: str = "") -> Certificate:
    if certificate.revoked_at is None:
        certificate.revoked_at = timezone.now()
        certificate.revoke_reason = reason[:200]
        certificate.save(update_fields=["revoked_at", "revoke_reason"])
    return certificate
