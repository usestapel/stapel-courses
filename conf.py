"""Settings namespace for stapel-courses.

All configuration is read through ``courses_settings`` (lazily, at call
time). Resolution order per key: ``settings.STAPEL_COURSES`` dict -> flat
Django setting of the same name -> environment variable -> default below.

Registries merge over built-ins (``ACCESS_STRATEGIES``, ``BLOCK_TYPES``:
``{name: dotted path | None}``, ``None`` removes a built-in, a dotted path
under a built-in name replaces it). Single-key strategies replace
(``COMPLETION_RULE``, ``HOLDER_NAME_RESOLVER``).
"""
from stapel_core.conf import AppSettings

#: The fields a public certificate verification may reveal.
CERTIFICATE_FIELDS = ("holder_name", "course_title", "course_slug", "issued_at")

DRIP_MODES = ("none", "days", "date")
AUTHORING_MODES = ("staff", "members")
PURCHASE_ACTIVATION_MODES = ("paid", "confirmed", "placed")

#: AppSettings-shaped literal dict: a top-level DEFAULTS lets the
#: capabilities.json emitter introspect axis keys/kinds.
DEFAULTS = {
    # {name: "dotted.path.Strategy" | None}, merged over the built-ins
    # free / enrolled / purchased / entitlement (access.py).
    "ACCESS_STRATEGIES": {},
    # Axis: the access strategy a new course starts with.
    "DEFAULT_ACCESS": "enrolled",
    # Axis: the drip mode a new course starts with (none | days | date).
    "DEFAULT_DRIP": "none",
    # Axis: does a new course unlock lessons strictly in order?
    "DEFAULT_SEQUENTIAL": False,
    # Axis: who may create courses (staff | members). Authors edit their own.
    "AUTHORING": "staff",
    # Axis: may a guest (anonymous account) enroll, write progress, take quizzes?
    "ENROLLMENT_REQUIRES_ACCOUNT": True,
    # The purchasable type the orders facts carry for a course.
    "PURCHASABLE_TYPE": "course",
    # Axis: which order fact activates a purchased enrollment
    # (paid | confirmed | placed).
    "PURCHASE_ACTIVATION": "paid",
    # The entitlement Function (stapel-billing contract) and the key it is asked.
    "ENTITLEMENT_FUNCTION": "billing.check_entitlement",
    "ENTITLEMENT_KEY_TEMPLATE": "course:{slug}",
    "ENTITLEMENT_CACHE_SECONDS": 300,
    # {block type: "dotted.path.validator" | None}, merged over text / video /
    # attachment / embed (blocks.py).
    "BLOCK_TYPES": {},
    # Hosts an embed block may point at; empty = any https host.
    "EMBED_HOSTS": [],
    "DEFAULT_PASS_MARK": 70,
    "DEFAULT_MAX_ATTEMPTS": 3,
    # (enrollment) -> bool. Default: every required lesson completed and
    # every required quiz passed, with at least one required item.
    "COMPLETION_RULE": "stapel_courses.services.progress.default_completion_rule",
    # Axis: issue a certificate when a course is completed.
    "CERTIFICATES": True,
    "PUBLIC_VERIFY_FIELDS": ["course_title", "issued_at"],
    "CERTIFICATE_NUMBER_PREFIX": "CERT",
    # (user_id: str) -> str, the name printed on a certificate.
    "HOLDER_NAME_RESOLVER": "stapel_courses.services.certificates.default_holder_name",
    # Best-effort notifications (courses.enrollment_activated,
    # courses.completed, courses.certificate_issued).
    "NOTIFY": True,
    # "{slug}" / "{course_id}" link templates for notifications; empty = no link.
    "COURSE_URL_TEMPLATE": "",
    "CERTIFICATE_URL_TEMPLATE": "",
}

courses_settings = AppSettings(
    "STAPEL_COURSES",
    defaults=DEFAULTS,
    import_strings=("COMPLETION_RULE", "HOLDER_NAME_RESOLVER"),
)

__all__ = [
    "courses_settings",
    "DEFAULTS",
    "CERTIFICATE_FIELDS",
    "DRIP_MODES",
    "AUTHORING_MODES",
    "PURCHASE_ACTIVATION_MODES",
]
