"""Small builders for courses, lessons and quizzes."""
from __future__ import annotations

from django.utils import timezone

from stapel_courses.models import Course, CourseStatus, Lesson, Module, Question, Quiz

V1 = "/courses/api/v1"

_counter = {"n": 0}


def _next() -> int:
    _counter["n"] += 1
    return _counter["n"]


def make_course(author=None, *, access="enrolled", status=CourseStatus.PUBLISHED, slug=None,
                **fields) -> Course:
    author_id = str(getattr(author, "pk", author or "author-1"))
    return Course.objects.create(
        slug=slug or f"course-{_next()}", title=fields.pop("title", "A course"),
        author_id=author_id, access=access, status=status,
        published_at=timezone.now() if status == CourseStatus.PUBLISHED else None, **fields,
    )


def make_module(course, position=1, title="Module") -> Module:
    return Module.objects.create(course=course, title=title, position=position)


def make_lesson(module, position=1, **fields) -> Lesson:
    fields.setdefault("blocks", [{"type": "text", "format": "markdown", "text": f"secret body {position}"}])
    return Lesson.objects.create(
        module=module, course=module.course, title=fields.pop("title", f"Lesson {position}"),
        position=position, **fields,
    )


def make_quiz(target, **fields) -> Quiz:
    if isinstance(target, Lesson):
        return Quiz.objects.create(course=target.course, lesson=target, title="Quiz", **fields)
    return Quiz.objects.create(course=target.course, module=target, title="Quiz", **fields)


def single(quiz, position=1, correct="b", points=1) -> Question:
    return Question.objects.create(
        quiz=quiz, kind="single", position=position, points=points, prompt=f"Pick one {position}",
        choices=[{"id": "a", "text": "Alpha"}, {"id": "b", "text": "Bravo"}, {"id": "c", "text": "Charlie"}],
        correct=[correct], explanation="Because bravo.",
    )


def multiple(quiz, position=2, correct=("a", "c")) -> Question:
    return Question.objects.create(
        quiz=quiz, kind="multiple", position=position, prompt="Pick some",
        choices=[{"id": "a", "text": "One"}, {"id": "b", "text": "Two"}, {"id": "c", "text": "Three"}],
        correct=list(correct),
    )


def true_false(quiz, position=3, correct=True) -> Question:
    return Question.objects.create(quiz=quiz, kind="true_false", position=position,
                                   prompt="True?", correct=correct)


def short_text(quiz, position=4, accepted=("Mount Everest",), match="normalised") -> Question:
    return Question.objects.create(quiz=quiz, kind="short_text", position=position,
                                   prompt="Highest mountain?", correct=list(accepted), match=match)


def simple_course(author=None, *, lessons=2, access="enrolled", **fields):
    """One module, *lessons* lessons; returns ``(course, module, [lessons])``."""
    course = make_course(author, access=access, **fields)
    module = make_module(course)
    return course, module, [make_lesson(module, position=i + 1) for i in range(lessons)]


class FakeFunction:
    """An in-process comm Function with a call log; ``fail`` makes it raise."""

    def __init__(self, name, answer):
        self.name = name
        self.answer = answer
        self.calls = []
        self.fail = False

    def __call__(self, payload):
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError("provider is down")
        return self.answer(payload) if callable(self.answer) else self.answer

    def install(self):
        from stapel_core.comm.registry import function_registry

        function_registry.register(self.name, self)
        return self

    def uninstall(self):
        from stapel_core.comm.registry import function_registry

        with function_registry._lock:
            function_registry._providers.pop(self.name, None)
            function_registry._schemas.pop(self.name, None)


class Event:
    """The shape a comm handler receives."""

    def __init__(self, payload, event_id="evt-1"):
        self.payload = payload
        self.event_id = event_id
