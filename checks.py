"""Django system checks for stapel-courses.

- E001  an ``ACCESS_STRATEGIES`` entry does not import to an ``AccessStrategy``.
- E002  ``DEFAULT_ACCESS`` names no registered strategy.
- E003  ``PUBLIC_VERIFY_FIELDS`` names a field verification cannot show.
- E004  a ``BLOCK_TYPES`` validator does not import to a callable.
- E005  an enumerated setting is out of its vocabulary
        (``DEFAULT_DRIP``, ``AUTHORING``, ``PURCHASE_ACTIVATION``).
- E006  ``COMPLETION_RULE`` / ``HOLDER_NAME_RESOLVER`` does not import.
- E007  an ``EMBED_HOSTS`` entry is not a bare host name.
- W001  ``DEFAULT_ACCESS = "entitlement"`` and the entitlement Function is not
        reachable here (new courses would answer 503 on enroll).

Neither stapel-orders nor stapel-billing is required: with the defaults
nothing here fires whether they are installed or not.
"""
import re

from django.core import checks
from django.utils.module_loading import import_string

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


@checks.register(checks.Tags.compatibility)
def check_access_strategies(app_configs, **kwargs):
    from .access import AccessStrategy, strategy_paths
    from .conf import courses_settings

    findings = []
    raw = courses_settings.ACCESS_STRATEGIES
    if raw is not None and not isinstance(raw, dict):
        return [checks.Error(
            "STAPEL_COURSES['ACCESS_STRATEGIES'] must be a dict of {name: dotted path | None}.",
            id="stapel_courses.E001",
        )]
    for name, path in sorted(strategy_paths().items()):
        try:
            cls = import_string(path)
        except ImportError as exc:
            findings.append(checks.Error(
                f"Access strategy {name!r}: {path!r} does not import ({exc}).",
                id="stapel_courses.E001",
            ))
            continue
        if not (isinstance(cls, type) and issubclass(cls, AccessStrategy)):
            findings.append(checks.Error(
                f"Access strategy {name!r}: {path!r} is not an AccessStrategy subclass.",
                id="stapel_courses.E001",
            ))
    default = courses_settings.DEFAULT_ACCESS
    if default not in strategy_paths():
        findings.append(checks.Error(
            f"STAPEL_COURSES['DEFAULT_ACCESS'] = {default!r} is not a registered strategy.",
            hint=f"One of {sorted(strategy_paths())}.",
            id="stapel_courses.E002",
        ))
    elif default == "entitlement":
        from stapel_core.comm import function_unreachable_reason

        reason = function_unreachable_reason(courses_settings.ENTITLEMENT_FUNCTION)
        if reason:
            findings.append(checks.Warning(
                f"DEFAULT_ACCESS is 'entitlement' but {courses_settings.ENTITLEMENT_FUNCTION!r} "
                f"is not reachable here ({reason}); enrolling in such a course answers 503.",
                hint="Install stapel-billing (or route the Function), or pick another DEFAULT_ACCESS.",
                id="stapel_courses.W001",
            ))
    return findings


@checks.register(checks.Tags.compatibility)
def check_certificate_fields(app_configs, **kwargs):
    from .conf import CERTIFICATE_FIELDS, courses_settings

    unknown = sorted(set(courses_settings.PUBLIC_VERIFY_FIELDS or ()) - set(CERTIFICATE_FIELDS))
    if unknown:
        return [checks.Error(
            f"STAPEL_COURSES['PUBLIC_VERIFY_FIELDS'] names unknown fields {unknown}.",
            hint=f"Choose from {list(CERTIFICATE_FIELDS)}.",
            id="stapel_courses.E003",
        )]
    return []


@checks.register(checks.Tags.compatibility)
def check_block_types(app_configs, **kwargs):
    from .blocks import block_type_paths

    findings = []
    for name, path in sorted(block_type_paths().items()):
        try:
            fn = import_string(path)
        except ImportError as exc:
            findings.append(checks.Error(
                f"Block type {name!r}: {path!r} does not import ({exc}).", id="stapel_courses.E004",
            ))
            continue
        if not callable(fn):
            findings.append(checks.Error(
                f"Block type {name!r}: {path!r} is not callable.", id="stapel_courses.E004",
            ))
    return findings


@checks.register(checks.Tags.compatibility)
def check_enums(app_configs, **kwargs):
    from .conf import AUTHORING_MODES, DRIP_MODES, PURCHASE_ACTIVATION_MODES, courses_settings

    findings = []
    for key, vocabulary in (
        ("DEFAULT_DRIP", DRIP_MODES),
        ("AUTHORING", AUTHORING_MODES),
        ("PURCHASE_ACTIVATION", PURCHASE_ACTIVATION_MODES),
    ):
        value = getattr(courses_settings, key)
        if value not in vocabulary:
            findings.append(checks.Error(
                f"STAPEL_COURSES[{key!r}] = {value!r} is not one of {list(vocabulary)}.",
                id="stapel_courses.E005",
            ))
    return findings


@checks.register(checks.Tags.compatibility)
def check_dotted_paths(app_configs, **kwargs):
    from .conf import courses_settings

    findings = []
    for key in ("COMPLETION_RULE", "HOLDER_NAME_RESOLVER"):
        try:
            value = getattr(courses_settings, key)
        except ImportError as exc:
            findings.append(checks.Error(
                f"STAPEL_COURSES[{key!r}] does not import ({exc}).", id="stapel_courses.E006",
            ))
            continue
        if not callable(value):
            findings.append(checks.Error(
                f"STAPEL_COURSES[{key!r}] is not callable.", id="stapel_courses.E006",
            ))
    return findings


@checks.register(checks.Tags.compatibility)
def check_embed_hosts(app_configs, **kwargs):
    from .conf import courses_settings

    bad_hosts = [h for h in (courses_settings.EMBED_HOSTS or []) if not _HOST_RE.match(str(h))]
    if bad_hosts:
        return [checks.Error(
            f"STAPEL_COURSES['EMBED_HOSTS'] entries must be bare lowercase host names: {bad_hosts}.",
            hint="Write 'www.youtube.com', not 'https://www.youtube.com/'.", id="stapel_courses.E007")]
    return []
