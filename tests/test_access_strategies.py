"""``GET author/access-strategies/``: the registry the editor's access picker offers."""
import pytest

from .factories import V1

pytestmark = pytest.mark.django_db

URL = f"{V1}/author/access-strategies/"


def test_the_builtins_by_default(author_client):
    body = author_client.get(URL).json()
    assert body == {
        "items": [{"name": n, "builtin": True} for n in ("enrolled", "entitlement", "free", "purchased")],
        "default": "enrolled",
    }


def test_the_host_registry_merges_and_the_api_validates_against_it(settings, staff_client):
    settings.STAPEL_COURSES = {
        "ACCESS_STRATEGIES": {
            "cohort": "stapel_courses.access.EnrolledAccess",
            "entitlement": None,
            "free": "stapel_courses.access.EnrolledAccess",
        },
        "DEFAULT_ACCESS": "cohort",
    }
    body = staff_client.get(URL).json()
    assert body["items"] == [
        {"name": "cohort", "builtin": False},
        {"name": "enrolled", "builtin": True},
        {"name": "free", "builtin": False},
        {"name": "purchased", "builtin": True},
    ]
    assert body["default"] == "cohort"
    names = [item["name"] for item in body["items"]]
    created = staff_client.post(f"{V1}/author/courses/", {"slug": "c1", "title": "C", "access": "cohort"},
                                format="json")
    assert created.status_code == 201 and created.json()["access"] in names
    refused = staff_client.post(f"{V1}/author/courses/", {"slug": "c2", "title": "C", "access": "entitlement"},
                                format="json")
    assert refused.status_code == 400
    assert refused.json()["localizable_error"] == "error.400.course_access_unknown"


def test_guests_are_refused(client_for, guest):
    assert client_for(guest).get(URL).status_code in (401, 403)
