"""Expiry (beat + command), the beat schedule, the demo seed."""
import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from stapel_courses.beat import EXPIRE_TASK_NAME, expire_enrollments, get_courses_beat_schedule
from stapel_courses.models import Course, Enrollment, Lesson, Question

from .factories import V1, simple_course

pytestmark = pytest.mark.django_db


def test_beat_schedule_names_the_task():
    (entry,) = get_courses_beat_schedule().values()
    assert entry["task"] == EXPIRE_TASK_NAME and entry["schedule"] == 900.0


def test_expired_enrollments_lose_access(learner_client, learner, captured_events):
    course, _, lessons = simple_course(access_days=10)
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    enrollment = Enrollment.objects.get()
    assert (enrollment.expires_at - enrollment.activated_at).days == 10
    assert expire_enrollments() == 0
    Enrollment.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert expire_enrollments() == 1
    assert expire_enrollments() == 0
    assert Enrollment.objects.get().status == "expired"
    resp = learner_client.get(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/")
    assert resp.status_code == 403 and resp.json()["params"]["reason"] == "enrollment_inactive"
    changed = [e.payload for e in captured_events if e.event_type == "courses.enrollment.status_changed"]
    assert changed[-1]["to"] == "expired" and changed[-1]["actor"] == "system"


def test_re_enrolling_after_expiry_restarts_the_clock(learner_client):
    course, _, _ = simple_course(access_days=10)
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    Enrollment.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    expire_enrollments()
    resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    assert resp.status_code == 201 and resp.json()["status"] == "active"
    assert Enrollment.objects.get().expires_at > timezone.now() + dt.timedelta(days=9)


def test_housekeeping_command():
    out = StringIO()
    call_command("courses_housekeeping", stdout=out)
    assert out.getvalue().strip() == "expired 0"


def test_seed_demo_is_idempotent_and_learnable(learner_client):
    out = StringIO()
    call_command("courses_seed_demo", stdout=out)
    call_command("courses_seed_demo", stdout=out)
    assert Course.objects.count() == 1 and "already present" in out.getvalue()
    course = Course.objects.get()
    assert Lesson.objects.filter(course=course).count() == 4
    assert set(Question.objects.values_list("kind", flat=True)) == {
        "single", "multiple", "true_false", "short_text"}
    outline = learner_client.get(f"{V1}/courses/{course.slug}/").json()
    assert outline["course"]["status"] == "published" and len(outline["modules"]) == 2
    from stapel_courses.blocks import clean_blocks

    for lesson in Lesson.objects.all():
        assert clean_blocks(lesson.blocks) == lesson.blocks
