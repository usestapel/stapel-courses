"""Lesson progress, the enrollment progress cache and the completion rule (spec §6).

A progress write is an idempotent upsert on ``(user_id, lesson)``: the status
only moves forward (started → submitted → completed) and the playback
position is the last one written. The enrollment row is locked
(``select_for_update``) while its cache is recomputed, so two lessons
completed at once still count to two.
"""
from __future__ import annotations

import math

from django.db import IntegrityError, transaction
from django.utils import timezone
from stapel_core.comm import mutate_and_emit

from ..errors import ERR_403_REVIEW_REQUIRED, ERR_404_LESSON_NOT_FOUND
from ..models import (
    PROGRESS_RANK,
    AttemptStatus,
    CourseStatus,
    Enrollment,
    EnrollmentSource,
    EnrollmentStatus,
    Lesson,
    LessonProgress,
    ProgressStatus,
    Quiz,
)
from . import CoursesError, events


def refresh_cache(enrollment: Enrollment, *, save: bool = False) -> Enrollment:
    """Recompute the progress counters of *enrollment* from the rows."""
    course_id = enrollment.course_id
    required_lessons = Lesson.objects.filter(course_id=course_id, required=True)
    required_quizzes = Quiz.objects.filter(course_id=course_id, required=True)
    enrollment.required_lessons = required_lessons.count()
    enrollment.completed_lessons = LessonProgress.objects.filter(
        user_id=enrollment.user_id, lesson__in=required_lessons, status=ProgressStatus.COMPLETED,
    ).count()
    enrollment.required_quizzes = required_quizzes.count()
    enrollment.passed_quizzes = required_quizzes.filter(
        attempts__user_id=enrollment.user_id, attempts__passed=True,
        attempts__status=AttemptStatus.SUBMITTED,
    ).distinct().count()
    total = enrollment.required_lessons + enrollment.required_quizzes
    done = enrollment.completed_lessons + enrollment.passed_quizzes
    enrollment.progress_percent = math.floor(100 * done / total) if total else 0
    if save:
        enrollment.save(update_fields=[
            "required_lessons", "completed_lessons", "required_quizzes", "passed_quizzes",
            "progress_percent", "last_lesson_id", "updated_at",
        ])
    return enrollment


def default_completion_rule(enrollment: Enrollment) -> bool:
    """Every required lesson completed and every required quiz passed (≥ 1 item)."""
    total = enrollment.required_lessons + enrollment.required_quizzes
    return bool(total) and (
        enrollment.completed_lessons >= enrollment.required_lessons
        and enrollment.passed_quizzes >= enrollment.required_quizzes
    )


def maybe_complete(enrollment: Enrollment, emit) -> bool:
    """Apply ``COMPLETION_RULE`` to a locked, refreshed enrollment."""
    from ..conf import courses_settings
    from .certificates import issue
    from .enrollments import SYSTEM, move

    if enrollment.status != EnrollmentStatus.ACTIVE:
        return False
    if not courses_settings.COMPLETION_RULE(enrollment):
        return False
    move(enrollment, EnrollmentStatus.COMPLETED, actor=SYSTEM, emit=emit)
    events.course_completed(emit, enrollment)
    issue(enrollment, emit)
    return True


def _lock_progress(user_id: str, lesson: Lesson) -> LessonProgress:
    row = LessonProgress.objects.select_for_update().filter(user_id=user_id, lesson=lesson).first()
    if row is not None:
        return row
    try:
        with transaction.atomic():
            return LessonProgress.objects.create(
                user_id=user_id, lesson=lesson, course_id=lesson.course_id
            )
    except IntegrityError:
        return LessonProgress.objects.select_for_update().get(user_id=user_id, lesson=lesson)


def _advance(row: LessonProgress, status: str | None, position_seconds: int | None) -> None:
    fields = ["updated_at"]
    if status and PROGRESS_RANK[status] > PROGRESS_RANK[row.status]:
        row.status = status
        fields.append("status")
        if status == ProgressStatus.COMPLETED:
            row.completed_at = timezone.now()
            fields.append("completed_at")
    if position_seconds is not None:
        row.position_seconds = int(position_seconds)
        fields.append("position_seconds")
    row.save(update_fields=fields)


def _locked_enrollment(view, emit):
    """The learner's enrollment row, locked; a free course enrolls on first write."""
    from ..access import get_strategy
    from .enrollments import LEARNER, grant

    if view.enrollment is not None:
        return Enrollment.objects.select_for_update().select_related("course").get(pk=view.enrollment.pk)
    if view.course.status != CourseStatus.PUBLISHED or view.privileged:
        return None
    if get_strategy(view.course.access).content_access(view.course, view.user_id, None).allowed:
        enrollment, _ = grant(
            view.course, view.user_id, source=EnrollmentSource.FREE, actor=LEARNER, emit=emit
        )
        return enrollment
    return None


def record(user, course, lesson_id, *, status: str | None = None,
           position_seconds: int | None = None):
    """``POST courses/{slug}/lessons/{id}/progress/``. Returns ``(row, enrollment)``."""
    from .enrollments import require_account
    from .gate import course_view, require_lesson

    user_id = require_account(user)
    view = course_view(course, user)
    lesson = require_lesson(view, lesson_id)
    if status == ProgressStatus.COMPLETED and lesson.review_required and not view.privileged:
        raise CoursesError(403, ERR_403_REVIEW_REQUIRED)
    with mutate_and_emit() as emit:
        enrollment = _locked_enrollment(view, emit)
        row = _lock_progress(user_id, lesson)
        _advance(row, status or ProgressStatus.STARTED, position_seconds)
        if enrollment is not None:
            enrollment.last_lesson_id = lesson.pk
            refresh_cache(enrollment, save=True)
            maybe_complete(enrollment, emit)
    return row, enrollment


def review(course, lesson_id, user_id: str, *, passed: bool) -> LessonProgress:
    """Staff/author verdict on a ``review_required`` lesson."""
    lesson = Lesson.objects.filter(course=course, pk=lesson_id).first()
    if lesson is None:
        raise CoursesError(404, ERR_404_LESSON_NOT_FOUND)
    with mutate_and_emit() as emit:
        row = _lock_progress(str(user_id), lesson)
        if passed:
            _advance(row, ProgressStatus.COMPLETED, None)
        elif row.status != ProgressStatus.COMPLETED:
            row.status = ProgressStatus.STARTED
            row.save(update_fields=["status", "updated_at"])
        enrollment = (
            Enrollment.objects.select_for_update().select_related("course")
            .filter(course=course, user_id=str(user_id)).first()
        )
        if enrollment is not None:
            refresh_cache(enrollment, save=True)
            maybe_complete(enrollment, emit)
    return row


def after_quiz(enrollment_id, emit) -> None:
    """Re-count and re-judge an enrollment after a quiz submission."""
    enrollment = Enrollment.objects.select_for_update().select_related("course").filter(
        pk=enrollment_id
    ).first()
    if enrollment is None:
        return
    refresh_cache(enrollment, save=True)
    maybe_complete(enrollment, emit)
