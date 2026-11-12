"""GDPR: export everything learner-keyed; erase it, anonymise certificates."""
import pytest
from stapel_core.gdpr import gdpr_registry, registered_gdpr_owners

from stapel_courses.gdpr import CoursesGDPRProvider, erase_subject
from stapel_courses.models import Attempt, Certificate, Course, CoursePurchase, Enrollment, LessonProgress

from .factories import V1, make_quiz, simple_course, single

pytestmark = pytest.mark.django_db


@pytest.fixture
def history(learner_client, learner, author):
    course, _, lessons = simple_course(author, lessons=1)
    quiz = make_quiz(lessons[0])
    q = single(quiz)
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    learner_client.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/",
                        {"status": "completed"}, format="json")
    attempt = learner_client.post(f"{V1}/quizzes/{quiz.pk}/attempts/").json()
    learner_client.post(f"{V1}/attempts/{attempt['id']}/submit/",
                        {"answers": [{"question_id": q.pk, "choice_ids": ["b"]}]}, format="json")
    CoursePurchase.objects.create(order_id="o-1", course=course, user_id=str(learner.pk), state="paid")
    return course


def test_owner_and_provider_are_registered():
    assert registered_gdpr_owners()["courses"] == ("account",)
    assert any(p.section == "courses" for p in gdpr_registry.providers)


def test_export_covers_every_learner_row(history, learner):
    data = CoursesGDPRProvider().export(str(learner.pk))
    assert set(data) == {"enrollments", "lesson_progress", "quiz_attempts", "certificates"}
    assert data["enrollments"][0]["status"] == "completed"
    assert data["lesson_progress"][0]["status"] == "completed"
    assert data["quiz_attempts"][0]["answers"]
    assert data["certificates"][0]["holder_name"] == "Alice Learner"


def test_erase_deletes_learning_and_anonymises_certificates(history, learner, api_client):
    number = Certificate.objects.get().number
    counts = erase_subject("account", str(learner.pk))
    assert counts == {"lesson_progress": 1, "quiz_attempts": 1, "enrollments": 1, "purchases": 1,
                      "certificates": 1, "authored_courses": 0}
    for model in (Enrollment, LessonProgress, Attempt, CoursePurchase):
        assert not model.objects.filter(user_id=str(learner.pk)).exists()
    certificate = Certificate.objects.get()
    assert certificate.user_id.startswith("pseudo") or certificate.user_id != str(learner.pk)
    assert certificate.holder_name == "" and certificate.revoked_at is not None
    body = api_client.get(f"{V1}/certificates/{number}/").json()
    assert body["valid"] is False
    assert CoursesGDPRProvider().export(str(learner.pk)) == {
        "enrollments": [], "lesson_progress": [], "quiz_attempts": [], "certificates": []}


def test_erase_is_idempotent(history, learner):
    erase_subject("account", str(learner.pk))
    again = erase_subject("account", str(learner.pk))
    assert again["enrollments"] == 0 and again["certificates"] == 0


def test_author_id_is_pseudonymised(history, author):
    erase_subject("account", str(author.pk))
    assert not Course.objects.filter(author_id=str(author.pk)).exists()
    assert Course.objects.count() == 1


def test_other_subject_types_are_not_ours(history, learner):
    assert erase_subject("workspace", str(learner.pk)) is None
    assert Enrollment.objects.exists()
