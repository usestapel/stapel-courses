"""System checks, each with the case that must fire and the one that must not,
with and without the orders / billing neighbours present."""
import pytest
from django.core import checks as dj_checks
from django.core.management import call_command

from stapel_courses import checks as c

from .factories import FakeFunction


def ids(findings):
    return [f.id for f in findings]


def all_courses_findings():
    return [f for f in dj_checks.run_checks() if (f.id or "").startswith("stapel_courses.")]


@pytest.mark.django_db
def test_defaults_are_silent_without_neighbours():
    assert all_courses_findings() == []


@pytest.mark.django_db
def test_defaults_are_silent_with_neighbours():
    orders = FakeFunction("orders.order.status", {}).install()
    billing = FakeFunction("billing.check_entitlement", {"allowed": True}).install()
    try:
        assert all_courses_findings() == []
    finally:
        orders.uninstall()
        billing.uninstall()


@pytest.mark.django_db
def test_manage_check_passes_at_error_level():
    call_command("check", "--fail-level", "ERROR", "--tag", "compatibility")


class TestStrategies:
    def test_unimportable_is_e001(self, settings):
        settings.STAPEL_COURSES = {"ACCESS_STRATEGIES": {"vip": "nowhere.Strategy"}}
        assert ids(c.check_access_strategies(None)) == ["stapel_courses.E001"]

    def test_not_a_strategy_is_e001(self, settings):
        settings.STAPEL_COURSES = {"ACCESS_STRATEGIES": {"vip": "stapel_courses.blocks.text_block"}}
        assert ids(c.check_access_strategies(None)) == ["stapel_courses.E001"]

    def test_not_a_dict_is_e001(self, settings):
        settings.STAPEL_COURSES = {"ACCESS_STRATEGIES": ["vip"]}
        assert ids(c.check_access_strategies(None)) == ["stapel_courses.E001"]

    def test_unknown_default_is_e002(self, settings):
        settings.STAPEL_COURSES = {"DEFAULT_ACCESS": "vip"}
        assert ids(c.check_access_strategies(None)) == ["stapel_courses.E002"]

    def test_entitlement_default_without_billing_is_w001(self, settings):
        settings.STAPEL_COURSES = {"DEFAULT_ACCESS": "entitlement"}
        findings = c.check_access_strategies(None)
        assert ids(findings) == ["stapel_courses.W001"] and isinstance(findings[0], dj_checks.Warning)

    def test_entitlement_default_with_billing_is_silent(self, settings, billing):
        settings.STAPEL_COURSES = {"DEFAULT_ACCESS": "entitlement"}
        assert c.check_access_strategies(None) == []


def test_unknown_certificate_field_is_e003(settings):
    settings.STAPEL_COURSES = {"PUBLIC_VERIFY_FIELDS": ["email"]}
    assert ids(c.check_certificate_fields(None)) == ["stapel_courses.E003"]


def test_unimportable_block_type_is_e004(settings):
    settings.STAPEL_COURSES = {"BLOCK_TYPES": {"quiz": "nowhere.validate"}}
    assert ids(c.check_block_types(None)) == ["stapel_courses.E004"]


def test_enum_out_of_vocabulary_is_e005(settings):
    settings.STAPEL_COURSES = {"DEFAULT_DRIP": "weekly", "AUTHORING": "anyone"}
    assert ids(c.check_enums(None)) == ["stapel_courses.E005", "stapel_courses.E005"]


def test_unimportable_rule_is_e006(settings):
    settings.STAPEL_COURSES = {"COMPLETION_RULE": "nowhere.rule"}
    assert ids(c.check_dotted_paths(None)) == ["stapel_courses.E006"]
