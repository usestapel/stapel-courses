"""Counters under a lock (wave gate §3): attempt limits, enrollment rows,
the purchase ledger.

SQLite has no row locks (Django drops FOR UPDATE there), so two OS threads
cannot prove the lock on this harness. What is proved here:

1. the lock is taken — ``select_for_update()`` on the enrollment row —
   BEFORE the attempts are counted (ordering spy);
2. two interleaved starts at the limit: the rival's attempt commits after
   our gate check and before our lock; we count after the lock, so the end
   is one attempt and one 409;
3. inversion: with the count taken before the lock, the same interleaving
   exceeds the limit — the test can see the defect;
4. rows keyed by a uniqueness (enrollment, purchase) re-read the winner's
   row when a rival created it first, never a duplicate or a 500.
On Postgres the lock makes step 2 the only possible interleaving.
"""
import pytest
from django.db.models import QuerySet
from stapel_core.comm import mutate_and_emit

from stapel_courses.models import Attempt, CoursePurchase, Enrollment
from stapel_courses.services import CoursesError
from stapel_courses.services import quizzes as quiz_service

from .factories import V1, make_quiz, simple_course, single


@pytest.fixture
def limited(learner_client):
    course, _, lessons = simple_course(lessons=1)
    quiz = make_quiz(lessons[0], max_attempts=1)
    single(quiz)
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    return quiz


@pytest.mark.django_db(transaction=True)
class TestAttemptLimit:
    def test_lock_is_taken_before_the_count(self, limited, learner, monkeypatch):
        order = []
        real_sfu = QuerySet.select_for_update

        def sfu_spy(self, *a, **kw):
            order.append(f"lock:{self.model.__name__}")
            return real_sfu(self, *a, **kw)

        real_count = quiz_service.attempts_used

        def count_spy(*a, **kw):
            order.append("count")
            return real_count(*a, **kw)

        monkeypatch.setattr(QuerySet, "select_for_update", sfu_spy)
        monkeypatch.setattr(quiz_service, "attempts_used", count_spy)
        quiz_service.start(learner, limited.pk)
        assert order.index("lock:Enrollment") < order.index("count")

    def _rival_commits_first(self, monkeypatch, quiz):
        """The rival's attempt commits after our gate check, before our transaction.

        It carries number 5 (numbers are not dense after a merge), so only the
        count — not the number uniqueness — can stop us.
        """
        real_gate = quiz_service.quiz_for_learner
        state = {"raced": False}

        def gate_then_rival(user, quiz_id):
            answer = real_gate(user, quiz_id)
            if not state["raced"]:
                state["raced"] = True
                Attempt.objects.create(quiz=quiz, user_id=str(user.pk), number=5, seed=1,
                                       question_order=[], choice_order={}, status="submitted")
            return answer

        monkeypatch.setattr(quiz_service, "quiz_for_learner", gate_then_rival)

    def test_two_starts_at_the_limit_one_attempt_one_409(self, limited, learner, monkeypatch):
        self._rival_commits_first(monkeypatch, limited)
        with pytest.raises(CoursesError) as exc:
            quiz_service.start(learner, limited.pk)
        assert exc.value.key == "error.409.quiz_attempts_exhausted"
        assert Attempt.objects.filter(quiz=limited).count() == 1

    def test_inversion_counting_before_the_lock_exceeds_the_limit(self, limited, learner, monkeypatch):
        stale = {"n": quiz_service.attempts_used(limited, str(learner.pk))}
        monkeypatch.setattr(quiz_service, "attempts_used", lambda quiz, user_id: stale["n"])
        self._rival_commits_first(monkeypatch, limited)
        quiz_service.start(learner, limited.pk)
        assert Attempt.objects.filter(quiz=limited).count() == 2  # limit 1: the defect is visible

    def test_number_uniqueness_is_a_second_net(self, limited, learner, monkeypatch):
        """A stale count cannot write the same attempt number twice."""
        Attempt.objects.create(quiz=limited, user_id=str(learner.pk), number=1, seed=1,
                               question_order=[], choice_order={}, status="submitted")
        monkeypatch.setattr(quiz_service, "attempts_used", lambda quiz, user_id: 0)
        with pytest.raises(CoursesError):
            quiz_service.start(learner, limited.pk)
        assert Attempt.objects.filter(quiz=limited).count() == 1


@pytest.mark.django_db(transaction=True)
class TestUniqueRows:
    def test_enrollment_created_by_a_rival_is_reused(self, learner, monkeypatch):
        from stapel_courses.services import enrollments as svc

        course, _, _ = simple_course(lessons=1)
        real_sfu = QuerySet.select_for_update
        state = {"raced": False}

        def stale_first_read(self, *a, **kw):
            if self.model is Enrollment and not state["raced"]:
                state["raced"] = True
                Enrollment.objects.create(course=course, user_id=str(learner.pk), status="active",
                                          source="free")
                return Enrollment.objects.none()
            return real_sfu(self, *a, **kw)

        monkeypatch.setattr(QuerySet, "select_for_update", stale_first_read)
        with mutate_and_emit() as emit:
            enrollment, _ = svc.grant(course, str(learner.pk), source="free", actor="learner", emit=emit)
        assert state["raced"] and Enrollment.objects.count() == 1
        assert enrollment.status == "active"

    def test_purchase_row_created_by_a_rival_is_reused(self, learner, monkeypatch):
        from stapel_courses.services import purchases as svc

        course, _, _ = simple_course(lessons=1, access="purchased", price="5.00", currency="USD")
        real_sfu = QuerySet.select_for_update
        state = {"raced": False}

        def stale_first_read(self, *a, **kw):
            if self.model is CoursePurchase and not state["raced"]:
                state["raced"] = True
                CoursePurchase.objects.create(order_id="o-1", course=course, user_id=str(learner.pk),
                                              state="placed")
                return CoursePurchase.objects.none()
            return real_sfu(self, *a, **kw)

        monkeypatch.setattr(QuerySet, "select_for_update", stale_first_read)
        touched = svc.order_placed({"order_id": "o-1", "user_id": str(learner.pk), "lines": [
            {"purchasable_type": "course", "purchasable_key": str(course.pk)}]})
        assert touched == 0 and CoursePurchase.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_progress_cache_is_recounted_under_the_enrollment_lock(learner_client, learner, monkeypatch):
    from stapel_courses.services import progress as progress_service

    course, _, lessons = simple_course(lessons=2)
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    order = []
    real_sfu = QuerySet.select_for_update
    real_refresh = progress_service.refresh_cache

    def sfu_spy(self, *a, **kw):
        order.append(f"lock:{self.model.__name__}")
        return real_sfu(self, *a, **kw)

    def refresh_spy(*a, **kw):
        order.append("recount")
        return real_refresh(*a, **kw)

    monkeypatch.setattr(QuerySet, "select_for_update", sfu_spy)
    monkeypatch.setattr(progress_service, "refresh_cache", refresh_spy)
    learner_client.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/",
                        {"status": "completed"}, format="json")
    assert order.index("lock:Enrollment") < order.index("recount")
    assert Enrollment.objects.get().completed_lessons == 1
