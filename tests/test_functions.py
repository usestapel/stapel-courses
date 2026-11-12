"""The comm Functions answer their schemas, in-process."""
import pytest
from stapel_core.comm import CommError, call

from .factories import V1, simple_course

pytestmark = pytest.mark.django_db


def test_enrollment_status_for_a_learner(learner_client, learner):
    course, _, lessons = simple_course()
    before = call("courses.enrollment.status", {"user_id": str(learner.pk), "course_id": str(course.pk)})
    assert before == {"enrolled": False, "status": None, "source": None, "has_access": False,
                      "expires_at": None, "progress_percent": 0}
    learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
    learner_client.post(f"{V1}/courses/{course.slug}/lessons/{lessons[0].pk}/progress/",
                        {"status": "completed"}, format="json")
    after = call("courses.enrollment.status", {"user_id": str(learner.pk), "course_id": str(course.pk)})
    assert after["enrolled"] and after["status"] == "active" and after["has_access"] is True
    assert after["progress_percent"] == 50 and after["source"] == "free"


def test_enrollment_status_free_course_has_access_without_enrollment(learner):
    course, _, _ = simple_course(access="free")
    answer = call("courses.enrollment.status", {"user_id": str(learner.pk), "course_id": str(course.pk)})
    assert answer["enrolled"] is False and answer["has_access"] is True


def test_unknown_course_is_a_lookup_error(learner):
    with pytest.raises(CommError):
        call("courses.enrollment.status", {"user_id": str(learner.pk), "course_id": "999999"})


def test_payload_schema_is_enforced():
    with pytest.raises(CommError):
        call("courses.enrollment.status", {"user_id": "u", "course_id": "not-a-number"})
    with pytest.raises(CommError):
        call("courses.purchasables", {"keys": []})
