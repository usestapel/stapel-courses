"""Drip (days since enrollment / fixed date) and sequential unlock (spec §4)."""
import datetime as dt

import pytest
from django.utils import timezone

from stapel_courses.models import Enrollment

from .factories import V1, make_lesson, make_module, make_quiz, simple_course, single

pytestmark = pytest.mark.django_db


def outline(client, course):
    body = client.get(f"{V1}/courses/{course.slug}/").json()
    return {lesson["id"]: lesson for m in body["modules"] for lesson in m["lessons"]}, body


def enroll(client, course):
    assert client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 201


def complete(client, course, lesson):
    return client.post(f"{V1}/courses/{course.slug}/lessons/{lesson.pk}/progress/",
                       {"status": "completed"}, format="json")


class TestDripDays:
    def test_lesson_opens_n_days_after_enrollment(self, learner_client, learner):
        course, module, lessons = simple_course(drip="days")
        later = make_lesson(module, position=3, unlock_after_days=7)
        enroll(learner_client, course)
        states, _ = outline(learner_client, course)
        assert states[lessons[0].pk]["locked"] is False
        assert states[later.pk]["lock_reason"] == "drip"
        enrollment = Enrollment.objects.get(user_id=str(learner.pk))
        unlocks = dt.datetime.fromisoformat(states[later.pk]["unlocks_at"].replace("Z", "+00:00"))
        assert abs(unlocks - (enrollment.activated_at + dt.timedelta(days=7))) < dt.timedelta(seconds=1)
        resp = learner_client.get(f"{V1}/courses/{course.slug}/lessons/{later.pk}/")
        assert resp.status_code == 403
        assert resp.json()["params"]["reason"] == "drip" and resp.json()["params"]["unlocks_at"]
        Enrollment.objects.filter(pk=enrollment.pk).update(
            activated_at=timezone.now() - dt.timedelta(days=8))
        assert learner_client.get(f"{V1}/courses/{course.slug}/lessons/{later.pk}/").status_code == 200

    def test_drip_fields_are_ignored_when_the_course_does_not_drip(self, learner_client):
        course, module, _ = simple_course(drip="none")
        later = make_lesson(module, position=3, unlock_after_days=7,
                            unlock_at=timezone.now() + dt.timedelta(days=3))
        enroll(learner_client, course)
        states, _ = outline(learner_client, course)
        assert states[later.pk]["locked"] is False


class TestDripDate:
    def test_lesson_opens_on_its_date(self, learner_client):
        course, module, _ = simple_course(drip="date")
        when = timezone.now() + dt.timedelta(days=3)
        future = make_lesson(module, position=3, unlock_at=when)
        past = make_lesson(module, position=4, unlock_at=timezone.now() - dt.timedelta(days=1))
        enroll(learner_client, course)
        states, _ = outline(learner_client, course)
        assert states[future.pk]["lock_reason"] == "drip"
        assert states[past.pk]["locked"] is False

    def test_free_preview_ignores_drip(self, api_client):
        course, module, _ = simple_course(drip="date")
        preview = make_lesson(module, position=3, free_preview=True,
                              unlock_at=timezone.now() + dt.timedelta(days=3))
        assert api_client.get(f"{V1}/courses/{course.slug}/lessons/{preview.pk}/").status_code == 200


class TestSequential:
    def test_next_lesson_opens_after_the_previous_is_completed(self, learner_client):
        course, _, lessons = simple_course(lessons=3, sequential=True)
        enroll(learner_client, course)
        states, _ = outline(learner_client, course)
        assert states[lessons[0].pk]["locked"] is False
        assert states[lessons[1].pk]["lock_reason"] == "sequential"
        assert states[lessons[1].pk]["after_lesson_id"] == lessons[0].pk
        assert states[lessons[2].pk]["after_lesson_id"] == lessons[0].pk
        complete(learner_client, course, lessons[0])
        states, _ = outline(learner_client, course)
        assert states[lessons[1].pk]["locked"] is False
        assert states[lessons[2].pk]["after_lesson_id"] == lessons[1].pk
        assert complete(learner_client, course, lessons[2]).status_code == 403

    def test_a_required_quiz_blocks_the_next_lesson(self, learner_client):
        course, _, lessons = simple_course(sequential=True)
        quiz = make_quiz(lessons[0])
        single(quiz)
        enroll(learner_client, course)
        complete(learner_client, course, lessons[0])
        states, _ = outline(learner_client, course)
        assert states[lessons[1].pk]["after_quiz_id"] == quiz.pk
        attempt = learner_client.post(f"{V1}/quizzes/{quiz.pk}/attempts/").json()
        learner_client.post(f"{V1}/attempts/{attempt['id']}/submit/",
                            {"answers": [{"question_id": attempt["questions"][0]["id"],
                                          "choice_ids": ["b"]}]}, format="json")
        states, _ = outline(learner_client, course)
        assert states[lessons[1].pk]["locked"] is False

    def test_module_quiz_blocks_the_next_module(self, learner_client):
        course, first, lessons = simple_course(lessons=1, sequential=True)
        quiz = make_quiz(first)
        single(quiz)
        second = make_module(course, position=2)
        later = make_lesson(second)
        enroll(learner_client, course)
        _, body = outline(learner_client, course)
        assert body["modules"][0]["quizzes"][0]["lock_reason"] == "sequential"
        complete(learner_client, course, lessons[0])
        states, body = outline(learner_client, course)
        assert body["modules"][0]["quizzes"][0]["locked"] is False
        assert states[later.pk]["after_quiz_id"] == quiz.pk

    def test_optional_lessons_do_not_block(self, learner_client):
        course, module, _ = simple_course(lessons=0, sequential=True)
        optional = make_lesson(module, position=1, required=False)
        after = make_lesson(module, position=2)
        enroll(learner_client, course)
        states, _ = outline(learner_client, course)
        assert states[optional.pk]["locked"] is False and states[after.pk]["locked"] is False

    def test_author_is_never_blocked(self, client_for, author):
        course, _, lessons = simple_course(author, lessons=2, sequential=True)
        states, _ = outline(client_for(author), course)
        assert not any(s["locked"] for s in states.values())
