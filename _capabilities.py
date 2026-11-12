"""stapel-courses capabilities.json emitter — thin shim over stapel_tools.capabilities."""
from pathlib import Path

from stapel_tools.capabilities import axis_group_rules, run_capabilities_cli

#: CTO-facing axes, all behavioural (no endpoint is unmounted).
AXES = {
    "DEFAULT_ACCESS": "courses.access",
    "ENROLLMENT_REQUIRES_ACCOUNT": "courses.access",
    "PURCHASE_ACTIVATION": "courses.purchase",
    "DEFAULT_DRIP": "courses.pacing",
    "DEFAULT_SEQUENTIAL": "courses.pacing",
    "AUTHORING": "courses.authoring",
    "CERTIFICATES": "courses.certificates",
}


def main(argv=None):
    from stapel_courses._codegen import _configure

    _configure()
    from stapel_courses.conf import DEFAULTS
    from stapel_courses.urls import GATE_REGISTRY

    return run_capabilities_cli(
        argv,
        repo=Path(__file__).resolve().parent,
        canonical_prefix="/courses/api/v1",
        defaults=DEFAULTS,
        registry=GATE_REGISTRY,
        is_axis=lambda k: k in AXES,
        axis_group=axis_group_rules(exact=AXES),
        prog="stapel-courses-capabilities",
    )


if __name__ == "__main__":
    raise SystemExit(main())
