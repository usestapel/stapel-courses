"""``EMBED_HOSTS`` reaches the renderer: the outline, the lesson and the author tree carry it.

It fails closed, as in stapel-cms: an empty list accepts no embed block.
"""
import pytest

from stapel_courses.blocks import embed_host_allowed
from stapel_courses.conf import DEFAULT_EMBED_HOSTS

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


def _patch_embed(author_client, lesson, url):
    return author_client.patch(f"{V1}/author/lessons/{lesson.pk}/",
                               {"blocks": [{"type": "embed", "url": url}]}, format="json")


def test_default_allowlist_is_the_known_video_and_map_hosts(author_client, opened, learner_client):
    course, lesson = opened
    assert learner_client.get(f"{V1}/courses/{course.slug}/").json()["embed_hosts"] == sorted(DEFAULT_EMBED_HOSTS)
    assert _patch_embed(author_client, lesson, "https://www.youtube.com/embed/x").status_code == 200
    refused = _patch_embed(author_client, lesson, "https://evil.example/x")
    assert refused.status_code == 400
    assert refused.json()["params"]["reason"] == "host_not_allowed"


def test_empty_allowlist_accepts_no_embed(settings, author_client, opened):
    settings.STAPEL_COURSES = {"EMBED_HOSTS": []}
    course, lesson = opened
    refused = _patch_embed(author_client, lesson, "https://www.youtube.com/embed/x")
    assert refused.status_code == 400
    assert refused.json()["params"]["reason"] == "host_not_allowed"


@pytest.mark.parametrize("url,ok", [
    ("https://player.vimeo.com/v/1", True),
    ("https://PLAYER.vimeo.com./v/1", True),
    ("https://player.vimeo.com:443/v/1", True),
    ("https://player.vimeo.com:8443/v/1", False),
    ("https://user@player.vimeo.com/v/1", False),
    ("https://vimeo.com.evil.example/v/1", False),
    ("https://evil.example/player.vimeo.com", False),
])
def test_host_match_is_exact(url, ok):
    assert embed_host_allowed(url, ["player.vimeo.com"]) is ok
    assert embed_host_allowed(url, []) is False
