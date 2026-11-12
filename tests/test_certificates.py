"""Certificate numbers, the public verification and revocation (spec §8)."""
import re

import pytest
from stapel_core.comm import call

from stapel_courses.models import Certificate, Enrollment
from stapel_courses.services.certificates import new_number

from .factories import V1, simple_course

pytestmark = pytest.mark.django_db


@pytest.fixture
def certificate(learner_client, learner):
    course, _, lessons = simple_course(lessons=1, slug="verified-course", title="Verified course")
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    learner_client.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/",
                        {"status": "completed"}, format="json")
    return Certificate.objects.get(user_id=str(learner.pk))


def test_number_shape():
    assert re.fullmatch(r"CERT-\d{4}-[0-9A-HJKMNP-TV-Z]{8}", new_number())


def test_prefix_setting(settings):
    settings.STAPEL_COURSES = {"CERTIFICATE_NUMBER_PREFIX": "acad"}
    assert new_number().startswith("ACAD-")


def test_default_verification_shows_title_and_date_only(api_client, certificate):
    body = api_client.get(f"{V1}/certificates/{certificate.number}/").json()
    assert body["valid"] is True and body["number"] == certificate.number
    assert body["course_title"] == "Verified course" and body["issued_at"]
    assert body["holder_name"] is None and body["course_slug"] is None
    assert "Alice" not in str(body)


def test_fields_follow_the_setting(api_client, certificate, settings):
    settings.STAPEL_COURSES = {"PUBLIC_VERIFY_FIELDS": ["holder_name"]}
    body = api_client.get(f"{V1}/certificates/{certificate.number.lower()}/").json()
    assert body["holder_name"] == "Alice Learner"
    assert body["course_title"] is None and body["issued_at"] is None


def test_unknown_number_is_404(api_client):
    resp = api_client.get(f"{V1}/certificates/CERT-2026-NOPE0000/")
    assert resp.status_code == 404
    assert resp.json()["localizable_error"] == "error.404.certificate_not_found"


def test_my_certificates(learner_client, certificate, client_for, other_learner):
    items = learner_client.get(f"{V1}/me/certificates/").json()["items"]
    assert [c["number"] for c in items] == [certificate.number]
    assert client_for(other_learner).get(f"{V1}/me/certificates/").json()["items"] == []


def test_revoke_by_author_makes_it_invalid(api_client, certificate, staff_client, client_for, other_learner):
    assert client_for(other_learner).post(
        f"{V1}/author/certificates/{certificate.number}/revoke/", {}, format="json").status_code == 404
    resp = staff_client.post(f"{V1}/author/certificates/{certificate.number}/revoke/",
                             {"reason": "fraud"}, format="json")
    assert resp.status_code == 200 and resp.json()["valid"] is False
    assert api_client.get(f"{V1}/certificates/{certificate.number}/").json()["valid"] is False


def test_issued_once_even_if_completed_again(learner_client, learner, certificate):
    enrollment = Enrollment.objects.get(user_id=str(learner.pk))
    from stapel_core.comm import mutate_and_emit

    from stapel_courses.services.certificates import issue

    with mutate_and_emit() as emit:
        assert issue(enrollment, emit).pk == certificate.pk
    assert Certificate.objects.count() == 1


def test_verify_function(certificate):
    answer = call("courses.certificate.verify", {"number": certificate.number})
    assert answer["valid"] is True and isinstance(answer["issued_at"], str)


def test_verify_function_unknown_number():
    from stapel_core.comm import CommError

    with pytest.raises(CommError):
        call("courses.certificate.verify", {"number": "CERT-0000-XXXXXXXX"})


def test_number_collision_is_redrawn(learner, monkeypatch, certificate):
    from stapel_core.comm import mutate_and_emit

    from stapel_courses.services import certificates as svc

    course2, _, _ = simple_course(lessons=1)
    enrollment = Enrollment.objects.create(course=course2, user_id=str(learner.pk), status="completed",
                                           source="free")
    draws = iter([certificate.number, "CERT-2026-FRESH000"])
    monkeypatch.setattr(svc, "new_number", lambda now=None: next(draws))
    with mutate_and_emit() as emit:
        assert svc.issue(enrollment, emit).number == "CERT-2026-FRESH000"
