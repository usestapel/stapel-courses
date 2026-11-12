"""The enrollment FSM as a table: every pair is either an edge or a 409."""
import itertools

import pytest
from stapel_core.comm import mutate_and_emit

from stapel_courses import fsm
from stapel_courses.models import CourseStatus, EnrollmentStatus
from stapel_courses.services import CoursesError
from stapel_courses.services.enrollments import SYSTEM, move

from .factories import simple_course

STATUSES = list(EnrollmentStatus.values)

EXPECTED = {
    ("pending", "active"), ("pending", "cancelled"),
    ("active", "completed"), ("active", "expired"), ("active", "cancelled"),
    ("completed", "expired"), ("completed", "cancelled"),
    ("expired", "active"), ("expired", "pending"),
    ("cancelled", "active"), ("cancelled", "pending"),
}


def test_the_table_is_exactly_the_spec():
    edges = {(a, b) for a, targets in fsm.TRANSITIONS.items() for b in targets}
    assert edges == EXPECTED


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", list(itertools.product(STATUSES, STATUSES)))
def test_every_pair(src, dst, learner):
    from stapel_courses.models import Enrollment

    course, _, _ = simple_course(lessons=0)
    enrollment = Enrollment.objects.create(course=course, user_id=str(learner.pk), status=src, source="free")
    if (src, dst) in EXPECTED:
        with mutate_and_emit() as emit:
            move(enrollment, dst, actor=SYSTEM, emit=emit)
        enrollment.refresh_from_db()
        assert enrollment.status == dst
    else:
        with pytest.raises(CoursesError) as exc, mutate_and_emit() as emit:
            move(enrollment, dst, actor=SYSTEM, emit=emit)
        assert exc.value.status == 409
        assert exc.value.key == "error.409.enrollment_transition_invalid"


def test_course_status_edges():
    assert fsm.course_allowed(CourseStatus.DRAFT, CourseStatus.PUBLISHED)
    assert fsm.course_allowed(CourseStatus.ARCHIVED, CourseStatus.PUBLISHED)
    assert not fsm.course_allowed(CourseStatus.PUBLISHED, CourseStatus.DRAFT)
    assert not fsm.course_allowed(CourseStatus.DRAFT, CourseStatus.ARCHIVED)
