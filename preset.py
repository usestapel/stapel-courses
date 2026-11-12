"""Settings fragments stapel-courses ships for its neighbours.

``SETTINGS_DEFAULTS["STAPEL_ORDERS"]`` registers the ``course`` purchasable
type with its resolver Function, so installing courses next to stapel-orders
sells a course with no hand edit (the scaffold / Studio merges it)::

    from stapel_courses.preset import SETTINGS_DEFAULTS

    STAPEL_ORDERS = {
        "PURCHASABLE_TYPES": {
            **SETTINGS_DEFAULTS["STAPEL_ORDERS"]["PURCHASABLE_TYPES"],
        },
    }

Courses never imports stapel-orders; this is data, read by whoever composes
the settings.
"""

SETTINGS_DEFAULTS = {
    "STAPEL_ORDERS": {
        "PURCHASABLE_TYPES": {
            "course": {"resolve": "courses.purchasables"},
        },
    },
}

__all__ = ["SETTINGS_DEFAULTS"]
