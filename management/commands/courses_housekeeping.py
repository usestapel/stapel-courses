from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Expire enrollments past their expiry (the beat pass, without Celery)."

    def handle(self, *args, **options):
        from stapel_courses.services.enrollments import expire_due

        self.stdout.write(f"expired {expire_due()}")
