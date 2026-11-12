"""GDPR for stapel-courses.

Export of an ``account``: enrollments, lesson progress, quiz attempts (with
the answers given) and certificates.

Erasure of an ``account``: lesson progress, quiz attempts, enrollments and
purchase ledger rows are deleted (none of them is the economic record — that
is the order, which stapel-orders keeps). Certificates are anonymised: the
user id becomes the fleet pseudonym, the holder name is cleared and the
certificate is revoked, so a public verification answers ``valid: false``
and names nobody. Authored courses keep their ``author_id`` pseudonymised.

One operation, :func:`erase_subject`, reached by the in-process provider and
by ``register_gdpr_owner``'s ``gdpr.erasure.requested`` / ``user.deleted``
subscribers alike.
"""
from __future__ import annotations

from stapel_core.gdpr import GDPRProvider

ERASED_REASON = "erased"


def _iso(value):
    return value.isoformat() if value is not None else None


class CoursesGDPRProvider(GDPRProvider):
    section = "courses"

    def export(self, user_id) -> dict:
        from .models import Attempt, Certificate, Enrollment, LessonProgress

        user_id = str(user_id)
        return {
            "enrollments": [
                {
                    "course": e.course.slug,
                    "status": e.status,
                    "source": e.source,
                    "order_id": e.order_id,
                    "activated_at": _iso(e.activated_at),
                    "expires_at": _iso(e.expires_at),
                    "completed_at": _iso(e.completed_at),
                    "progress_percent": e.progress_percent,
                }
                for e in Enrollment.objects.filter(user_id=user_id).select_related("course")
            ],
            "lesson_progress": [
                {
                    "course": p.course.slug,
                    "lesson_id": p.lesson_id,
                    "status": p.status,
                    "position_seconds": p.position_seconds,
                    "started_at": _iso(p.started_at),
                    "completed_at": _iso(p.completed_at),
                }
                for p in LessonProgress.objects.filter(user_id=user_id).select_related("course")
            ],
            "quiz_attempts": [
                {
                    "quiz_id": a.quiz_id,
                    "number": a.number,
                    "status": a.status,
                    "answers": a.answers,
                    "score": a.score,
                    "max_score": a.max_score,
                    "percent": None if a.percent is None else str(a.percent),
                    "passed": a.passed,
                    "started_at": _iso(a.started_at),
                    "submitted_at": _iso(a.submitted_at),
                }
                for a in Attempt.objects.filter(user_id=user_id)
            ],
            "certificates": [
                {
                    "number": c.number,
                    "course_title": c.course_title,
                    "holder_name": c.holder_name,
                    "issued_at": _iso(c.issued_at),
                    "revoked_at": _iso(c.revoked_at),
                }
                for c in Certificate.objects.filter(user_id=user_id)
            ],
        }

    def delete(self, user_id) -> None:
        erase_subject("account", user_id)

    #: Erasure leaves only pseudonymised certificates: that IS the
    #: anonymisation, so one operation answers both names.
    anonymize = delete


OWNER = CoursesGDPRProvider.section
SUBJECT_TYPES = ("account",)


def erase_subject(subject_type, subject_key, workspace_id=None):
    """Erase one account's learning data. Idempotent; counts what it touched."""
    from django.db import transaction
    from django.utils import timezone
    from stapel_core.gdpr.owners import pseudonymize

    from .models import Attempt, Certificate, Course, CoursePurchase, Enrollment, LessonProgress

    if subject_type != "account" or not subject_key:
        return None
    user_id = str(subject_key)
    pseudonym = pseudonymize(user_id)
    with transaction.atomic():
        progress, _ = LessonProgress.objects.filter(user_id=user_id).delete()
        attempts, _ = Attempt.objects.filter(user_id=user_id).delete()
        enrollments, _ = Enrollment.objects.filter(user_id=user_id).delete()
        purchases, _ = CoursePurchase.objects.filter(user_id=user_id).delete()
        certificates = Certificate.objects.filter(user_id=user_id).update(
            user_id=pseudonym, holder_name="", revoked_at=timezone.now(),
            revoke_reason=ERASED_REASON,
        )
        authored = Course.objects.filter(author_id=user_id).update(author_id=pseudonym)
    return {
        "lesson_progress": progress,
        "quiz_attempts": attempts,
        "enrollments": enrollments,
        "purchases": purchases,
        "certificates": certificates,
        "authored_courses": authored,
    }
