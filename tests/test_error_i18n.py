"""Localized error catalogs (``translations/errors.<lang>.json``) + reference.

The convention of stapel-profiles: the en canon is the registry
(``errors.py`` → ``docs/errors.json``); every target language ships a flat
``translations/errors.<lang>.json`` with the shared ``translations/.state.json``
provenance sidecar, and ``docs/errors.<lang>.md`` is the per-language error
reference. :func:`check_translation_catalogs` gates coverage, staleness,
placeholders and byte stability. Core-owned keys are core's to translate and
never copied here.

The strings (seeded from the React pair's authored texts) are kept in
:data:`_MACHINE` (``origin: llm``), so the catalog regenerates
deterministically without a live model.
Adding a language: append it to :data:`LANGUAGES`, add its table, regenerate.

Regenerate after adding/changing an error key or a translation:

    STAPEL_REGEN_ERROR_I18N=1 python -m pytest tests/test_error_i18n.py::test_regen

then commit ``translations/`` + ``docs/errors.<lang>.md``. Without the env
var the same module is the CI gate.
"""
import io
import os
import tomllib
from pathlib import Path

import pytest
from django.core.management import call_command
from stapel_core.i18n import (
    check_translation_catalogs,
    source_texts,
    summarize,
    translate_catalog,
)
from stapel_core.i18n.catalogs import load_catalog_file

REPO = Path(__file__).resolve().parent.parent
TRANSLATIONS = REPO / "translations"
DOCS = REPO / "docs"
THIS_PACKAGE = "stapel_courses"
LANGUAGES = ["en", "ru", "es"]
TARGET_LANGUAGES = [lang for lang in LANGUAGES if lang != "en"]

_MACHINE_RU = {
    "error.400.course_access_unknown": "Неизвестный режим доступа {access}",
    "error.400.course_price_required": "Для продажи курса через заказы нужны цена и валюта",
    "error.400.course_slug_frozen": "Адрес опубликованного курса нельзя изменить",
    "error.400.course_slug_taken": "Адрес {slug} уже занят другим курсом",
    "error.400.lesson_block_invalid": "Блок содержимого {index} заполнен неверно ({reason})",
    "error.400.question_invalid": "Вопрос составлен неверно ({reason})",
    "error.400.quiz_answer_invalid": "Ответ на вопрос {question_id} ему не подходит",
    "error.400.quiz_target_invalid": "Тест относится ровно к одному уроку или модулю курса",
    "error.403.course_authoring_forbidden": "Вы не можете редактировать этот курс",
    "error.403.course_entitlement_required": "Ваш тариф не включает этот курс",
    "error.403.course_purchase_required": "Купите курс, чтобы начать обучение",
    "error.403.enrollment_requires_account": "Войдите, чтобы записаться",
    "error.403.lesson_locked": "Этот урок пока закрыт ({reason}; откроется {unlocks_at}; после урока {after_lesson_id}; после теста {after_quiz_id})",
    "error.403.lesson_review_required": "Урок засчитывается после проверки",
    "error.404.certificate_not_found": "Сертификат не найден",
    "error.404.course_module_not_found": "Модуль не найден",
    "error.404.course_not_found": "Курс не найден",
    "error.404.enrollment_not_found": "Запись на курс не найдена",
    "error.404.lesson_not_found": "Урок не найден",
    "error.404.question_not_found": "Вопрос не найден",
    "error.404.quiz_attempt_not_found": "Попытка не найдена",
    "error.404.quiz_not_found": "Тест не найден",
    "error.409.course_not_draft": "Удалить можно только черновик курса",
    "error.409.course_not_published": "Запись на этот курс закрыта",
    "error.409.course_transition_invalid": "Курс нельзя перевести из {from} в {to}",
    "error.409.enrollment_transition_invalid": "Запись нельзя перевести из {from} в {to}",
    "error.409.quiz_attempts_exhausted": "Попыток не осталось (не более {max})",
    "error.409.quiz_empty": "В этом тесте пока нет вопросов",
    "error.503.entitlement_unavailable": "Сейчас не удаётся проверить ваш тариф, попробуйте чуть позже",
}

_MACHINE_ES = {
    "error.400.course_access_unknown": "Modo de acceso desconocido {access}",
    "error.400.course_price_required": "Un curso vendido mediante pedidos necesita precio y moneda",
    "error.400.course_slug_frozen": "La dirección de un curso publicado no se puede cambiar",
    "error.400.course_slug_taken": "La dirección {slug} ya la usa otro curso",
    "error.400.lesson_block_invalid": "El bloque de contenido {index} no es válido ({reason})",
    "error.400.question_invalid": "La pregunta no es válida ({reason})",
    "error.400.quiz_answer_invalid": "La respuesta a la pregunta {question_id} no le corresponde",
    "error.400.quiz_target_invalid": "Un cuestionario pertenece exactamente a una lección o un módulo del curso",
    "error.403.course_authoring_forbidden": "No puedes editar este curso",
    "error.403.course_entitlement_required": "Tu plan no incluye este curso",
    "error.403.course_purchase_required": "Compra este curso para empezar a aprender",
    "error.403.enrollment_requires_account": "Inicia sesión para inscribirte",
    "error.403.lesson_locked": "Esta lección aún no está abierta ({reason}; se abre el {unlocks_at}; tras la lección {after_lesson_id}; tras el cuestionario {after_quiz_id})",
    "error.403.lesson_review_required": "Esta lección se completa cuando un revisor la acepta",
    "error.404.certificate_not_found": "Certificado no encontrado",
    "error.404.course_module_not_found": "Módulo no encontrado",
    "error.404.course_not_found": "Curso no encontrado",
    "error.404.enrollment_not_found": "Inscripción no encontrada",
    "error.404.lesson_not_found": "Lección no encontrada",
    "error.404.question_not_found": "Pregunta no encontrada",
    "error.404.quiz_attempt_not_found": "Intento no encontrado",
    "error.404.quiz_not_found": "Cuestionario no encontrado",
    "error.409.course_not_draft": "Solo se puede eliminar un curso en borrador",
    "error.409.course_not_published": "Este curso no está abierto a inscripciones",
    "error.409.course_transition_invalid": "El curso no puede pasar de {from} a {to}",
    "error.409.enrollment_transition_invalid": "La inscripción no puede pasar de {from} a {to}",
    "error.409.quiz_attempts_exhausted": "No quedan intentos (como máximo {max})",
    "error.409.quiz_empty": "Este cuestionario todavía no tiene preguntas",
    "error.503.entitlement_unavailable": "Ahora no se puede comprobar tu plan; inténtalo de nuevo en breve",
}

_MACHINE = {"ru": _MACHINE_RU, "es": _MACHINE_ES}


class _DictTranslator:
    """Offline translator seam — returns fixed machine translations by key."""

    def __init__(self, table):
        self._table = table

    def translate(self, entries, source_language, target_language):
        return {k: self._table[k] for k in entries if k in self._table}


def _regen(lang: str):
    return translate_catalog(
        "errors", lang, TRANSLATIONS,
        source_texts=source_texts("errors"),
        llm=True,
        translator=_DictTranslator(_MACHINE[lang]),
    )


def _owned() -> dict[str, str]:
    from stapel_core.i18n import owned_keys, source_owners

    return owned_keys(source_texts("errors"), source_owners("errors"), THIS_PACKAGE)


def test_regen():
    """Regenerate (env-gated) or assert every catalog is a no-op regen (drift)."""
    if os.environ.get("STAPEL_REGEN_ERROR_I18N"):
        for lang in TARGET_LANGUAGES:
            result = _regen(lang)
            assert not result.missing, f"{lang}: still missing: {result.missing}"
        for lang in LANGUAGES:
            call_command("generate_error_docs", "--lang", lang,
                         "--out", str(DOCS), "--translations", str(TRANSLATIONS),
                         stdout=io.StringIO())
        return

    for lang in TARGET_LANGUAGES:
        path = TRANSLATIONS / f"errors.{lang}.json"
        before = path.read_bytes()
        _regen(lang)
        assert path.read_bytes() == before, (
            f"errors.{lang}.json drifted — run "
            f"STAPEL_REGEN_ERROR_I18N=1 pytest tests/test_error_i18n.py::test_regen"
        )


def test_catalog_gate_green():
    """Missing / stale / params / byte-stability / foreign: all zero."""
    issues = check_translation_catalogs(
        "errors", TRANSLATIONS,
        source_texts=source_texts("errors"),
        languages=LANGUAGES,
        owner=THIS_PACKAGE,
    )
    errors, _warnings = summarize(issues)
    blocking = [i for i in issues if i.level == "error"]
    assert not blocking, "\n".join(f"[{i.code}/{i.language}] {i.message}" for i in blocking)
    assert errors == 0


def test_every_language_covers_every_code_in_errors_py():
    from stapel_courses.errors import STAPEL_COURSES_ERRORS

    owned = _owned()
    assert set(owned) == set(STAPEL_COURSES_ERRORS), (
        "the loader does not attribute this module's registry to it"
    )
    for lang in TARGET_LANGUAGES:
        catalog = load_catalog_file(TRANSLATIONS / f"errors.{lang}.json")
        missing = sorted(set(STAPEL_COURSES_ERRORS) - set(catalog))
        assert not missing, f"{lang} catalog misses {missing}"
        empty = sorted(k for k, v in catalog.items() if not str(v).strip())
        assert not empty, f"{lang}: empty translation(s): {empty}"


@pytest.mark.parametrize("lang", TARGET_LANGUAGES)
def test_the_catalog_carries_nothing_but_owned_keys(lang):
    stray = sorted(set(load_catalog_file(TRANSLATIONS / f"errors.{lang}.json")) - set(_owned()))
    assert not stray, f"{lang}: not this module's keys: {stray}"


@pytest.mark.parametrize("lang", TARGET_LANGUAGES)
def test_translations_preserve_placeholders(lang):
    from stapel_core.i18n.domains import params_of

    canon = _owned()
    for key, text in load_catalog_file(TRANSLATIONS / f"errors.{lang}.json").items():
        assert set(params_of(text)) == set(params_of(canon[key])), f"{lang}: {key}"


def test_the_shipped_language_set_is_exactly_the_gated_one():
    shipped = {p.name for p in TRANSLATIONS.glob("errors.*.json")}
    assert shipped == {f"errors.{lang}.json" for lang in TARGET_LANGUAGES}


def test_error_reference_matches_a_fresh_regeneration(tmp_path):
    for lang in LANGUAGES:
        call_command("generate_error_docs", "--lang", lang, "--out", str(tmp_path),
                     "--translations", str(TRANSLATIONS), stdout=io.StringIO())
        assert (tmp_path / f"errors.{lang}.md").read_bytes() == \
            (DOCS / f"errors.{lang}.md").read_bytes(), (
                f"docs/errors.{lang}.md is stale — run "
                f"STAPEL_REGEN_ERROR_I18N=1 pytest tests/test_error_i18n.py::test_regen"
            )


def test_error_reference_has_no_en_fallback_rows():
    for lang in TARGET_LANGUAGES:
        assert "_(en)_" not in (DOCS / f"errors.{lang}.md").read_text(), (
            f"{lang} error reference has en-fallback rows — the catalog is incomplete"
        )


def test_the_wheel_ships_the_catalogue():
    """package-data must carry ``translations/*.json``, or no host reads it."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        patterns = tomllib.load(handle)["tool"]["setuptools"]["package-data"]
    assert "translations/*.json" in patterns[THIS_PACKAGE]
