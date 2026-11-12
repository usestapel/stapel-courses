def pytest_configure(config):
    from django.conf import settings

    if not settings.configured:
        from stapel_courses._codegen_settings import settings_kwargs

        settings.configure(**settings_kwargs())
        import django

        django.setup()

        from stapel_core.comm.schemas import autoload_schemas

        autoload_schemas()


import pytest  # noqa: E402
from stapel_core.testing import emit_outside_atomic_gate  # noqa: E402,F401


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


def _make_user(username, **extra):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="x", **extra
    )


@pytest.fixture
def learner(db):
    return _make_user("alice", first_name="Alice", last_name="Learner")


@pytest.fixture
def other_learner(db):
    return _make_user("bob")


@pytest.fixture
def author(db):
    return _make_user("author")


@pytest.fixture
def guest(db):
    return _make_user("guest-1", is_anonymous=True)


@pytest.fixture
def staff(db):
    return _make_user("staff", is_staff=True)


@pytest.fixture
def client_for():
    def _client(u):
        from rest_framework.test import APIClient

        c = APIClient()
        if u is not None:
            c.force_authenticate(user=u)
        return c

    return _client


@pytest.fixture
def learner_client(client_for, learner):
    return client_for(learner)


@pytest.fixture
def author_client(client_for, author):
    return client_for(author)


@pytest.fixture
def staff_client(client_for, staff):
    return client_for(staff)


@pytest.fixture
def captured_events():
    """Collect courses emits delivered in-process."""
    from stapel_core.comm import action_registry, subscribe_action

    from stapel_courses.services.events import EMITS

    collected = []

    def _handler(event):
        collected.append(event)

    for name in EMITS:
        subscribe_action(name, _handler)
    try:
        yield collected
    finally:
        for name in EMITS:
            handlers = action_registry._subscribers.get(name, [])
            if _handler in handlers:
                handlers.remove(_handler)


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def billing():
    """A fake ``billing.check_entitlement``; set ``billing.allowed``."""
    from stapel_courses.tests.factories import FakeFunction

    state = {"allowed": True}
    fake = FakeFunction("billing.check_entitlement", lambda p: {
        "allowed": state["allowed"], "limit": None, "reason": None,
    })
    fake.state = state
    fake.install()
    try:
        yield fake
    finally:
        fake.uninstall()
