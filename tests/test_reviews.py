"""The review queue: ``GET author/reviews/`` lists lessons submitted for review."""
import pytest

from .factories import V1, make_course, make_lesson, make_module, simple_course

pytestmark = pytest.mark.django_db

URL = f"{V1}/author/reviews/"


def _submit(client, course, lesson):
    client.post(f"{V1}/courses/{course.slug}/enroll/")
    resp = client.post(f"{V1}/courses/{course.slug}/lessons/{lesson.pk}/progress/",
                       {"status": "submitted"}, format="json")
    assert resp.status_code == 200, resp.content


@pytest.fixture
def queued(author, learner_client):
    course, module, _ = simple_course(author, lessons=0)
    lesson = make_lesson(module, review_required=True, title="Essay")
    _submit(learner_client, course, lesson)
    return course, lesson


def test_a_submission_is_listed_with_what_review_needs(author_client, queued, learner, cards):
    course, lesson = queued
    cards.names[str(learner.pk)] = "Alice"
    items = author_client.get(URL).json()["items"]
    assert len(items) == 1
    item = items[0]
    assert (item["lesson_id"], item["lesson_title"], item["course_id"]) == (lesson.pk, "Essay", course.pk)
    assert item["user_id"] == str(learner.pk)
    assert item["learner"]["display_name"] == "Alice"
    verdict = author_client.post(f"{V1}/author/lessons/{item['lesson_id']}/review/",
                                 {"user_id": item["user_id"], "passed": True}, format="json")
    assert verdict.status_code == 200
    assert author_client.get(URL).json()["items"] == [], "a reviewed lesson leaves the queue"


def test_a_returned_submission_leaves_the_queue(author_client, queued, learner):
    _, lesson = queued
    author_client.post(f"{V1}/author/lessons/{lesson.pk}/review/",
                       {"user_id": str(learner.pk), "passed": False}, format="json")
    assert author_client.get(URL).json()["items"] == []


def test_filter_by_course(author_client, author, queued):
    course, _ = queued
    other = make_course(author)
    make_module(other)
    assert len(author_client.get(f"{URL}?course={course.pk}").json()["items"]) == 1
    assert author_client.get(f"{URL}?course={other.pk}").json()["items"] == []


def test_another_authors_queue_is_not_mine(client_for, other_learner, queued, staff_client):
    course, _ = queued
    stranger = client_for(other_learner)
    assert stranger.get(URL).json()["items"] == []
    assert stranger.get(f"{URL}?course={course.pk}").status_code == 404
    assert stranger.get(f"{URL}?course=abc").status_code == 404
    assert len(staff_client.get(URL).json()["items"]) == 1, "staff see every course"


def test_guests_are_refused(client_for, guest):
    assert client_for(guest).get(URL).status_code in (401, 403)
