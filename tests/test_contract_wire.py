"""Every response body the committed schema declares is the body the views send.

The operation list is DERIVED from ``docs/schema.json``: an operation with a
declared JSON 2xx body and no recipe here fails loudly. Every body is
validated against its declared schema (OAS ``nullable`` honoured), and each
list is driven in a populated and an empty state.
"""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from stapel_courses.models import Certificate, Enrollment

from .factories import make_course, make_lesson, make_module, make_quiz, multiple, short_text, single, true_false

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "docs" / "schema.json").read_text())
V1 = "/courses/api/v1"

pytestmark = pytest.mark.django_db


def _json_schema(node):
    if isinstance(node, list):
        return [_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    rebuilt = {k: _json_schema(v) for k, v in node.items() if k != "nullable"}
    if node.get("nullable"):
        return {"anyOf": [rebuilt, {"type": "null"}]}
    return rebuilt


def _validator(body_schema):
    root = copy.deepcopy(body_schema)
    root["components"] = copy.deepcopy(SCHEMA["components"])
    return jsonschema.Draft202012Validator(_json_schema(root))


def _operations():
    ops = []
    for path, methods in SCHEMA["paths"].items():
        for method, op in methods.items():
            for code, response in op.get("responses", {}).items():
                body = response.get("content", {}).get("application/json", {}).get("schema")
                if body is not None and code.startswith("2"):
                    ops.append((method.upper(), path, int(code), body))
    return sorted(ops, key=lambda o: (o[1], o[0], o[2]))


OPERATIONS = _operations()


class Env:
    def __init__(self, client_for, learner, author, staff):
        self.client_for = client_for
        self.learner, self.author, self.staff = learner, author, staff
        self.lc = client_for(learner)
        self.ac = client_for(author)
        course = make_course(author, slug="wire", sequential=True, access_days=30)
        module = make_module(course)
        self.course, self.module = course, module
        self.lessons = [make_lesson(module, position=1), make_lesson(module, position=2, review_required=True)]
        self.quiz = make_quiz(self.lessons[0], reveal="after_submit")
        self.questions = [single(self.quiz), multiple(self.quiz), true_false(self.quiz), short_text(self.quiz)]

    def enroll(self):
        return self.lc.post(f"{V1}/courses/{self.course.slug}/enroll/")

    def finish(self):
        """Complete everything: an enrollment, progress, a passed attempt, a certificate."""
        self.enroll()
        base = f"{V1}/courses/{self.course.slug}/lessons/"
        self.lc.post(f"{base}{self.lessons[0].pk}/progress/", {"status": "completed"}, format="json")
        attempt = self.lc.post(f"{V1}/quizzes/{self.quiz.pk}/attempts/").json()
        s, m, tf, st = self.questions
        self.lc.post(f"{V1}/attempts/{attempt['id']}/submit/", {"answers": [
            {"question_id": s.pk, "choice_ids": ["b"]}, {"question_id": m.pk, "choice_ids": ["a", "c"]},
            {"question_id": tf.pk, "value": True}, {"question_id": st.pk, "text": "mount everest"},
        ]}, format="json")
        self.lc.post(f"{base}{self.lessons[1].pk}/progress/", {"status": "submitted"}, format="json")
        self.ac.post(f"{V1}/author/lessons/{self.lessons[1].pk}/review/",
                     {"user_id": str(self.learner.pk), "passed": True}, format="json")
        return attempt["id"]


def r_attempt_get(clients):
    clients.enroll()
    open_attempt = clients.lc.post(f"{V1}/quizzes/{clients.quiz.pk}/attempts/").json()
    first = clients.lc.get(f"{V1}/attempts/{open_attempt['id']}/")
    clients.lc.post(f"{V1}/attempts/{open_attempt['id']}/submit/", {"answers": []}, format="json")
    return [first, clients.lc.get(f"{V1}/attempts/{open_attempt['id']}/")], []


def r_attempt_submit(clients):
    attempt_id = clients.finish()
    return [clients.lc.post(f"{V1}/attempts/{attempt_id}/submit/", {"answers": []}, format="json")], []


def r_revoke(clients):
    clients.finish()
    number = Certificate.objects.get().number
    return [clients.ac.post(f"{V1}/author/certificates/{number}/revoke/", {"reason": "test"}, format="json")], []


def r_author_list(clients):
    empty = clients.client_for(clients.learner).get(f"{V1}/author/courses/")
    return [clients.ac.get(f"{V1}/author/courses/")], [empty]


def r_author_create(clients):
    return [clients.client_for(clients.staff).post(f"{V1}/author/courses/", {
        "slug": "new-one", "title": "New", "access": "purchased", "price": "10.00", "currency": "USD"},
        format="json")], []


def r_author_tree(clients):
    empty = make_course(clients.author, slug="empty", status="draft")
    return [clients.ac.get(f"{V1}/author/courses/{clients.course.pk}/")], [
        clients.ac.get(f"{V1}/author/courses/{empty.pk}/")]


def r_author_patch(clients):
    return [clients.ac.patch(f"{V1}/author/courses/{clients.course.pk}/", {"summary": "s"}, format="json")], []


def r_author_archive(clients):
    return [clients.ac.post(f"{V1}/author/courses/{clients.course.pk}/archive/")], []


def r_author_publish(clients):
    draft = make_course(clients.author, slug="draft", status="draft")
    return [clients.ac.post(f"{V1}/author/courses/{draft.pk}/publish/")], []


def r_author_enrollments(clients):
    empty = clients.ac.get(f"{V1}/author/courses/{clients.course.pk}/enrollments/")
    clients.finish()
    return [clients.ac.get(f"{V1}/author/courses/{clients.course.pk}/enrollments/")], [empty]


def r_author_grant(code):
    def recipe(clients):
        url = f"{V1}/author/courses/{clients.course.pk}/enrollments/"
        first = clients.ac.post(url, {"user_id": str(clients.learner.pk)}, format="json")
        if code == 201:
            return [first], []
        return [clients.ac.post(url, {"user_id": str(clients.learner.pk)}, format="json")], []
    return recipe


def r_author_modules(clients):
    return [clients.ac.post(f"{V1}/author/courses/{clients.course.pk}/modules/", {"title": "M2"}, format="json")], []


def r_author_transition(clients):
    clients.enroll()
    enrollment = Enrollment.objects.get()
    return [clients.ac.post(f"{V1}/author/enrollments/{enrollment.pk}/transition/", {"to": "cancelled"},
                        format="json")], []


def r_author_lesson_patch(clients):
    return [clients.ac.patch(f"{V1}/author/lessons/{clients.lessons[0].pk}/", {"title": "x",
                         "unlock_at": "2030-01-01T00:00:00Z"}, format="json")], []


def r_author_review(clients):
    clients.enroll()
    return [clients.ac.post(f"{V1}/author/lessons/{clients.lessons[1].pk}/review/",
                        {"user_id": str(clients.learner.pk), "passed": False}, format="json")], []


def r_author_module_patch(clients):
    return [clients.ac.patch(f"{V1}/author/modules/{clients.module.pk}/", {"position": 3}, format="json")], []


def r_author_lessons(clients):
    return [clients.ac.post(f"{V1}/author/modules/{clients.module.pk}/lessons/", {
        "title": "L3", "blocks": [{"type": "video", "media_id": "m-1"}]}, format="json")], []


def r_author_question_patch(clients):
    return [clients.ac.patch(f"{V1}/author/questions/{clients.questions[0].pk}/", {"points": 3}, format="json")], []


def r_author_quizzes(clients):
    """A new quiz has no questions yet: its body is the empty state."""
    return [], [clients.ac.post(f"{V1}/author/quizzes/", {"title": "Module quiz", "module_id": clients.module.pk},
                            format="json")]


def r_author_quiz_get(clients):
    empty = make_quiz(clients.module)
    return [clients.ac.get(f"{V1}/author/quizzes/{clients.quiz.pk}/")], [clients.ac.get(f"{V1}/author/quizzes/{empty.pk}/")]


def r_author_quiz_patch(clients):
    return [clients.ac.patch(f"{V1}/author/quizzes/{clients.quiz.pk}/", {"max_attempts": 0}, format="json")], []


def r_author_questions(clients):
    return [clients.ac.post(f"{V1}/author/quizzes/{clients.quiz.pk}/questions/", {
        "kind": "single", "prompt": "p", "choices": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "correct": ["a"]}, format="json")], []


def r_verify(clients):
    clients.finish()
    number = Certificate.objects.get().number
    return [clients.client_for(None).get(f"{V1}/certificates/{number}/")], []


def r_catalog(clients):
    from stapel_courses.models import Course

    populated = clients.client_for(None).get(f"{V1}/courses/")
    Course.objects.update(status="draft")
    return [populated], [clients.client_for(None).get(f"{V1}/courses/")]


def r_outline(clients):
    anonymous = clients.client_for(None).get(f"{V1}/courses/{clients.course.slug}/")
    clients.finish()
    return [anonymous, clients.lc.get(f"{V1}/courses/{clients.course.slug}/")], []


def r_enroll(code):
    def recipe(clients):
        first = clients.enroll()
        return ([first] if code == 201 else [clients.enroll()]), []
    return recipe


def r_lesson(clients):
    clients.enroll()
    return [clients.lc.get(f"{V1}/courses/{clients.course.slug}/lessons/{clients.lessons[0].pk}/")], []


def r_progress(clients):
    clients.enroll()
    return [clients.lc.post(f"{V1}/courses/{clients.course.slug}/lessons/{clients.lessons[0].pk}/progress/",
                        {"position_seconds": 12}, format="json")], []


def r_course_progress(clients):
    empty = clients.lc.get(f"{V1}/courses/{clients.course.slug}/progress/")
    clients.finish()
    return [clients.lc.get(f"{V1}/courses/{clients.course.slug}/progress/")], [empty]


def r_my_certificates(clients):
    empty = clients.lc.get(f"{V1}/me/certificates/")
    clients.finish()
    return [clients.lc.get(f"{V1}/me/certificates/")], [empty]


def r_my_enrollments(clients):
    empty = clients.lc.get(f"{V1}/me/enrollments/")
    clients.finish()
    return [clients.lc.get(f"{V1}/me/enrollments/")], [empty]


def r_quiz(clients):
    anonymous = clients.client_for(None).get(f"{V1}/quizzes/{clients.quiz.pk}/")
    clients.finish()
    return [anonymous, clients.lc.get(f"{V1}/quizzes/{clients.quiz.pk}/")], []


def r_start(code):
    def recipe(clients):
        clients.enroll()
        first = clients.lc.post(f"{V1}/quizzes/{clients.quiz.pk}/attempts/")
        return ([first] if code == 201 else [clients.lc.post(f"{V1}/quizzes/{clients.quiz.pk}/attempts/")]), []
    return recipe


A = V1 + "/author"
RECIPES = {
    ("GET", V1 + "/attempts/{attempt_id}/", 200): r_attempt_get,
    ("POST", V1 + "/attempts/{attempt_id}/submit/", 200): r_attempt_submit,
    ("POST", A + "/certificates/{number}/revoke/", 200): r_revoke,
    ("GET", A + "/courses/", 200): r_author_list,
    ("POST", A + "/courses/", 201): r_author_create,
    ("GET", A + "/courses/{course_id}/", 200): r_author_tree,
    ("PATCH", A + "/courses/{course_id}/", 200): r_author_patch,
    ("POST", A + "/courses/{course_id}/archive/", 200): r_author_archive,
    ("GET", A + "/courses/{course_id}/enrollments/", 200): r_author_enrollments,
    ("POST", A + "/courses/{course_id}/enrollments/", 201): r_author_grant(201),
    ("POST", A + "/courses/{course_id}/enrollments/", 200): r_author_grant(200),
    ("POST", A + "/courses/{course_id}/modules/", 201): r_author_modules,
    ("POST", A + "/courses/{course_id}/publish/", 200): r_author_publish,
    ("POST", A + "/enrollments/{enrollment_id}/transition/", 200): r_author_transition,
    ("PATCH", A + "/lessons/{lesson_id}/", 200): r_author_lesson_patch,
    ("POST", A + "/lessons/{lesson_id}/review/", 200): r_author_review,
    ("PATCH", A + "/modules/{module_id}/", 200): r_author_module_patch,
    ("POST", A + "/modules/{module_id}/lessons/", 201): r_author_lessons,
    ("PATCH", A + "/questions/{question_id}/", 200): r_author_question_patch,
    ("POST", A + "/quizzes/", 201): r_author_quizzes,
    ("GET", A + "/quizzes/{quiz_id}/", 200): r_author_quiz_get,
    ("PATCH", A + "/quizzes/{quiz_id}/", 200): r_author_quiz_patch,
    ("POST", A + "/quizzes/{quiz_id}/questions/", 201): r_author_questions,
    ("GET", V1 + "/certificates/{number}/", 200): r_verify,
    ("GET", V1 + "/courses/", 200): r_catalog,
    ("GET", V1 + "/courses/{slug}/", 200): r_outline,
    ("POST", V1 + "/courses/{slug}/enroll/", 201): r_enroll(201),
    ("POST", V1 + "/courses/{slug}/enroll/", 200): r_enroll(200),
    ("GET", V1 + "/courses/{slug}/lessons/{lesson_id}/", 200): r_lesson,
    ("POST", V1 + "/courses/{slug}/lessons/{lesson_id}/progress/", 200): r_progress,
    ("GET", V1 + "/courses/{slug}/progress/", 200): r_course_progress,
    ("GET", V1 + "/me/certificates/", 200): r_my_certificates,
    ("GET", V1 + "/me/enrollments/", 200): r_my_enrollments,
    ("GET", V1 + "/quizzes/{quiz_id}/", 200): r_quiz,
    ("POST", V1 + "/quizzes/{quiz_id}/attempts/", 201): r_start(201),
    ("POST", V1 + "/quizzes/{quiz_id}/attempts/", 200): r_start(200),
}


def test_every_declared_operation_has_a_recipe():
    declared = {(m, p, c) for m, p, c, _ in OPERATIONS}
    assert declared == set(RECIPES), {
        "missing": sorted(declared - set(RECIPES)),
        "stale": sorted(set(RECIPES) - declared),
    }


@pytest.mark.parametrize("method,path,code,body_schema", OPERATIONS,
                         ids=[f"{m} {p} {c}" for m, p, c, _ in OPERATIONS])
def test_wire_matches_the_declared_body(method, path, code, body_schema, client_for, learner, author, staff):
    populated, empty = RECIPES[(method, path, code)](Env(client_for, learner, author, staff))
    validator = _validator(body_schema)
    for resp in populated + empty:
        assert resp.status_code == code, (method, path, resp.status_code, resp.content[:300])
        errors = sorted(validator.iter_errors(resp.json()), key=str)
        assert not errors, [e.message for e in errors[:5]]
    for resp in populated:
        data = resp.json()
        for key in ("items", "modules", "questions", "lessons"):
            if key in data:
                assert data[key], f"{method} {path}: populated '{key}' came back empty"
    for resp in empty:
        data = resp.json()
        for key in ("items", "questions", "lessons"):
            if key in data:
                assert not data[key], f"{method} {path}: the empty state is not empty"


def test_the_gate_is_not_blind(client_for, learner, author, staff):
    """Inversion: a body validated against a wrong schema must fail."""
    clients = Env(client_for, learner, author, staff)
    body = clients.enroll().json()
    schema = SCHEMA["paths"][V1 + "/courses/{slug}/enroll/"]["post"]["responses"]["201"][
        "content"]["application/json"]["schema"]
    assert not list(_validator(schema).iter_errors(body))
    assert list(_validator(schema).iter_errors(dict(body, progress_percent="50")))
    assert list(_validator(schema).iter_errors(dict(body, status="lost")))
