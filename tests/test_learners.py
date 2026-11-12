"""Author/staff enrollments name the learner: ``user_id`` and a profiles card when reachable."""
import pytest

from stapel_courses.models import Enrollment

from .factories import make_course

pytestmark = pytest.mark.django_db


def _list(client, course):
    resp = client.get(f"/courses/api/v1/author/courses/{course.pk}/enrollments/")
    assert resp.status_code == 200, resp.content
    return resp.json()["items"]


@pytest.fixture
def course(author):
    return make_course(author)


@pytest.fixture
def enrolled(course, learner, other_learner):
    for user in (learner, other_learner):
        Enrollment.objects.create(course=course, user_id=str(user.pk), status="active", source="staff")
    return course


def test_cards_resolve_in_one_batched_call(author_client, enrolled, learner, other_learner, cards):
    cards.names[str(learner.pk)] = "Alice L."
    items = {i["user_id"]: i for i in _list(author_client, enrolled)}
    assert items[str(learner.pk)]["learner"] == {
        "user_id": str(learner.pk), "display_name": "Alice L.", "avatar_ref": f"avatar-{learner.pk}",
    }
    assert items[str(other_learner.pk)]["learner"] is None, "an id profiles does not know"
    assert len(cards.calls) == 1
    assert sorted(cards.calls[0]["user_ids"]) == sorted([str(learner.pk), str(other_learner.pk)])


def test_absent_profiles_leaves_user_id_only(author_client, enrolled, learner):
    items = _list(author_client, enrolled)
    assert {i["user_id"] for i in items} >= {str(learner.pk)}
    assert all(i["learner"] is None for i in items)


def test_a_failing_profiles_degrades(author_client, enrolled, learner, cards):
    cards.names[str(learner.pk)] = "Alice"
    cards.fail = True
    assert all(i["learner"] is None for i in _list(author_client, enrolled))


def test_the_setting_switches_cards_off(author_client, enrolled, learner, cards, settings):
    cards.names[str(learner.pk)] = "Alice"
    settings.STAPEL_COURSES = {"CARDS_FUNCTION": ""}
    assert all(i["learner"] is None for i in _list(author_client, enrolled))
    assert cards.calls == []


def test_grant_and_transition_answer_with_the_learner(author_client, course, learner, cards):
    cards.names[str(learner.pk)] = "Alice"
    grant = author_client.post(f"/courses/api/v1/author/courses/{course.pk}/enrollments/",
                               {"user_id": str(learner.pk)}, format="json")
    assert grant.status_code == 201, grant.content
    assert grant.json()["learner"]["display_name"] == "Alice"
    moved = author_client.post(f"/courses/api/v1/author/enrollments/{grant.json()['id']}/transition/",
                               {"to": "cancelled"}, format="json")
    assert moved.status_code == 200, moved.content
    assert moved.json()["user_id"] == str(learner.pk)


def test_the_learner_facing_enrollment_stays_anonymous(learner_client, course, learner, cards):
    cards.names[str(learner.pk)] = "Alice"
    Enrollment.objects.create(course=course, user_id=str(learner.pk), status="active", source="free")
    item = learner_client.get("/courses/api/v1/me/enrollments/").json()["items"][0]
    assert "learner" not in item and "user_id" not in item
    assert cards.calls == []
