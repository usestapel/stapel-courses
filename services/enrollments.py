"""Enrollments: self-enrollment, grants, the FSM, expiry, merges (spec §3-§5).

Every status move goes through :func:`move`, which checks ``fsm.py`` and
emits ``courses.enrollment.status_changed`` (and ``.activated`` when the
target is ``active``) through the caller's ``mutate_and_emit`` emitter.
Rows are created under the ``(course, user_id)`` uniqueness, never
read-then-create: a racing second writer re-reads the winner's row.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from stapel_core.comm import mutate_and_emit

from .. import fsm
from ..errors import (
    ERR_403_ENROLLMENT_REQUIRES_ACCOUNT,
    ERR_404_ENROLLMENT_NOT_FOUND,
    ERR_409_COURSE_NOT_PUBLISHED,
    ERR_409_ENROLLMENT_TRANSITION_INVALID,
)
from ..models import (
    GRANTING_STATUSES,
    Attempt,
    Certificate,
    Course,
    CoursePurchase,
    CourseStatus,
    Enrollment,
    EnrollmentSource,
    EnrollmentStatus,
    LessonProgress,
    PROGRESS_RANK,
)
from . import CoursesError, events, is_guest, user_id_of

logger = logging.getLogger(__name__)

SYSTEM = "system"
LEARNER = "learner"
STAFF = "staff"
ORDER = "order"
ACTORS = (SYSTEM, LEARNER, STAFF, ORDER)

#: Upper bound of rows one housekeeping pass touches.
BATCH = 500


def for_user(user_id: str):
    return Enrollment.objects.filter(user_id=str(user_id)).select_related("course")


def find(course, user_id: str | None) -> Enrollment | None:
    if not user_id:
        return None
    return Enrollment.objects.filter(course=course, user_id=str(user_id)).first()


def _expiry(course, now: dt.datetime):
    if course.access_days:
        return now + dt.timedelta(days=int(course.access_days))
    return None


def lock_or_create(course, user_id: str, defaults: dict) -> tuple[Enrollment, bool]:
    """The ``(course, user_id)`` row under ``select_for_update``; created if absent."""
    row = Enrollment.objects.select_for_update().filter(course=course, user_id=user_id).first()
    if row is not None:
        return row, False
    try:
        with transaction.atomic():
            row = Enrollment.objects.create(course=course, user_id=user_id, **defaults)
        return row, True
    except IntegrityError:
        return Enrollment.objects.select_for_update().get(course=course, user_id=user_id), False


def move(enrollment: Enrollment, to_status: str, *, actor: str, emit, reason: str = "",
         now: dt.datetime | None = None) -> Enrollment:
    """Move *enrollment* (already locked) along the FSM; emits the facts."""
    now = now or timezone.now()
    try:
        fsm.check(enrollment.status, to_status)
    except fsm.TransitionInvalid:
        raise CoursesError(
            409, ERR_409_ENROLLMENT_TRANSITION_INVALID,
            {"from": enrollment.status, "to": to_status},
        ) from None
    from_status = enrollment.status
    enrollment.status = to_status
    if to_status == EnrollmentStatus.ACTIVE:
        # Drip counts from the first activation; the expiry restarts.
        enrollment.activated_at = enrollment.activated_at or now
        enrollment.expires_at = _expiry(enrollment.course, now)
    if to_status == EnrollmentStatus.COMPLETED:
        enrollment.completed_at = enrollment.completed_at or now
    enrollment.save()
    events.enrollment_status_changed(emit, enrollment, from_status, actor, reason)
    if to_status == EnrollmentStatus.ACTIVE:
        events.enrollment_activated(emit, enrollment)
    return enrollment


def activate(enrollment: Enrollment, *, actor: str, emit, source: str | None = None,
             order_id: str | None = None, now=None) -> Enrollment:
    """Grant access: a pending/cancelled/expired row becomes active; idempotent."""
    if source is not None:
        enrollment.source = source
    if order_id is not None:
        enrollment.order_id = order_id
    if enrollment.status in GRANTING_STATUSES:
        if source is not None or order_id is not None:
            enrollment.save(update_fields=["source", "order_id", "updated_at"])
        return enrollment
    return move(enrollment, EnrollmentStatus.ACTIVE, actor=actor, emit=emit, now=now)


def grant(course, user_id: str, *, source: str, actor: str, emit, order_id: str = "",
          now=None) -> tuple[Enrollment, bool]:
    """Create-or-activate the learner's enrollment. Returns ``(row, changed)``."""
    now = now or timezone.now()
    enrollment, created = lock_or_create(course, user_id, {
        "status": EnrollmentStatus.ACTIVE,
        "source": source,
        "order_id": order_id,
        "activated_at": now,
        "expires_at": _expiry(course, now),
    })
    if created:
        from .progress import refresh_cache

        refresh_cache(enrollment, save=True)
        events.enrollment_activated(emit, enrollment)
        return enrollment, True
    if enrollment.status in GRANTING_STATUSES:
        return enrollment, False
    activate(enrollment, actor=actor, emit=emit, source=source, order_id=order_id, now=now)
    return enrollment, True


def require_account(user) -> str:
    """The learner's id, or the refusal a guest/anonymous request gets."""
    from ..conf import courses_settings

    user_id = user_id_of(user)
    if user_id is None or (is_guest(user) and courses_settings.ENROLLMENT_REQUIRES_ACCOUNT):
        raise CoursesError(403, ERR_403_ENROLLMENT_REQUIRES_ACCOUNT)
    return user_id


def self_enroll(user, course: Course) -> tuple[Enrollment, bool]:
    """``POST courses/{slug}/enroll/``: the strategy decides the source."""
    from ..access import get_strategy

    user_id = require_account(user)
    if course.status != CourseStatus.PUBLISHED:
        raise CoursesError(409, ERR_409_COURSE_NOT_PUBLISHED)
    existing = find(course, user_id)
    if existing is not None and existing.grants_access:
        return existing, False
    source = get_strategy(course.access).self_enroll_source(course, user_id)
    with mutate_and_emit() as emit:
        return grant(course, user_id, source=source, actor=LEARNER, emit=emit)


def can_self_enroll(user, course: Course, enrollment) -> bool:
    """Would ``POST enroll/`` succeed for this caller now? Never raises."""
    from ..access import get_strategy

    if enrollment is not None and enrollment.grants_access:
        return False
    if course.status != CourseStatus.PUBLISHED:
        return False
    try:
        user_id = require_account(user)
        get_strategy(course.access).self_enroll_source(course, user_id)
    except CoursesError:
        return False
    return True


def staff_grant(course: Course, user_id: str, *, expires_at=None) -> tuple[Enrollment, bool]:
    with mutate_and_emit() as emit:
        enrollment, changed = grant(
            course, str(user_id), source=EnrollmentSource.STAFF, actor=STAFF, emit=emit
        )
        if enrollment.source != EnrollmentSource.STAFF or expires_at is not None:
            enrollment.source = EnrollmentSource.STAFF
            if expires_at is not None:
                enrollment.expires_at = expires_at
            enrollment.save(update_fields=["source", "expires_at", "updated_at"])
            changed = True
    return enrollment, changed


def staff_transition(enrollment_id, to_status: str, *, reason: str = "",
                     course_ids=None) -> Enrollment:
    """Staff move; *course_ids* scopes the lookup to an author's courses."""
    with mutate_and_emit() as emit:
        qs = Enrollment.objects.select_for_update().select_related("course")
        if course_ids is not None:
            qs = qs.filter(course_id__in=course_ids)
        enrollment = qs.filter(pk=enrollment_id).first()
        if enrollment is None:
            raise CoursesError(404, ERR_404_ENROLLMENT_NOT_FOUND)
        if to_status == EnrollmentStatus.ACTIVE:
            if enrollment.status in GRANTING_STATUSES:
                raise CoursesError(
                    409, ERR_409_ENROLLMENT_TRANSITION_INVALID,
                    {"from": enrollment.status, "to": to_status},
                )
            return activate(enrollment, actor=STAFF, emit=emit, source=EnrollmentSource.STAFF)
        return move(enrollment, to_status, actor=STAFF, emit=emit, reason=reason)


def expire_due(now: dt.datetime | None = None) -> int:
    """Beat: active/completed enrollments past ``expires_at`` become expired."""
    now = now or timezone.now()
    ids = list(
        Enrollment.objects.filter(status__in=GRANTING_STATUSES, expires_at__lte=now)
        .order_by("id").values_list("id", flat=True)[:BATCH]
    )
    moved = 0
    for pk in ids:
        with mutate_and_emit() as emit:
            enrollment = Enrollment.objects.select_for_update().select_related("course").get(pk=pk)
            if enrollment.status in GRANTING_STATUSES and enrollment.expires_at and enrollment.expires_at <= now:
                move(enrollment, EnrollmentStatus.EXPIRED, actor=SYSTEM, emit=emit, now=now)
                moved += 1
    return moved


def merge_users(from_user_id: str, into_user_id: str) -> dict:
    """``user.merged``: a guest's learning follows it into the account.

    A course only the guest holds is re-parented. A course both hold keeps
    the survivor's enrollment, takes the further status of each lesson,
    renumbers the guest's attempts after the survivor's, and keeps the
    survivor's certificate. Idempotent.
    """
    moved = {"enrollments": 0, "progress": 0, "attempts": 0, "certificates": 0}
    with transaction.atomic():
        for guest in Enrollment.objects.select_for_update().filter(user_id=from_user_id):
            survivor = Enrollment.objects.select_for_update().filter(
                course_id=guest.course_id, user_id=into_user_id
            ).first()
            if survivor is None:
                guest.user_id = into_user_id
                guest.save(update_fields=["user_id", "updated_at"])
                moved["enrollments"] += 1
            else:
                if guest.grants_access and not survivor.grants_access:
                    survivor.status = guest.status
                    survivor.source = guest.source
                    survivor.order_id = guest.order_id
                    survivor.activated_at = guest.activated_at
                    survivor.expires_at = guest.expires_at
                    survivor.completed_at = guest.completed_at
                    survivor.save()
                guest.delete()
        for row in LessonProgress.objects.select_for_update().filter(user_id=from_user_id):
            mine = LessonProgress.objects.select_for_update().filter(
                user_id=into_user_id, lesson_id=row.lesson_id
            ).first()
            if mine is None:
                row.user_id = into_user_id
                row.save(update_fields=["user_id", "updated_at"])
            else:
                if PROGRESS_RANK[row.status] > PROGRESS_RANK[mine.status]:
                    mine.status = row.status
                    mine.completed_at = row.completed_at
                mine.position_seconds = max(mine.position_seconds, row.position_seconds)
                mine.save()
                row.delete()
            moved["progress"] += 1
        for attempt in Attempt.objects.select_for_update().filter(user_id=from_user_id).order_by("id"):
            last = (
                Attempt.objects.filter(quiz_id=attempt.quiz_id, user_id=into_user_id)
                .order_by("-number").values_list("number", flat=True).first()
            ) or 0
            attempt.user_id = into_user_id
            attempt.number = last + 1
            attempt.save(update_fields=["user_id", "number"])
            moved["attempts"] += 1
        for cert in Certificate.objects.select_for_update().filter(user_id=from_user_id):
            if Certificate.objects.filter(course_id=cert.course_id, user_id=into_user_id).exists():
                cert.delete()
            else:
                cert.user_id = into_user_id
                cert.save(update_fields=["user_id"])
                moved["certificates"] += 1
        CoursePurchase.objects.filter(user_id=from_user_id).update(user_id=into_user_id)
        from .progress import refresh_cache

        for enrollment in Enrollment.objects.select_for_update().filter(user_id=into_user_id):
            refresh_cache(enrollment, save=True)
    return moved
