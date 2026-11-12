"""``EMBED_HOSTS`` reaches the renderer: the outline, the lesson and the author tree carry it."""
import pytest

from .factories import V1, simple_course

pytestmark = pytest.mark.django_db


@pytest.fixture
def opened(author, learner_client):
    course, module, lessons = simple_course(author, lessons=1, access="free")
    return course, lessons[0]


@pytest.mark.parametrize("configured,exposed", [
    ([], []),
    (["Player.Vimeo.com", "www.youtube.com", " "], ["player.vimeo.com", "www.youtube.com"]),
])
def test_every_payload_carries_the_allowlist(configured, exposed, settings, opened, learner_client,
                                             author_client):
    settings.STAPEL_COURSES = {"EMBED_HOSTS": configured}
    course, lesson = opened
    outline = learner_client.get(f"{V1}/courses/{course.slug}/").json()
    read = learner_client.get(f"{V1}/courses/{course.slug}/lessons/{lesson.pk}/").json()
    tree = author_client.get(f"{V1}/author/courses/{course.pk}/").json()
    assert outline["embed_hosts"] == read["embed_hosts"] == tree["embed_hosts"] == exposed


def test_the_exposed_list_is_the_one_authoring_enforces(settings, author_client, opened):
    settings.STAPEL_COURSES = {"EMBED_HOSTS": ["Player.Vimeo.com"]}
    course, lesson = opened
    url = f"{V1}/author/lessons/{lesson.pk}/"
    ok = author_client.patch(url, {"blocks": [{"type": "embed", "url": "https://player.vimeo.com/v/1"}]},
                             format="json")
    assert ok.status_code == 200, ok.content
    refused = author_client.patch(url, {"blocks": [{"type": "embed", "url": "https://evil.example/x"}]},
                                  format="json")
    assert refused.status_code == 400
    assert refused.json()["params"]["reason"] == "host_not_allowed"
