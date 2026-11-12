"""Learner reads: the catalog, my enrollments, my certificates."""
from __future__ import annotations

from ..models import Certificate, Course, CourseLevel, CourseStatus, Enrollment


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
