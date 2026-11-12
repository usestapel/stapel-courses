"""Progress upserts, the progress cache, completion, certificates (spec §6, §8)."""
import pytest

from stapel_courses.models import Certificate, Enrollment, LessonProgress

from .factories import V1, make_lesson, make_quiz, simple_course, single

pytestmark = pytest.mark.django_db


def progress(client, course, lesson, **body):
    return client.post(f"{V1}/courses/{course.slug}/lessons/{lesson.pk}/progress/", body, format="json")


def enrolled(client, course):
    assert client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 201


class TestUpsert:
    def test_started_then_position_then_completed(self, learner_client, learner):
        course, _, lessons = simple_course()
        enrolled(learner_client, course)
        first = progress(learner_client, course, lessons[0], position_seconds=30).json()
        assert first["progress"]["status"] == "started" and first["progress"]["position_seconds"] == 30
        progress(learner_client, course, lessons[0], position_seconds=12)
        row = LessonProgress.objects.get(user_id=str(learner.pk), lesson=lessons[0])
        assert row.position_seconds == 12
        done = progress(learner_client, course, lessons[0], status="completed").json()
        assert done["progress"]["status"] == "completed" and done["progress"]["completed_at"]
        assert done["enrollment"]["completed_lessons"] == 1
        assert done["enrollment"]["progress_percent"] == 50
        assert done["enrollment"]["last_lesson_id"] == lessons[0].pk

    def test_status_never_moves_back(self, learner_client, learner):
        course, _, lessons = simple_course()
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        again = progress(learner_client, course, lessons[0], status="started").json()
        assert again["progress"]["status"] == "completed"
        assert LessonProgress.objects.filter(user_id=str(learner.pk)).count() == 1

    def test_replay_is_idempotent(self, learner_client, captured_events):
        course, _, lessons = simple_course(lessons=1)
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        progress(learner_client, course, lessons[0], status="completed")
        types = [e.event_type for e in captured_events]
        assert types.count("courses.course.completed") == 1
        assert types.count("courses.certificate.issued") == 1

    def test_locked_lesson_refuses_progress(self, learner_client):
        course, _, lessons = simple_course()
        resp = progress(learner_client, course, lessons[0], status="completed")
        assert resp.status_code == 403
        assert not LessonProgress.objects.exists()

    def test_optional_lessons_do_not_count(self, learner_client):
        course, module, lessons = simple_course(lessons=1)
        make_lesson(module, position=5, required=False)
        enrolled(learner_client, course)
        body = progress(learner_client, course, lessons[0], status="completed").json()
        assert body["enrollment"]["status"] == "completed"
        assert body["enrollment"]["progress_percent"] == 100


class TestCompletion:
    def test_all_lessons_and_quiz_complete_the_course(self, learner_client, learner, captured_events):
        course, _, lessons = simple_course()
        quiz = make_quiz(lessons[1])
        single(quiz)
        enrolled(learner_client, course)
        for lesson in lessons:
            progress(learner_client, course, lesson, status="completed")
        enrollment = Enrollment.objects.get(user_id=str(learner.pk))
        assert enrollment.status == "active" and enrollment.progress_percent == 66
        attempt = learner_client.post(f"{V1}/quizzes/{quiz.pk}/attempts/").json()
        qid = attempt["questions"][0]["id"]
        learner_client.post(f"{V1}/attempts/{attempt['id']}/submit/",
                            {"answers": [{"question_id": qid, "choice_ids": ["b"]}]}, format="json")
        enrollment.refresh_from_db()
        assert enrollment.status == "completed" and enrollment.progress_percent == 100
        assert enrollment.completed_at is not None
        certificate = Certificate.objects.get(user_id=str(learner.pk))
        assert certificate.holder_name == "Alice Learner"
        assert certificate.course_title == course.title
        completed = [e for e in captured_events if e.event_type == "courses.course.completed"]
        assert completed[0].payload["user_id"] == str(learner.pk)
        issued = [e for e in captured_events if e.event_type == "courses.certificate.issued"]
        assert issued[0].payload["number"] == certificate.number
        changed = [e.payload for e in captured_events if e.event_type == "courses.enrollment.status_changed"]
        assert changed[-1]["to"] == "completed" and changed[-1]["actor"] == "system"

    def test_a_failed_quiz_does_not_complete(self, learner_client, learner):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0])
        single(quiz)
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        attempt = learner_client.post(f"{V1}/quizzes/{quiz.pk}/attempts/").json()
        learner_client.post(f"{V1}/attempts/{attempt['id']}/submit/",
                            {"answers": [{"question_id": attempt["questions"][0]["id"], "choice_ids": ["a"]}]},
                            format="json")
        assert Enrollment.objects.get(user_id=str(learner.pk)).status == "active"

    def test_a_course_with_nothing_required_never_completes(self, learner_client, learner):
        course, module, _ = simple_course(lessons=0)
        lesson = make_lesson(module, required=False)
        enrolled(learner_client, course)
        progress(learner_client, course, lesson, status="completed")
        assert Enrollment.objects.get(user_id=str(learner.pk)).status == "active"

    def test_certificates_switched_off(self, learner_client, settings):
        settings.STAPEL_COURSES = {"CERTIFICATES": False}
        course, _, lessons = simple_course(lessons=1)
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        assert not Certificate.objects.exists()

    def test_course_without_certificate(self, learner_client):
        course, _, lessons = simple_course(lessons=1, certificate_enabled=False)
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        assert not Certificate.objects.exists()

    def test_completion_rule_is_replaceable(self, learner_client, learner, settings):
        settings.STAPEL_COURSES = {"COMPLETION_RULE": "stapel_courses.tests.test_progress.half_is_enough"}
        course, _, lessons = simple_course()
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        assert Enrollment.objects.get(user_id=str(learner.pk)).status == "completed"


def half_is_enough(enrollment):
    return enrollment.progress_percent >= 50


class TestReview:
    def test_learner_submits_staff_passes(self, learner_client, learner, client_for, author):
        course, module, _ = simple_course(author, lessons=0)
        lesson = make_lesson(module, review_required=True)
        enrolled(learner_client, course)
        refused = progress(learner_client, course, lesson, status="completed")
        assert refused.status_code == 403
        assert refused.json()["localizable_error"] == "error.403.lesson_review_required"
        assert progress(learner_client, course, lesson, status="submitted").json()["progress"]["status"] == "submitted"
        resp = client_for(author).post(f"{V1}/author/lessons/{lesson.pk}/review/",
                                       {"user_id": str(learner.pk), "passed": True}, format="json")
        assert resp.status_code == 200 and resp.json()["progress"]["status"] == "completed"
        assert resp.json()["enrollment"]["status"] == "completed"

    def test_returned_submission_goes_back_to_started(self, learner_client, learner, client_for, author):
        course, module, _ = simple_course(author, lessons=0)
        lesson = make_lesson(module, review_required=True)
        enrolled(learner_client, course)
        progress(learner_client, course, lesson, status="submitted")
        resp = client_for(author).post(f"{V1}/author/lessons/{lesson.pk}/review/",
                                       {"user_id": str(learner.pk), "passed": False}, format="json")
        assert resp.json()["progress"]["status"] == "started"

    def test_a_stranger_cannot_review(self, learner_client, learner, client_for, other_learner):
        course, module, _ = simple_course(lessons=0)
        lesson = make_lesson(module, review_required=True)
        resp = client_for(other_learner).post(f"{V1}/author/lessons/{lesson.pk}/review/",
                                              {"user_id": str(learner.pk), "passed": True}, format="json")
        assert resp.status_code == 404


class TestReads:
    def test_course_progress_and_my_enrollments(self, learner_client):
        course, _, lessons = simple_course()
        quiz = make_quiz(lessons[0])
        single(quiz)
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[0], status="completed")
        body = learner_client.get(f"{V1}/courses/{course.slug}/progress/").json()
        assert [row["lesson_id"] for row in body["lessons"]] == [lessons[0].pk]
        assert body["quizzes"] == [{"quiz_id": quiz.pk, "passed": False, "best_percent": None,
                                    "attempts_used": 0}]
        mine = learner_client.get(f"{V1}/me/enrollments/").json()
        assert [e["course_slug"] for e in mine["items"]] == [course.slug]
        filtered = learner_client.get(f"{V1}/me/enrollments/", {"status": "completed"}).json()
        assert filtered["items"] == []

    def test_lesson_read_carries_my_progress(self, learner_client):
        course, _, lessons = simple_course()
        enrolled(learner_client, course)
        progress(learner_client, course, lessons[1], position_seconds=44)
        body = learner_client.get(f"{V1}/courses/{course.slug}/lessons/{lessons[1].pk}/").json()
        assert body["progress"]["position_seconds"] == 44
        assert body["prev_lesson_id"] == lessons[0].pk and body["next_lesson_id"] is None
