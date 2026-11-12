"""The access gate: who sees a course, which lessons are open, and why not.

:func:`course_view` evaluates one ``(course, user)`` pair once — strategy,
enrollment, progress and passed quizzes — and computes a lock state for
every lesson and quiz in outline order. The outline, the lesson read, the
progress write and the quiz start all ask the same object, so a lesson the
outline shows as locked is a lesson the content endpoint refuses.

Evaluation order per lesson: privileged (staff / the author) → free preview
→ strategy → drip → sequence.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from django.utils import timezone

from ..access import DRIP, ENROLLMENT_REQUIRED, OPEN, SEQUENTIAL, Decision, get_strategy
from ..errors import (
    ERR_403_LESSON_LOCKED,
    ERR_404_COURSE_NOT_FOUND,
    ERR_404_LESSON_NOT_FOUND,
)
from ..models import (
    AttemptStatus,
    Course,
    CourseStatus,
    DripMode,
    Lesson,
    LessonProgress,
    Module,
    ProgressStatus,
    Quiz,
)
from . import CoursesError, is_staff, user_id_of


@dataclass
class ItemState:
    locked: bool = False
    reason: Optional[str] = None
    unlocks_at: Optional[dt.datetime] = None
    after_lesson_id: Optional[int] = None
    after_quiz_id: Optional[int] = None

    def params(self) -> dict:
        params = {"reason": self.reason}
        if self.unlocks_at is not None:
            params["unlocks_at"] = self.unlocks_at.isoformat()
        if self.after_lesson_id is not None:
            params["after_lesson_id"] = self.after_lesson_id
        if self.after_quiz_id is not None:
            params["after_quiz_id"] = self.after_quiz_id
        return params


@dataclass
class CourseView:
    course: Course
    user_id: Optional[str]
    enrollment: object
    privileged: bool
    decision: Decision
    modules: list = field(default_factory=list)
    lessons_by_module: dict = field(default_factory=dict)
    quizzes_by_lesson: dict = field(default_factory=dict)
    quizzes_by_module: dict = field(default_factory=dict)
    progress: dict = field(default_factory=dict)
    passed_quizzes: set = field(default_factory=set)
    lesson_states: dict = field(default_factory=dict)
    quiz_states: dict = field(default_factory=dict)

    def ordered_lessons(self) -> list:
        return [lesson for module in self.modules for lesson in self.lessons_by_module.get(module.pk, [])]

    def lesson_status(self, lesson_id: int) -> Optional[str]:
        return self.progress.get(lesson_id)


def is_privileged(user, course: Course) -> bool:
    user_id = user_id_of(user)
    return is_staff(user) or (user_id is not None and user_id == course.author_id)


def visible_course(slug: str, user) -> Course:
    """A course the caller may open: published; archived for its learners;
    a draft for its author and staff. Anything else is the same 404."""
    from .enrollments import find

    course = Course.objects.filter(slug=slug).first()
    if course is None:
        raise CoursesError(404, ERR_404_COURSE_NOT_FOUND)
    if course.status == CourseStatus.PUBLISHED or is_privileged(user, course):
        return course
    if course.status == CourseStatus.ARCHIVED and find(course, user_id_of(user)) is not None:
        return course
    raise CoursesError(404, ERR_404_COURSE_NOT_FOUND)


def course_view(course: Course, user, now: dt.datetime | None = None) -> CourseView:
    from .enrollments import find

    now = now or timezone.now()
    user_id = user_id_of(user)
    enrollment = find(course, user_id)
    privileged = is_privileged(user, course)
    decision = OPEN if privileged else get_strategy(course.access).content_access(
        course, user_id, enrollment
    )
    view = CourseView(course, user_id, enrollment, privileged, decision)
    view.modules = list(Module.objects.filter(course=course))
    for lesson in Lesson.objects.filter(course=course):
        view.lessons_by_module.setdefault(lesson.module_id, []).append(lesson)
    for quiz in Quiz.objects.filter(course=course):
        if quiz.lesson_id:
            view.quizzes_by_lesson.setdefault(quiz.lesson_id, []).append(quiz)
        else:
            view.quizzes_by_module.setdefault(quiz.module_id, []).append(quiz)
    if user_id:
        view.progress = dict(
            LessonProgress.objects.filter(course=course, user_id=user_id)
            .values_list("lesson_id", "status")
        )
        view.passed_quizzes = set(
            Quiz.objects.filter(
                course=course, attempts__user_id=user_id, attempts__passed=True,
                attempts__status=AttemptStatus.SUBMITTED,
            ).values_list("id", flat=True)
        )
    _compute_states(view, now)
    return view


def _drip_state(view: CourseView, lesson: Lesson, now: dt.datetime) -> Optional[ItemState]:
    course = view.course
    if course.drip == DripMode.DAYS and lesson.unlock_after_days:
        activated = getattr(view.enrollment, "activated_at", None)
        if activated is None:
            return ItemState(True, ENROLLMENT_REQUIRED)
        unlocks = activated + dt.timedelta(days=int(lesson.unlock_after_days))
        if now < unlocks:
            return ItemState(True, DRIP, unlocks_at=unlocks)
    if course.drip == DripMode.DATE and lesson.unlock_at is not None and now < lesson.unlock_at:
        return ItemState(True, DRIP, unlocks_at=lesson.unlock_at)
    return None


def _compute_states(view: CourseView, now: dt.datetime) -> None:
    blocker: Optional[ItemState] = None
    sequential = view.course.sequential

    def quiz_blocker(quiz) -> Optional[ItemState]:
        if quiz.required and quiz.pk not in view.passed_quizzes:
            return ItemState(True, SEQUENTIAL, after_quiz_id=quiz.pk)
        return None

    for module in view.modules:
        for lesson in view.lessons_by_module.get(module.pk, []):
            state = _lesson_state(view, lesson, blocker if sequential else None, now)
            view.lesson_states[lesson.pk] = state
            for quiz in view.quizzes_by_lesson.get(lesson.pk, []):
                if not state.locked and not view.privileged and not view.decision.allowed:
                    # A free-preview lesson's quiz still needs the course.
                    view.quiz_states[quiz.pk] = ItemState(True, view.decision.reason)
                else:
                    view.quiz_states[quiz.pk] = state
            if blocker is None:
                if lesson.required and view.progress.get(lesson.pk) != ProgressStatus.COMPLETED:
                    blocker = ItemState(True, SEQUENTIAL, after_lesson_id=lesson.pk)
                else:
                    for quiz in view.quizzes_by_lesson.get(lesson.pk, []):
                        blocker = blocker or quiz_blocker(quiz)
        for quiz in view.quizzes_by_module.get(module.pk, []):
            if view.privileged:
                view.quiz_states[quiz.pk] = ItemState()
            elif not view.decision.allowed:
                view.quiz_states[quiz.pk] = ItemState(True, view.decision.reason)
            elif sequential and blocker is not None:
                view.quiz_states[quiz.pk] = ItemState(
                    True, SEQUENTIAL, after_lesson_id=blocker.after_lesson_id,
                    after_quiz_id=blocker.after_quiz_id,
                )
            else:
                view.quiz_states[quiz.pk] = ItemState()
        if blocker is None:
            for quiz in view.quizzes_by_module.get(module.pk, []):
                blocker = blocker or quiz_blocker(quiz)


def _lesson_state(view: CourseView, lesson: Lesson, blocker: Optional[ItemState],
                  now: dt.datetime) -> ItemState:
    if view.privileged or lesson.free_preview:
        return ItemState()
    if not view.decision.allowed:
        return ItemState(True, view.decision.reason)
    drip = _drip_state(view, lesson, now)
    if drip is not None:
        return drip
    if blocker is not None:
        return ItemState(
            True, SEQUENTIAL, after_lesson_id=blocker.after_lesson_id,
            after_quiz_id=blocker.after_quiz_id,
        )
    return ItemState()


def require_lesson(view: CourseView, lesson_id) -> Lesson:
    """The open lesson, or 404 (not in this course) / 403 ``lesson_locked``."""
    lesson = next((item for item in view.ordered_lessons() if item.pk == int(lesson_id)), None)
    if lesson is None:
        raise CoursesError(404, ERR_404_LESSON_NOT_FOUND)
    state = view.lesson_states[lesson.pk]
    if state.locked:
        raise CoursesError(403, ERR_403_LESSON_LOCKED, state.params())
    return lesson
