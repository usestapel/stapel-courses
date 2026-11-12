"""``GET author/courses/{id}/certificates/``: a course's certificates with their holders."""
import datetime as dt

import pytest
from django.utils import timezone

from stapel_courses.models import Certificate

from .factories import V1, make_course

pytestmark = pytest.mark.django_db


def _url(course):
    return f"{V1}/author/courses/{course.pk}/certificates/"


@pytest.fixture
def course(author):
    return make_course(author)


@pytest.fixture
def issued(course, learner, other_learner):
    now = timezone.now()
    first = Certificate.objects.create(number="CERT-2026-AAAAAAAA", course=course, user_id=str(learner.pk),
                                       holder_name="Alice Learner", course_title=course.title, issued_at=now)
    second = Certificate.objects.create(number="CERT-2026-BBBBBBBB", course=course,
                                        user_id=str(other_learner.pk), course_title=course.title,
                                        issued_at=now + dt.timedelta(seconds=1))
    return first, second


def test_lists_number_holder_issue_and_revocation(author_client, course, issued, learner, cards):
    cards.names[str(learner.pk)] = "Alice"
    first, second = issued
    revoked = author_client.post(f"{V1}/author/certificates/{second.number}/revoke/", {"reason": "fraud"},
                                 format="json")
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    items = author_client.get(_url(course)).json()["items"]
    assert [i["number"] for i in items] == [second.number, first.number]
    alice = items[1]
    assert (alice["user_id"], alice["holder_name"], alice["revoked"], alice["valid"]) == (
        str(learner.pk), "Alice Learner", False, True)
    assert alice["learner"]["display_name"] == "Alice"
    assert items[0]["revoked"] is True and items[0]["revoke_reason"] == "fraud"
    assert items[0]["revoked_at"] is not None and items[0]["learner"] is None


def test_revoked_filter(author_client, course, issued):
    author_client.post(f"{V1}/author/certificates/{issued[1].number}/revoke/", {}, format="json")
    assert [i["number"] for i in author_client.get(_url(course) + "?revoked=true").json()["items"]] == [
        issued[1].number]
    assert [i["number"] for i in author_client.get(_url(course) + "?revoked=false").json()["items"]] == [
        issued[0].number]


def test_only_for_who_may_edit_the_course(client_for, other_learner, staff_client, course, issued):
    assert client_for(other_learner).get(_url(course)).status_code == 404
    assert len(staff_client.get(_url(course)).json()["items"]) == 2
