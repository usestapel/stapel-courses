"""user.merged: a guest's learning follows it into the account."""
import pytest

from stapel_courses import actions
from stapel_courses.models import Attempt, Certificate, Enrollment, LessonProgress

from .factories import V1, Event, make_quiz, simple_course, single

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def guests_learn(settings):
    settings.STAPEL_COURSES = {"ENROLLMENT_REQUIRES_ACCOUNT": False}


def merged(guest, user):
    actions.handle_user_merged(Event({"from_user_id": str(guest.pk), "into_user_id": str(user.pk)}))


def test_a_course_only_the_guest_holds_is_reparented(client_for, guest, learner):
    course, _, lessons = simple_course(lessons=2)
    quiz = make_quiz(lessons[0])
    single(quiz)
    c = client_for(guest)
    c.post(f"{V1}/courses/{course.slug}/enroll/")
    c.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/", {"status": "completed"},
           format="json")
    c.post(f"{V1}/quizzes/{quiz.pk}/attempts/")
    merged(guest, learner)
    merged(guest, learner)
    enrollment = Enrollment.objects.get()
    assert enrollment.user_id == str(learner.pk) and enrollment.completed_lessons == 1
    assert LessonProgress.objects.get().user_id == str(learner.pk)
    assert Attempt.objects.get().user_id == str(learner.pk)


def test_a_course_both_hold_keeps_the_survivor_with_the_union(client_for, guest, learner):
    course, _, lessons = simple_course(lessons=3)
    quiz = make_quiz(lessons[2])
    single(quiz)
    g, u = client_for(guest), client_for(learner)
    for c in (g, u):
        c.post(f"{V1}/courses/{course.slug}/enroll/")
    g.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/", {"status": "completed"},
           format="json")
    u.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/", {"position_seconds": 5},
           format="json")
    u.post(f"{V1}/courses/{course.slug}/lessons/{lessons[1].pk}/progress/", {"status": "completed"},
           format="json")
    g_attempt = g.post(f"{V1}/quizzes/{quiz.pk}/attempts/").json()
    g.post(f"{V1}/attempts/{g_attempt['id']}/submit/", {"answers": []}, format="json")
    u.post(f"{V1}/quizzes/{quiz.pk}/attempts/")
    merged(guest, learner)
    enrollment = Enrollment.objects.get()
    assert enrollment.user_id == str(learner.pk) and enrollment.completed_lessons == 2
    assert LessonProgress.objects.filter(user_id=str(learner.pk), status="completed").count() == 2
    assert sorted(Attempt.objects.filter(user_id=str(learner.pk)).values_list("number", flat=True)) == [1, 2]


def test_certificates_follow_without_duplicates(guest, learner):
    course, _, _ = simple_course(lessons=1)
    Certificate.objects.create(number="CERT-2026-AAAAAAAA", course=course, user_id=str(guest.pk),
                               course_title="t", issued_at="2026-11-01T00:00:00Z")
    merged(guest, learner)
    assert Certificate.objects.get().user_id == str(learner.pk)


def test_survivors_certificate_wins(guest, learner):
    course, _, _ = simple_course(lessons=1)
    for user, n in ((guest, "A"), (learner, "B")):
        Certificate.objects.create(number=f"CERT-2026-{n * 8}", course=course, user_id=str(user.pk),
                                   course_title="t", issued_at="2026-11-01T00:00:00Z")
    merged(guest, learner)
    assert list(Certificate.objects.values_list("number", flat=True)) == ["CERT-2026-BBBBBBBB"]


def test_malformed_and_self_merges_are_noops(learner):
    actions.handle_user_merged(Event({"from_user_id": "", "into_user_id": str(learner.pk)}))
    actions.handle_user_merged(Event({"from_user_id": str(learner.pk), "into_user_id": str(learner.pk)}))
