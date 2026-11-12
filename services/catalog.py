"""List reads: the catalog, my enrollments and certificates, and the
author/staff lists (course enrollments, the review queue, course certificates)."""
from __future__ import annotations

from ..models import (
    Certificate,
    Course,
    CourseLevel,
    CourseStatus,
    Enrollment,
    LessonProgress,
    ProgressStatus,
)


def catalog(level: str | None = None, scope: str | None = None):
    qs = Course.objects.filter(status=CourseStatus.PUBLISHED)
    if level and level in CourseLevel.values:
        qs = qs.filter(level=level)
    if scope:
        qs = qs.filter(scope=scope)
    return qs


def my_enrollments(user_id: str, statuses=None):
    qs = Enrollment.objects.filter(user_id=str(user_id)).select_related("course")
    wanted = [s for s in (statuses or []) if s]
    if wanted:
        qs = qs.filter(status__in=wanted)
    return qs


def my_certificates(user_id: str):
    return Certificate.objects.filter(user_id=str(user_id)).select_related("course")


def course_enrollments(course, statuses=None):
    qs = Enrollment.objects.filter(course=course).select_related("course")
    wanted = [s for s in (statuses or []) if s]
    if wanted:
        qs = qs.filter(status__in=wanted)
    return qs


def pending_reviews(courses):
    """Lesson progress submitted for review in *courses* (the editable ones)."""
    return (
        LessonProgress.objects.filter(status=ProgressStatus.SUBMITTED, course__in=courses)
        .select_related("lesson", "course")
    )


def course_certificates(course, revoked: bool | None = None):
    qs = Certificate.objects.filter(course=course).select_related("course")
    if revoked is not None:
        qs = qs.filter(revoked_at__isnull=not revoked)
    return qs
