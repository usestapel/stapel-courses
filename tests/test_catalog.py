"""Catalog, outline visibility and self-enrollment over HTTP."""
import pytest

from stapel_courses.models import CourseStatus, Enrollment

from .factories import V1, make_course, make_lesson, make_module, simple_course

pytestmark = pytest.mark.django_db


def test_catalog_lists_published_only(api_client):
    published = make_course(title="Open")
    make_course(status=CourseStatus.DRAFT)
    make_course(status=CourseStatus.ARCHIVED)
    body = api_client.get(f"{V1}/courses/").json()
    assert [c["slug"] for c in body["items"]] == [published.slug]
    assert body["count"] == 1 and body["has_next"] is False


def test_catalog_filters_and_counts_lessons(api_client):
    course, module, _ = simple_course(level="advanced")
    make_lesson(module, position=3, duration_seconds=90)
    make_course(level="beginner")
    items = api_client.get(f"{V1}/courses/", {"level": "advanced"}).json()["items"]
    assert [i["id"] for i in items] == [course.pk]
    assert items[0]["lesson_count"] == 3 and items[0]["total_duration_seconds"] == 90


def test_catalog_anchor_walks_every_course(api_client):
    ids = {make_course().pk for _ in range(5)}
    seen, anchor = [], None
    while True:
        params = {"limit": 2, **({"anchor": anchor} if anchor else {})}
        body = api_client.get(f"{V1}/courses/", params).json()
        seen += [c["id"] for c in body["items"]]
        if not body["has_next"]:
            break
        anchor = body["next_anchor"]
        assert isinstance(anchor, str)
    assert set(seen) == ids and len(seen) == 5


def test_bad_anchor_reads_as_head(api_client):
    make_course()
    assert api_client.get(f"{V1}/courses/", {"anchor": "x"}).status_code == 200


def test_draft_is_404_for_strangers_and_open_to_author(api_client, client_for, author):
    course = make_course(author, status=CourseStatus.DRAFT)
    assert api_client.get(f"{V1}/courses/{course.slug}/").status_code == 404
    resp = client_for(author).get(f"{V1}/courses/{course.slug}/")
    assert resp.status_code == 200 and resp.json()["access"]["privileged"] is True


def test_unknown_course_is_the_same_404(api_client):
    resp = api_client.get(f"{V1}/courses/nope/")
    assert resp.status_code == 404
    assert resp.json()["localizable_error"] == "error.404.course_not_found"


def test_archived_course_stays_open_to_its_learners(client_for, learner, other_learner):
    course, _, _ = simple_course()
    Enrollment.objects.create(course=course, user_id=str(learner.pk), status="active", source="free")
    course.status = CourseStatus.ARCHIVED
    course.save()
    assert client_for(learner).get(f"{V1}/courses/{course.slug}/").status_code == 200
    assert client_for(other_learner).get(f"{V1}/courses/{course.slug}/").status_code == 404


class TestOutline:
    def test_anonymous_sees_lock_reasons_but_no_content(self, api_client):
        course, module, lessons = simple_course()
        make_lesson(module, position=3, free_preview=True)
        body = api_client.get(f"{V1}/courses/{course.slug}/").json()
        outline = body["modules"][0]["lessons"]
        assert [lesson["lock_reason"] for lesson in outline] == ["sign_in_required", "sign_in_required", None]
        assert body["access"] == {"allowed": False, "reason": "sign_in_required",
                                  "can_enroll": False, "privileged": False}
        assert "secret body" not in str(body)

    def test_learner_before_and_after_enrolling(self, learner_client, captured_events):
        course, _, _ = simple_course()
        before = learner_client.get(f"{V1}/courses/{course.slug}/").json()
        assert before["access"]["reason"] == "enrollment_required"
        assert before["access"]["can_enroll"] is True and before["enrollment"] is None
        resp = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 201
        enrollment = resp.json()
        assert enrollment["status"] == "active" and enrollment["source"] == "free"
        assert enrollment["required_lessons"] == 2 and enrollment["progress_percent"] == 0
        assert [e.event_type for e in captured_events] == ["courses.enrollment.activated"]
        again = learner_client.post(f"{V1}/courses/{course.slug}/enroll/")
        assert again.status_code == 200 and again.json()["id"] == enrollment["id"]
        assert len(captured_events) == 1
        after = learner_client.get(f"{V1}/courses/{course.slug}/").json()
        assert after["access"]["allowed"] is True and after["access"]["can_enroll"] is False
        assert all(not lesson["locked"] for lesson in after["modules"][0]["lessons"])

    def test_draft_course_cannot_be_enrolled(self, client_for, author, learner):
        course = make_course(author, status=CourseStatus.DRAFT)
        make_lesson(make_module(course))
        resp = client_for(author).post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 409
        assert resp.json()["localizable_error"] == "error.409.course_not_published"


class TestGuests:
    def test_anonymous_enroll_is_401(self, api_client):
        course, _, _ = simple_course()
        assert api_client.post(f"{V1}/courses/{course.slug}/enroll/").status_code in (401, 403)

    def test_guest_is_asked_to_sign_in(self, client_for, guest):
        course, _, _ = simple_course()
        resp = client_for(guest).post(f"{V1}/courses/{course.slug}/enroll/")
        assert resp.status_code == 403
        assert resp.json()["localizable_error"] == "error.403.enrollment_requires_account"

    def test_guest_may_enroll_when_the_switch_is_off(self, client_for, guest, settings):
        settings.STAPEL_COURSES = {"ENROLLMENT_REQUIRES_ACCOUNT": False}
        course, _, _ = simple_course()
        assert client_for(guest).post(f"{V1}/courses/{course.slug}/enroll/").status_code == 201
