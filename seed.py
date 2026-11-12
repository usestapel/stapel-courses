"""A small demo course: two modules, four lessons, one quiz of every kind.

Used by ``manage.py courses_seed_demo`` and by tests. Idempotent on the
slug: an existing demo course is left as it is.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

DEMO_SLUG = "learning-basics"


def seed_demo_course(author_id: str = "demo-author", *, slug: str = DEMO_SLUG, access: str = "enrolled"):
    """Create (once) and publish the demo course. Returns ``(course, created)``."""
    from .models import Course, CourseStatus, Lesson, Module, Question, Quiz

    existing = Course.objects.filter(slug=slug).first()
    if existing is not None:
        return existing, False
    with transaction.atomic():
        course = Course.objects.create(
            slug=slug,
            title="Learning basics",
            summary="A short demo course: read, watch, and check what you learned.",
            description="Two modules with text and video lessons and a final quiz.",
            author_id=str(author_id),
            level="beginner",
            access=access,
            status=CourseStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        first = Module.objects.create(course=course, title="Getting started", position=1)
        second = Module.objects.create(course=course, title="Going further", position=2)
        Lesson.objects.create(
            module=first, course=course, title="Welcome", position=1, free_preview=True,
            duration_seconds=120,
            blocks=[{"type": "text", "format": "markdown",
                     "text": "Welcome! This course shows how lessons, progress and quizzes work."}],
        )
        Lesson.objects.create(
            module=first, course=course, title="How lessons work", position=2, duration_seconds=300,
            blocks=[
                {"type": "text", "format": "markdown", "text": "Each lesson is a list of content blocks."},
                {"type": "video", "media_id": "demo-video-1", "caption": "A short walkthrough"},
            ],
        )
        Lesson.objects.create(
            module=second, course=course, title="Practice", position=1, duration_seconds=600,
            blocks=[
                {"type": "text", "format": "markdown", "text": "Download the worksheet and try it."},
                {"type": "attachment", "media_id": "demo-file-1", "name": "worksheet.pdf"},
            ],
        )
        final = Lesson.objects.create(
            module=second, course=course, title="Wrap-up", position=2, duration_seconds=180,
            blocks=[{"type": "text", "format": "markdown", "text": "Take the final quiz to finish."}],
        )
        quiz = Quiz.objects.create(
            course=course, lesson=final, title="Final quiz", pass_mark=60, max_attempts=3,
            shuffle_choices=True, reveal="after_submit",
        )
        Question.objects.create(
            quiz=quiz, kind="single", position=1, prompt="What is a lesson made of?",
            choices=[{"id": "a", "text": "Content blocks"}, {"id": "b", "text": "Spreadsheets"}],
            correct=["a"], explanation="A lesson is a list of typed content blocks.",
        )
        Question.objects.create(
            quiz=quiz, kind="multiple", position=2, prompt="Which blocks can a lesson hold?",
            choices=[{"id": "a", "text": "Text"}, {"id": "b", "text": "Video"},
                     {"id": "c", "text": "Payment form"}],
            correct=["a", "b"],
        )
        Question.objects.create(
            quiz=quiz, kind="true_false", position=3, prompt="Progress is saved per lesson.",
            correct=True,
        )
        Question.objects.create(
            quiz=quiz, kind="short_text", position=4, prompt="One word: what proves you finished?",
            correct=["certificate"], match="normalised",
        )
    return course, True
