"""Quizzes: server grading, attempt limits, stored shuffle seed, and the
rule that no right answer leaves before submission (spec §7)."""
import json
from decimal import Decimal

import pytest

from stapel_courses.models import Attempt
from stapel_courses.services.quizzes import is_correct, normalise, orders_for, percent_of

from .factories import (
    V1,
    make_quiz,
    multiple,
    short_text,
    simple_course,
    single,
    true_false,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def quiz_setup(learner_client):
    course, _, lessons = simple_course(lessons=1)
    quiz = make_quiz(lessons[0], pass_mark=75, max_attempts=2, reveal="after_submit")
    questions = [single(quiz), multiple(quiz), true_false(quiz), short_text(quiz)]
    assert learner_client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 201
    return course, quiz, questions


def start(client, quiz):
    return client.post(f"{V1}/quizzes/{quiz.pk}/attempts/")


def submit(client, attempt_id, answers):
    return client.post(f"{V1}/attempts/{attempt_id}/submit/", {"answers": answers}, format="json")


def all_right(questions):
    s, m, tf, st = questions
    return [
        {"question_id": s.pk, "choice_ids": ["b"]},
        {"question_id": m.pk, "choice_ids": ["c", "a"]},
        {"question_id": tf.pk, "value": True},
        {"question_id": st.pk, "text": "  mount   EVEREST! "},
    ]


class TestNoLeakBeforeSubmission:
    SECRET_KEYS = ("correct", "explanation", "accepted")

    def test_open_attempt_body_carries_no_answer(self, learner_client, quiz_setup):
        _, quiz, questions = quiz_setup
        resp = start(learner_client, quiz)
        assert resp.status_code == 201
        body = resp.json()
        raw = json.dumps(body)
        assert "Mount Everest" not in raw and "Because bravo" not in raw
        for question in body["questions"]:
            assert question["correct_answer"] is None
            assert question["result"] is None
            assert question["explanation"] is None
            assert question["answer"] is None
            for choice in question["choices"]:
                assert set(choice) == {"id", "text"}
        assert body["score"] is None and body["percent"] is None and body["passed"] is None
        again = learner_client.get(f"{V1}/attempts/{body['id']}/").json()
        assert again == body

    def test_inversion_the_scan_sees_a_leak(self, learner_client, quiz_setup):
        """A submitted attempt with reveal on does carry the answer: the scan above can see one."""
        _, quiz, questions = quiz_setup
        attempt = start(learner_client, quiz).json()
        raw = json.dumps(submit(learner_client, attempt["id"], all_right(questions)).json())
        assert "Mount Everest" in raw and "Because bravo" in raw

    def test_quiz_summary_never_lists_questions(self, learner_client, quiz_setup):
        _, quiz, _ = quiz_setup
        body = learner_client.get(f"{V1}/quizzes/{quiz.pk}/").json()
        assert "questions" not in body and body["question_count"] == 4
        assert body["attempts_left"] == 2 and body["open_attempt_id"] is None


class TestGrading:
    def test_all_right_passes(self, learner_client, quiz_setup):
        _, quiz, questions = quiz_setup
        attempt = start(learner_client, quiz).json()
        body = submit(learner_client, attempt["id"], all_right(questions)).json()
        assert body["status"] == "submitted" and body["passed"] is True
        assert body["score"] == 4 and body["max_score"] == 4 and body["percent"] == "100.00"
        assert all(q["result"]["correct"] for q in body["questions"])
        assert body["reveals_answers"] is True

    def test_partial_fails_under_the_pass_mark(self, learner_client, quiz_setup):
        _, quiz, questions = quiz_setup
        answers = all_right(questions)
        answers[1]["choice_ids"] = ["a"]
        answers[3]["text"] = "K2"
        attempt = start(learner_client, quiz).json()
        body = submit(learner_client, attempt["id"], answers).json()
        assert body["percent"] == "50.00" and body["passed"] is False

    def test_unanswered_questions_score_zero(self, learner_client, quiz_setup):
        _, quiz, _ = quiz_setup
        attempt = start(learner_client, quiz).json()
        body = submit(learner_client, attempt["id"], []).json()
        assert body["score"] == 0 and body["passed"] is False

    def test_replay_returns_the_stored_result(self, learner_client, quiz_setup):
        _, quiz, questions = quiz_setup
        attempt = start(learner_client, quiz).json()
        first = submit(learner_client, attempt["id"], all_right(questions)).json()
        second = submit(learner_client, attempt["id"], []).json()
        assert second == first

    def test_answer_that_does_not_fit_is_400(self, learner_client, quiz_setup):
        _, quiz, questions = quiz_setup
        attempt = start(learner_client, quiz).json()
        for bad in (
            {"question_id": questions[0].pk, "choice_ids": ["z"]},
            {"question_id": questions[0].pk, "choice_ids": ["a", "b"]},
            {"question_id": questions[2].pk, "text": "yes"},
            {"question_id": 999999, "choice_ids": ["a"]},
        ):
            resp = submit(learner_client, attempt["id"], [bad])
            assert resp.status_code == 400, bad
            assert resp.json()["localizable_error"] == "error.400.quiz_answer_invalid"
        assert Attempt.objects.get(pk=attempt["id"]).status == "in_progress"

    def test_someone_elses_attempt_is_404(self, learner_client, quiz_setup, client_for, other_learner):
        _, quiz, _ = quiz_setup
        attempt = start(learner_client, quiz).json()
        assert client_for(other_learner).get(f"{V1}/attempts/{attempt['id']}/").status_code == 404
        assert submit(client_for(other_learner), attempt["id"], []).status_code == 404


class TestUnitGrading:
    class Q:
        def __init__(self, kind, correct, match="normalised"):
            self.kind, self.correct, self.match = kind, correct, match

    def test_single(self):
        q = self.Q("single", ["b"])
        assert is_correct(q, {"choice_ids": ["b"]}) and not is_correct(q, {"choice_ids": ["a"]})
        assert not is_correct(q, {"choice_ids": []}) and not is_correct(q, None)

    def test_multiple_is_all_or_nothing(self):
        q = self.Q("multiple", ["a", "c"])
        assert is_correct(q, {"choice_ids": ["c", "a"]})
        assert not is_correct(q, {"choice_ids": ["a"]})
        assert not is_correct(q, {"choice_ids": ["a", "b", "c"]})

    def test_true_false(self):
        q = self.Q("true_false", False)
        assert is_correct(q, {"value": False}) and not is_correct(q, {"value": True})
        assert not is_correct(q, {"value": None})

    def test_short_text_exact_and_normalised(self):
        exact = self.Q("short_text", ["Paris"], match="exact")
        assert is_correct(exact, {"text": " Paris "}) and not is_correct(exact, {"text": "paris"})
        loose = self.Q("short_text", ["Saint-Étienne"])
        assert is_correct(loose, {"text": "saint étienne"}) is False
        assert is_correct(loose, {"text": "SAINTÉTIENNE"})
        assert normalise("  Hello,   World! ") == "hello world"
        assert not is_correct(loose, {"text": "   "})

    def test_percent_rounds_half_up(self):
        assert percent_of(2, 3) == Decimal("66.67")
        assert percent_of(1, 8) == Decimal("12.50")
        assert percent_of(0, 0) == Decimal("0.00")


class TestShuffle:
    def test_stored_seed_gives_a_stable_order(self, learner_client, learner):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0], shuffle_questions=True, shuffle_choices=True)
        questions = [single(quiz, position=i) for i in range(8)]
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        body = start(learner_client, quiz).json()
        attempt = Attempt.objects.get(pk=body["id"])
        expected_q, expected_c = orders_for(quiz, questions, attempt.seed)
        assert [q["id"] for q in body["questions"]] == expected_q == attempt.question_order
        assert [c["id"] for c in body["questions"][0]["choices"]] == expected_c[str(body["questions"][0]["id"])]
        for _ in range(3):
            assert learner_client.get(f"{V1}/attempts/{body['id']}/").json()["questions"] == body["questions"]

    def test_unshuffled_quiz_keeps_authored_order(self, learner_client):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0])
        questions = [single(quiz, position=i) for i in range(4)]
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        body = start(learner_client, quiz).json()
        assert [q["id"] for q in body["questions"]] == [q.pk for q in questions]
        assert [c["id"] for c in body["questions"][0]["choices"]] == ["a", "b", "c"]

    def test_different_seeds_can_differ(self):
        class Quiz:
            shuffle_questions = True
            shuffle_choices = False

        class Q:
            def __init__(self, pk):
                self.pk, self.kind, self.choices = pk, "single", []

        qs = [Q(i) for i in range(10)]
        orders = {tuple(orders_for(Quiz, qs, seed)[0]) for seed in range(20)}
        assert len(orders) > 1


class TestAttempts:
    def test_open_attempt_is_returned_not_duplicated(self, learner_client, quiz_setup):
        _, quiz, _ = quiz_setup
        first = start(learner_client, quiz)
        second = start(learner_client, quiz)
        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"]

    def test_limit_is_enforced(self, learner_client, quiz_setup):
        _, quiz, _ = quiz_setup
        for _ in range(2):
            attempt = start(learner_client, quiz).json()
            submit(learner_client, attempt["id"], [])
        resp = start(learner_client, quiz)
        assert resp.status_code == 409
        assert resp.json()["localizable_error"] == "error.409.quiz_attempts_exhausted"
        assert resp.json()["params"]["max"] == 2
        summary = learner_client.get(f"{V1}/quizzes/{quiz.pk}/").json()
        assert summary["attempts_left"] == 0 and summary["attempts_used"] == 2

    def test_unlimited_attempts(self, learner_client):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0], max_attempts=0)
        single(quiz)
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        for _ in range(4):
            attempt = start(learner_client, quiz).json()
            submit(learner_client, attempt["id"], [])
        assert learner_client.get(f"{V1}/quizzes/{quiz.pk}/").json()["attempts_left"] is None

    def test_locked_quiz_cannot_be_started(self, learner_client):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0])
        single(quiz)
        resp = start(learner_client, quiz)
        assert resp.status_code == 403 and resp.json()["params"]["reason"] == "enrollment_required"

    def test_empty_quiz_is_409(self, learner_client):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0])
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert start(learner_client, quiz).status_code == 409

    def test_quiz_of_a_draft_course_is_404(self, learner_client):
        course, _, lessons = simple_course(lessons=1, status="draft")
        quiz = make_quiz(lessons[0])
        assert learner_client.get(f"{V1}/quizzes/{quiz.pk}/").status_code == 404


class TestReveal:
    def _run(self, client, quiz_kwargs, right):
        course, _, lessons = simple_course(lessons=1)
        quiz = make_quiz(lessons[0], **quiz_kwargs)
        q = single(quiz)
        client.post(f"{V1}/courses/{course.slug}/enroll/")
        attempt = start(client, quiz).json()
        return submit(client, attempt["id"], [{"question_id": q.pk, "choice_ids": ["b" if right else "a"]}]).json()

    def test_never(self, learner_client):
        body = self._run(learner_client, {"reveal": "never"}, True)
        assert body["questions"][0]["correct_answer"] is None and body["reveals_answers"] is False
        assert body["questions"][0]["result"]["correct"] is True

    def test_after_pass_hides_on_a_fail(self, learner_client):
        body = self._run(learner_client, {"reveal": "after_pass"}, False)
        assert body["questions"][0]["correct_answer"] is None

    def test_after_pass_shows_on_a_pass(self, learner_client):
        body = self._run(learner_client, {"reveal": "after_pass"}, True)
        assert body["questions"][0]["correct_answer"]["choice_ids"] == ["b"]
        assert body["questions"][0]["explanation"] == "Because bravo."
