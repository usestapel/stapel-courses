"""The author/staff API: ownership scope, validation, publish lifecycle."""
import pytest

from stapel_courses.models import Course, Lesson, Question

from .factories import V1, make_course, make_lesson, make_module, make_quiz

pytestmark = pytest.mark.django_db


def create(client, **body):
    body = {"slug": "intro", "title": "Intro", **body}
    return client.post(f"{V1}/author/courses/", body, format="json")


class TestCreate:
    def test_staff_creates_with_defaults(self, staff_client, staff, settings):
        settings.STAPEL_COURSES = {"DEFAULT_DRIP": "days", "DEFAULT_SEQUENTIAL": True}
        body = create(staff_client).json()
        assert body["status"] == "draft" and body["author_id"] == str(staff.pk)
        assert body["access"] == "enrolled" and body["drip"] == "days" and body["sequential"] is True

    def test_staff_names_the_author(self, staff_client, author):
        assert create(staff_client, author_id=str(author.pk)).json()["author_id"] == str(author.pk)

    def test_members_cannot_author_by_default(self, author_client):
        resp = create(author_client)
        assert resp.status_code == 403
        assert resp.json()["localizable_error"] == "error.403.course_authoring_forbidden"

    def test_members_author_when_the_axis_says_so(self, author_client, author, settings):
        settings.STAPEL_COURSES = {"AUTHORING": "members"}
        body = create(author_client, author_id="someone-else").json()
        assert body["author_id"] == str(author.pk)

    def test_guests_never_author(self, client_for, guest, settings):
        settings.STAPEL_COURSES = {"AUTHORING": "members"}
        assert create(client_for(guest)).status_code == 403

    def test_anonymous_is_refused(self, api_client):
        assert create(api_client).status_code in (401, 403)

    def test_slug_taken(self, staff_client):
        create(staff_client)
        resp = create(staff_client)
        assert resp.status_code == 400
        assert resp.json()["localizable_error"] == "error.400.course_slug_taken"

    def test_unknown_access(self, staff_client):
        resp = create(staff_client, access="vip")
        assert resp.status_code == 400 and resp.json()["params"]["access"] == "vip"

    def test_purchased_needs_a_price(self, staff_client):
        resp = create(staff_client, access="purchased")
        assert resp.json()["localizable_error"] == "error.400.course_price_required"
        ok = create(staff_client, access="purchased", price="10.00", currency="eur")
        assert ok.status_code == 201 and ok.json()["currency"] == "EUR"


class TestScope:
    def test_author_sees_only_own_courses(self, author_client, author, client_for, other_learner):
        mine = make_course(author)
        make_course(other_learner)
        items = author_client.get(f"{V1}/author/courses/").json()["items"]
        assert [i["id"] for i in items] == [mine.pk]

    def test_foreign_course_is_404(self, author_client, other_learner):
        theirs = make_course(other_learner)
        assert author_client.get(f"{V1}/author/courses/{theirs.pk}/").status_code == 404
        assert author_client.patch(f"{V1}/author/courses/{theirs.pk}/", {"title": "x"},
                                   format="json").status_code == 404

    def test_tree(self, author_client, author):
        course = make_course(author)
        module = make_module(course)
        lesson = make_lesson(module)
        make_quiz(lesson)
        body = author_client.get(f"{V1}/author/courses/{course.pk}/").json()
        assert body["course"]["id"] == course.pk
        assert body["modules"][0]["lessons"][0]["blocks"][0]["type"] == "text"
        assert len(body["modules"][0]["quizzes"]) == 1


class TestLifecycle:
    def test_publish_archive_republish(self, author_client, author):
        course = make_course(author, status="draft")
        assert author_client.post(f"{V1}/author/courses/{course.pk}/archive/").status_code == 409
        published = author_client.post(f"{V1}/author/courses/{course.pk}/publish/").json()
        assert published["status"] == "published" and published["published_at"]
        assert author_client.post(f"{V1}/author/courses/{course.pk}/archive/").json()["status"] == "archived"
        assert author_client.post(f"{V1}/author/courses/{course.pk}/publish/").json()["status"] == "published"

    def test_slug_frozen_after_publish(self, author_client, author):
        course = make_course(author)
        resp = author_client.patch(f"{V1}/author/courses/{course.pk}/", {"slug": "new"}, format="json")
        assert resp.json()["localizable_error"] == "error.400.course_slug_frozen"

    def test_delete_only_drafts(self, author_client, author):
        published = make_course(author)
        draft = make_course(author, status="draft")
        assert author_client.delete(f"{V1}/author/courses/{published.pk}/").status_code == 409
        assert author_client.delete(f"{V1}/author/courses/{draft.pk}/").status_code == 204
        assert not Course.objects.filter(pk=draft.pk).exists()


class TestContent:
    def test_module_lesson_crud(self, author_client, author):
        course = make_course(author, status="draft")
        module = author_client.post(f"{V1}/author/courses/{course.pk}/modules/",
                                    {"title": "M1", "position": 1}, format="json").json()
        lesson = author_client.post(f"{V1}/author/modules/{module['id']}/lessons/", {
            "title": "L1", "blocks": [
                {"type": "text", "text": "Hello"},
                {"type": "video", "media_id": "cdn-1"},
                {"type": "attachment", "media_id": "cdn-2", "name": "notes.pdf"},
                {"type": "embed", "url": "https://video.example/abc"},
            ]}, format="json")
        assert lesson.status_code == 201
        assert lesson.json()["blocks"][0] == {"type": "text", "text": "Hello", "format": "markdown"}
        patched = author_client.patch(f"{V1}/author/lessons/{lesson.json()['id']}/",
                                      {"free_preview": True}, format="json").json()
        assert patched["free_preview"] is True
        assert author_client.patch(f"{V1}/author/modules/{module['id']}/", {"title": "M!"},
                                   format="json").json()["title"] == "M!"
        assert author_client.delete(f"{V1}/author/lessons/{lesson.json()['id']}/").status_code == 204
        assert author_client.delete(f"{V1}/author/modules/{module['id']}/").status_code == 204

    @pytest.mark.parametrize("block,reason", [
        ({"type": "nope"}, "type_unknown"),
        ({"type": "text", "text": ""}, "text_required"),
        ({"type": "text", "text": "x", "format": "html"}, "format_unknown"),
        ({"type": "video"}, "media_id_required"),
        ({"type": "embed", "url": "http://insecure.example/"}, "url_not_https"),
        ("just a string", "not_an_object"),
    ])
    def test_bad_blocks(self, author_client, author, block, reason):
        module = make_module(make_course(author))
        resp = author_client.post(f"{V1}/author/modules/{module.pk}/lessons/",
                                  {"title": "L", "blocks": [{"type": "text", "text": "ok"}, block]},
                                  format="json")
        if resp.status_code == 400 and resp.json()["localizable_error"] == "error.400.lesson_block_invalid":
            assert resp.json()["params"] == {"index": 1, "reason": reason}
        else:
            assert reason == "not_an_object" and resp.status_code == 400

    def test_embed_host_allowlist(self, author_client, author, settings):
        settings.STAPEL_COURSES = {"EMBED_HOSTS": ["video.example"]}
        module = make_module(make_course(author))
        ok = author_client.post(f"{V1}/author/modules/{module.pk}/lessons/",
                                {"title": "L", "blocks": [{"type": "embed", "url": "https://video.example/1"}]},
                                format="json")
        bad = author_client.post(f"{V1}/author/modules/{module.pk}/lessons/",
                                 {"title": "L", "blocks": [{"type": "embed", "url": "https://evil.example/1"}]},
                                 format="json")
        assert ok.status_code == 201 and bad.json()["params"]["reason"] == "host_not_allowed"

    def test_custom_block_type(self, author_client, author, settings):
        settings.STAPEL_COURSES = {"BLOCK_TYPES": {"callout": "stapel_courses.tests.test_authoring.callout"}}
        module = make_module(make_course(author))
        resp = author_client.post(f"{V1}/author/modules/{module.pk}/lessons/",
                                  {"title": "L", "blocks": [{"type": "callout", "tone": "warn"}]}, format="json")
        assert resp.status_code == 201 and Lesson.objects.get().blocks == [{"type": "callout", "tone": "warn"}]


def callout(raw):
    return {"type": "callout", "tone": str(raw.get("tone", "info"))}


class TestQuizzes:
    def test_quiz_needs_exactly_one_target(self, author_client, author):
        module = make_module(make_course(author))
        lesson = make_lesson(module)
        both = author_client.post(f"{V1}/author/quizzes/",
                                  {"title": "Q", "lesson_id": lesson.pk, "module_id": module.pk}, format="json")
        assert both.json()["localizable_error"] == "error.400.quiz_target_invalid"
        ok = author_client.post(f"{V1}/author/quizzes/", {"title": "Q", "lesson_id": lesson.pk}, format="json")
        assert ok.status_code == 201
        assert ok.json()["pass_mark"] == 70 and ok.json()["max_attempts"] == 3

    def test_question_shapes(self, author_client, author):
        lesson = make_lesson(make_module(make_course(author)))
        quiz = make_quiz(lesson)
        url = f"{V1}/author/quizzes/{quiz.pk}/questions/"
        choices = [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}]
        good = [
            {"kind": "single", "prompt": "p", "choices": choices, "correct": ["a"]},
            {"kind": "multiple", "prompt": "p", "choices": choices, "correct": ["a", "b"]},
            {"kind": "true_false", "prompt": "p", "correct": False},
            {"kind": "short_text", "prompt": "p", "correct": ["x"], "match": "exact"},
        ]
        for body in good:
            assert author_client.post(url, body, format="json").status_code == 201, body
        bad = [
            ({"kind": "single", "prompt": "p", "choices": choices, "correct": ["a", "b"]}, "single_needs_one"),
            ({"kind": "single", "prompt": "p", "choices": choices[:1], "correct": ["a"]}, "choices_count"),
            ({"kind": "multiple", "prompt": "p", "choices": choices, "correct": ["z"]}, "correct_not_in_choices"),
            ({"kind": "single", "prompt": "p", "choices": [{"id": "a", "text": "A"}] * 2, "correct": ["a"]},
             "choice_ids"),
            ({"kind": "true_false", "prompt": "p", "correct": "yes"}, "true_false_needs_bool"),
            ({"kind": "short_text", "prompt": "p", "correct": [""]}, "accepted_answers"),
        ]
        for body, reason in bad:
            resp = author_client.post(url, body, format="json")
            assert resp.status_code == 400 and resp.json()["params"]["reason"] == reason, body
        assert Question.objects.count() == 4

    def test_author_view_carries_answers(self, author_client, author):
        quiz = make_quiz(make_lesson(make_module(make_course(author))))
        author_client.post(f"{V1}/author/quizzes/{quiz.pk}/questions/",
                           {"kind": "true_false", "prompt": "p", "correct": True}, format="json")
        body = author_client.get(f"{V1}/author/quizzes/{quiz.pk}/").json()
        assert body["questions"][0]["correct"] is True
        qid = body["questions"][0]["id"]
        assert author_client.patch(f"{V1}/author/questions/{qid}/", {"correct": False},
                                   format="json").json()["correct"] is False
        assert author_client.patch(f"{V1}/author/quizzes/{quiz.pk}/", {"pass_mark": 90},
                                   format="json").json()["pass_mark"] == 90
        assert author_client.delete(f"{V1}/author/questions/{qid}/").status_code == 204
        assert author_client.delete(f"{V1}/author/quizzes/{quiz.pk}/").status_code == 204


class TestEnrollmentsAdmin:
    def test_list_grant_transition(self, author_client, author, learner):
        course = make_course(author)
        grant = author_client.post(f"{V1}/author/courses/{course.pk}/enrollments/",
                                   {"user_id": str(learner.pk)}, format="json").json()
        again = author_client.post(f"{V1}/author/courses/{course.pk}/enrollments/",
                                   {"user_id": str(learner.pk)}, format="json")
        assert again.status_code == 200
        items = author_client.get(f"{V1}/author/courses/{course.pk}/enrollments/").json()["items"]
        assert [i["id"] for i in items] == [grant["id"]]
        url = f"{V1}/author/enrollments/{grant['id']}/transition/"
        assert author_client.post(url, {"to": "cancelled"}, format="json").json()["status"] == "cancelled"
        assert author_client.post(url, {"to": "expired"}, format="json").status_code == 409
        assert author_client.post(url, {"to": "active"}, format="json").json()["status"] == "active"
        assert author_client.post(url, {"to": "active"}, format="json").status_code == 409

    def test_foreign_enrollment_is_404(self, author_client, learner, other_learner):
        from stapel_courses.models import Enrollment

        course = make_course(other_learner)

        enrollment = Enrollment.objects.create(course=course, user_id=str(learner.pk), status="active",
                                               source="free")
        resp = author_client.post(f"{V1}/author/enrollments/{enrollment.pk}/transition/",
                                  {"to": "cancelled"}, format="json")
        assert resp.status_code == 404

    def test_grant_with_expiry(self, staff_client, learner):
        course = make_course()
        body = staff_client.post(f"{V1}/author/courses/{course.pk}/enrollments/",
                                 {"user_id": str(learner.pk), "expires_at": "2030-01-01T00:00:00Z"},
                                 format="json").json()
        assert body["expires_at"].startswith("2030-01-01")
