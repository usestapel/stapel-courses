"""Package-level public API (PEP 562 lazy exports) and import hygiene."""
import os
import subprocess
import sys

import stapel_courses


class TestLazyExports:
    def test_all_declares_public_api(self):
        assert stapel_courses.__all__ == [
            "courses_settings",
        ]

    def test_settings_resolve(self):
        from stapel_courses.conf import courses_settings

        assert stapel_courses.courses_settings is courses_settings

    def test_unknown_attribute_raises(self):
        try:
            stapel_courses.nonexistent_export
        except AttributeError as exc:
            assert "nonexistent_export" in str(exc)
        else:
            raise AssertionError("expected AttributeError")


class TestImportWithoutDjangoSettings:
    def test_package_import_is_django_free(self):
        """`import stapel_courses` must not import Django nor require settings."""
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
        code = (
            "import sys\n"
            "import stapel_courses\n"
            'polluted = [m for m in sys.modules if m == "django" or m.startswith("django.")]\n'
            'assert not polluted, f"django imported at package import time: {polluted}"\n'
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.path.dirname(sys.executable),
        )
        assert result.returncode == 0, result.stderr
