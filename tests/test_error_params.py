"""Every param a raised error carries is declared in ``docs/errors.json``.

A client types an error's params from the artifact (``errors.json`` →
``params``, derived from the ``{slot}`` placeholders of the en template); a
param the server sends but the artifact does not declare is invisible to
that typing. Two halves:

- a static scan of every ``CoursesError(status, ERR_X, params)`` call in the
  package: a literal dict's keys must be declared; a non-literal params
  argument must be one of :data:`DYNAMIC`, each proved at runtime below;
- the runtime proof of :data:`DYNAMIC`: every shape the call can produce
  carries exactly the declared params.
"""
import ast
import json
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
ERRORS_JSON = PACKAGE / "docs" / "errors.json"

#: Raise sites whose params are computed, keyed by the error constant; each
#: has a runtime test in this module.
DYNAMIC = {"ERR_403_LESSON_LOCKED": "ItemState.params"}


def _declared() -> dict[str, set]:
    return {e["code"]: set(e["params"]) for e in json.loads(ERRORS_JSON.read_text())}


def _sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(PACKAGE).parts
        if rel[0] in ("tests", "build", "dist", ".venv", "migrations") or ".egg-info" in str(path):
            continue
        yield path


def _raise_sites():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "CoursesError":
                continue
            yield f"{path.relative_to(PACKAGE)}:{node.lineno}", node


def test_every_raise_site_names_its_code_by_constant():
    sites = list(_raise_sites())
    assert len(sites) > 30, f"scanned only {len(sites)} raise sites — the scan lost its subject"
    from stapel_courses import errors

    bad = [
        where for where, node in sites
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Name)
        or not hasattr(errors, node.args[1].id)
    ]
    assert bad == []


def test_every_literal_param_is_declared():
    from stapel_courses import errors

    declared = _declared()
    undeclared = []
    dynamic_seen = set()
    for where, node in _raise_sites():
        if len(node.args) < 3:
            continue
        constant = node.args[1].id
        code = getattr(errors, constant)
        params = node.args[2]
        if isinstance(params, ast.Dict):
            keys = {k.value for k in params.keys if isinstance(k, ast.Constant)}
            assert len(keys) == len(params.keys), f"{where}: non-literal param name"
            missing = keys - declared.get(code, set())
            if missing:
                undeclared.append(f"{where} {code}: {sorted(missing)}")
        else:
            assert constant in DYNAMIC, f"{where}: computed params for {code} with no runtime proof"
            dynamic_seen.add(constant)
    assert undeclared == []
    assert dynamic_seen == set(DYNAMIC), "a DYNAMIC entry no longer matches a raise site"


@pytest.mark.parametrize("state_kwargs", [
    {"locked": True, "reason": "enrollment_required"},
    {"locked": True, "reason": "drip", "unlocks_at": "now"},
    {"locked": True, "reason": "sequential", "after_lesson_id": 3},
    {"locked": True, "reason": "sequential", "after_quiz_id": 4},
])
def test_lesson_locked_params_are_exactly_the_declared_ones(state_kwargs):
    import datetime as dt

    from stapel_courses.errors import ERR_403_LESSON_LOCKED
    from stapel_courses.services.gate import ItemState

    if state_kwargs.get("unlocks_at") == "now":
        state_kwargs = {**state_kwargs, "unlocks_at": dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)}
    params = ItemState(**state_kwargs).params()
    assert set(params) == _declared()[ERR_403_LESSON_LOCKED]
