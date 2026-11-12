from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create and publish a small demo course (idempotent on its slug)."

    def add_arguments(self, parser):
        parser.add_argument("--author", default="demo-author", help="author_id of the demo course")
        parser.add_argument("--access", default="enrolled", help="access strategy name")

    def handle(self, *args, **options):
        from stapel_courses.seed import seed_demo_course

        course, created = seed_demo_course(options["author"], access=options["access"])
        state = "created" if created else "already present"
        self.stdout.write(f"demo course {course.slug!r} {state}")
