"""The four built-in access strategies, the registry seam, and the 503 rule."""
import pytest

from stapel_courses.access import EnrolledAccess, get_strategy, strategy_names
from stapel_courses.models import Enrollment

from .factories import V1, make_lesson, simple_course

pytestmark = pytest.mark.django_db


def lesson_url(course, lesson):
    return f"{V1}/courses/{course.slug}/lessons/{lesson.pk}/"


class TestFree:
    def test_anyone_reads_without_enrolling(self, api_client):
        course, _, lessons = simple_course(access="free")
        resp = api_client.get(lesson_url(course, lessons[0]))
        assert resp.status_code == 200
        assert resp.json()["blocks"][0]["text"] == "secret body 1"
        assert resp.json()["next_lesson_id"] == lessons[1].pk and resp.json()["prev_lesson_id"] is None

    def test_first_progress_write_enrolls(self, learner_client, learner):
        course, _, lessons = simple_course(access="free")
        resp = learner_client.post(f"{lesson_url(course, lessons[0])}progress/", {}, format="json")
        assert resp.status_code == 200
        assert resp.json()["enrollment"]["source"] == "free"
        assert Enrollment.objects.get(user_id=str(learner.pk)).status == "active"


class TestEnrolled:
    def test_content_needs_the_enrollment(self, learner_client):
        course, _, lessons = simple_course()
        resp = learner_client.get(lesson_url(course, lessons[0]))
        assert resp.status_code == 403
        body = resp.json()
        assert body["localizable_error"] == "error.403.lesson_locked"
        assert "secret body" not in str(body)
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert learner_client.get(lesson_url(course, lessons[0])).status_code == 200

    def test_free_preview_is_open_to_anonymous(self, api_client):
        course, module, _ = simple_course()
        preview = make_lesson(module, position=9, free_preview=True)
        assert api_client.get(lesson_url(course, preview)).status_code == 200

    def test_cancelled_enrollment_locks_with_its_reason(self, learner_client, learner):
        course, _, lessons = simple_course()
        Enrollment.objects.create(course=course, user_id=str(learner.pk), status="cancelled", source="free")
        resp = learner_client.get(lesson_url(course, lessons[0]))
        assert resp.status_code == 403
        assert resp.json()["params"]["reason"] == "enrollment_inactive"

    def test_lesson_of_another_course_is_404(self, learner_client):
        course, _, _ = simple_course(access="free")
        other, _, other_lessons = simple_course(access="free")
        resp = learner_client.get(lesson_url(course, other_lessons[0]))
        assert resp.status_code == 404


class TestPurchased:
    def test_self_enroll_is_refused(self, learner_client):
        course, _, lessons = simple_course(access="purchased", price="19.00", currency="USD")
        resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 403
        assert resp.json()["localizable_error"] == "error.403.course_purchase_required"
        outline = learner_client.get(f"{V1}/courses/{course.slug}/").json()
        assert outline["access"]["reason"] == "purchase_required"
        assert outline["access"]["can_enroll"] is False

    def test_staff_grant_opens_it(self, staff_client, learner, client_for, captured_events):
        course, _, lessons = simple_course(access="purchased", price="19.00", currency="USD")
        resp = staff_client.post(f"{V1}/author/courses/{course.pk}/enrollments/",
                                 {"user_id": str(learner.pk)}, format="json")
        assert resp.status_code == 201 and resp.json()["source"] == "staff"
        assert client_for(learner).get(lesson_url(course, lessons[0])).status_code == 200


class TestEntitlement:
    def test_plan_allows_enrolling(self, learner_client, learner, billing):
        course, _, lessons = simple_course(access="entitlement", slug="pro-course")
        resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 201 and resp.json()["source"] == "entitlement"
        assert billing.calls[0] == {"user_id": str(learner.pk), "key": "course:pro-course"}
        assert learner_client.get(lesson_url(course, lessons[0])).status_code == 200

    def test_course_key_overrides_the_template(self, learner_client, billing):
        course, _, _ = simple_course(access="entitlement", entitlement_key="plan.pro")
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert billing.calls[0]["key"] == "plan.pro"

    def test_plan_refuses(self, learner_client, billing):
        billing.state["allowed"] = False
        course, _, _ = simple_course(access="entitlement")
        resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 403
        assert resp.json()["localizable_error"] == "error.403.course_entitlement_required"

    def test_lost_plan_locks_the_content_again(self, learner_client, billing, settings):
        settings.STAPEL_COURSES = {"ENTITLEMENT_CACHE_SECONDS": 0}
        course, _, lessons = simple_course(access="entitlement")
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        billing.state["allowed"] = False
        resp = learner_client.get(lesson_url(course, lessons[0]))
        assert resp.status_code == 403 and resp.json()["params"]["reason"] == "entitlement_required"

    def test_answers_are_cached(self, learner_client, billing):
        course, _, lessons = simple_course(access="entitlement")
        learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        learner_client.get(lesson_url(course, lessons[0]))
        learner_client.get(lesson_url(course, lessons[1]))
        assert len(billing.calls) == 1

    def test_unreachable_billing_is_503_never_a_guess(self, learner_client):
        course, _, _ = simple_course(access="entitlement")
        resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 503
        assert resp.json()["localizable_error"] == "error.503.entitlement_unavailable"
        assert not Enrollment.objects.exists()

    def test_failing_billing_is_503(self, learner_client, billing):
        billing.fail = True
        course, _, _ = simple_course(access="entitlement")
        assert learner_client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 503

    def test_malformed_answer_is_503(self, learner_client, billing):
        billing.answer = {"maybe": True}
        course, _, _ = simple_course(access="entitlement")
        assert learner_client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 503

    def test_outline_does_not_fail_when_billing_is_down(self, learner_client):
        course, _, _ = simple_course(access="entitlement")
        resp = learner_client.get(f"{V1}/courses/{course.slug}/")
        assert resp.status_code == 200 and resp.json()["access"]["can_enroll"] is False


class OpenToStaffOnly(EnrolledAccess):
    def self_enroll_source(self, course, user_id):
        from stapel_courses.errors import ERR_403_PURCHASE_REQUIRED
        from stapel_courses.services import CoursesError

        raise CoursesError(403, ERR_403_PURCHASE_REQUIRED)


class TestRegistry:
    def test_builtins(self):
        assert strategy_names() == ["enrolled", "entitlement", "free", "purchased"]

    def test_dotted_path_replaces_a_builtin(self, settings, learner_client):
        settings.STAPEL_COURSES = {
            "ACCESS_STRATEGIES": {"enrolled": "stapel_courses.tests.test_access.OpenToStaffOnly"}
        }
        assert type(get_strategy("enrolled")).__name__ == "OpenToStaffOnly"
        course, _, _ = simple_course()
        assert learner_client.post(f"{V1}/courses/{course.slug}/enroll/").status_code == 403

    def test_none_removes_and_the_course_fails_closed(self, settings, api_client):
        settings.STAPEL_COURSES = {"ACCESS_STRATEGIES": {"free": None}}
        assert "free" not in strategy_names()
        course, _, lessons = simple_course(access="free")
        assert api_client.get(lesson_url(course, lessons[0])).status_code == 403

    def test_staff_and_author_always_pass(self, client_for, staff, author):
        course, _, lessons = simple_course(author, access="purchased", price="5.00", currency="USD")
        assert client_for(staff).get(lesson_url(course, lessons[0])).status_code == 200
        assert client_for(author).get(lesson_url(course, lessons[0])).status_code == 200
