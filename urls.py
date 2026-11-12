"""Root URLconf for stapel-courses — v1 canon mount.

The host mounts the module under ``courses/api/``; this module contributes
the ``v1/`` segment:

    path("courses/api/", include("stapel_courses.urls"))   # -> /courses/api/v1/...
"""
from django.urls import include, path

from stapel_courses.urls_v1 import GATE_REGISTRY  # noqa: F401  (re-export)

urlpatterns = [
    path("v1/", include("stapel_courses.urls_v1")),
]
