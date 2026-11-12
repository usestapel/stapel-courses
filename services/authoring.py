"""Authoring: courses, modules, lessons, quizzes and questions (staff/author API).

Who edits: staff, and the course's author (``Course.author_id``). Who
creates: staff, or any signed-in account when ``AUTHORING = "members"``. A
course the caller may not edit answers the same 404 as an absent one.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from .. import fsm
from ..access import strategy_names
from ..blocks import BlockInvalid, clean_blocks
from ..errors import (
    ERR_400_ACCESS_UNKNOWN,
    ERR_400_BLOCK_INVALID,
    ERR_400_COURSE_PRICE_REQUIRED,
    ERR_400_QUESTION_INVALID,
    ERR_400_QUIZ_TARGET_INVALID,
    ERR_400_SLUG_FROZEN,
    ERR_400_SLUG_TAKEN,
    ERR_403_AUTHORING_FORBIDDEN,
    ERR_404_CERTIFICATE_NOT_FOUND,
    ERR_404_COURSE_NOT_FOUND,
    ERR_404_LESSON_NOT_FOUND,
    ERR_404_MODULE_NOT_FOUND,
    ERR_404_QUESTION_NOT_FOUND,
    ERR_404_QUIZ_NOT_FOUND,
    ERR_409_COURSE_NOT_DRAFT,
    ERR_409_COURSE_TRANSITION_INVALID,
)
from ..models import (
    MAX_ACCEPTED_ANSWERS,
    Certificate,
    MAX_CHOICES,
    Course,
    CourseStatus,
    Lesson,
    Module,
    Question,
    QuestionKind,
    Quiz,
)
from . import CoursesError, is_guest, is_staff, user_id_of

COURSE_FIELDS = (
    "slug", "title", "summary", "description", "cover_media_id", "level", "language", "access",
    "price", "currency", "entitlement_key", "drip", "sequential", "access_days",
    "certificate_enabled", "scope",
)
MODULE_FIELDS = ("title", "position")
LESSON_FIELDS = (
    "title", "position", "blocks", "duration_seconds", "free_preview", "required",
    "review_required", "unlock_after_days", "unlock_at",
)
QUIZ_FIELDS = (
    "title", "pass_mark", "max_attempts", "shuffle_questions", "shuffle_choices", "required",
    "reveal",
)
QUESTION_FIELDS = ("kind", "prompt", "position", "points", "choices", "correct", "match", "explanation")


def _author_id(user) -> str:
    user_id = user_id_of(user)
    if user_id is None or is_guest(user):
        raise CoursesError(403, ERR_403_AUTHORING_FORBIDDEN)
    return user_id


def can_create(user) -> bool:
    from ..conf import courses_settings

    if is_staff(user):
        return True
    return (
        courses_settings.AUTHORING == "members"
        and user_id_of(user) is not None and not is_guest(user)
    )


def editable_courses(user):
    if is_staff(user):
        return Course.objects.all()
    return Course.objects.filter(author_id=_author_id(user))


def editable_course(user, course_id) -> Course:
    course = editable_courses(user).filter(pk=course_id).first()
    if course is None:
        raise CoursesError(404, ERR_404_COURSE_NOT_FOUND)
    return course


def _check_course(course: Course) -> None:
    if course.access not in strategy_names():
        raise CoursesError(400, ERR_400_ACCESS_UNKNOWN, {"access": course.access})
    if course.access == "purchased" and (course.price is None or not course.currency):
        raise CoursesError(400, ERR_400_COURSE_PRICE_REQUIRED)
    course.currency = (course.currency or "").upper()


def _save_course(course: Course) -> Course:
    try:
        with transaction.atomic():
            course.save()
    except IntegrityError:
        raise CoursesError(400, ERR_400_SLUG_TAKEN, {"slug": course.slug}) from None
    return course


def create_course(user, data: dict) -> Course:
    from ..conf import courses_settings

    if not can_create(user):
        raise CoursesError(403, ERR_403_AUTHORING_FORBIDDEN)
    author_id = str(data.get("author_id") or "") if is_staff(user) else ""
    course = Course(
        author_id=author_id or _author_id(user),
        access=courses_settings.DEFAULT_ACCESS,
        drip=courses_settings.DEFAULT_DRIP,
        sequential=bool(courses_settings.DEFAULT_SEQUENTIAL),
    )
    for name in COURSE_FIELDS:
        if name in data:
            setattr(course, name, data[name])
    _check_course(course)
    return _save_course(course)


def update_course(user, course_id, data: dict) -> Course:
    course = editable_course(user, course_id)
    if "slug" in data and data["slug"] != course.slug and course.status != CourseStatus.DRAFT:
        raise CoursesError(400, ERR_400_SLUG_FROZEN)
    for name in COURSE_FIELDS:
        if name in data:
            setattr(course, name, data[name])
    if is_staff(user) and data.get("author_id"):
        course.author_id = str(data["author_id"])
    _check_course(course)
    return _save_course(course)


def delete_course(user, course_id) -> None:
    course = editable_course(user, course_id)
    if course.status != CourseStatus.DRAFT or course.enrollments.exists():
        raise CoursesError(409, ERR_409_COURSE_NOT_DRAFT)
    course.delete()


def move_course(user, course_id, to_status: str) -> Course:
    course = editable_course(user, course_id)
    if not fsm.course_allowed(course.status, to_status):
        raise CoursesError(
            409, ERR_409_COURSE_TRANSITION_INVALID, {"from": course.status, "to": to_status}
        )
    course.status = to_status
    if to_status == CourseStatus.PUBLISHED and course.published_at is None:
        course.published_at = timezone.now()
    course.save(update_fields=["status", "published_at", "updated_at"])
    return course


# ── modules and lessons ───────────────────────────────────────────────────


def _assign(obj, data: dict, fields) -> None:
    for name in fields:
        if name in data:
            setattr(obj, name, data[name])


def create_module(user, course_id, data: dict) -> Module:
    course = editable_course(user, course_id)
    module = Module(course=course)
    _assign(module, data, MODULE_FIELDS)
    module.save()
    return module


def editable_module(user, module_id) -> Module:
    module = Module.objects.filter(pk=module_id, course__in=editable_courses(user)).first()
    if module is None:
        raise CoursesError(404, ERR_404_MODULE_NOT_FOUND)
    return module


def update_module(user, module_id, data: dict) -> Module:
    module = editable_module(user, module_id)
    _assign(module, data, MODULE_FIELDS)
    module.save()
    return module


def delete_module(user, module_id) -> None:
    editable_module(user, module_id).delete()


def _clean_lesson(data: dict) -> dict:
    if "blocks" in data:
        try:
            data = {**data, "blocks": clean_blocks(data["blocks"])}
        except BlockInvalid as exc:
            raise CoursesError(
                400, ERR_400_BLOCK_INVALID, {"index": getattr(exc, "index", None), "reason": exc.reason}
            ) from None
    return data


def create_lesson(user, module_id, data: dict) -> Lesson:
    module = editable_module(user, module_id)
    lesson = Lesson(module=module, course_id=module.course_id)
    _assign(lesson, _clean_lesson(data), LESSON_FIELDS)
    lesson.save()
    return lesson


def editable_lesson(user, lesson_id) -> Lesson:
    lesson = Lesson.objects.filter(pk=lesson_id, course__in=editable_courses(user)).first()
    if lesson is None:
        raise CoursesError(404, ERR_404_LESSON_NOT_FOUND)
    return lesson


def update_lesson(user, lesson_id, data: dict) -> Lesson:
    lesson = editable_lesson(user, lesson_id)
    if "module_id" in data and data["module_id"] != lesson.module_id:
        lesson.module = editable_module(user, data["module_id"])
        if lesson.module.course_id != lesson.course_id:
            raise CoursesError(404, ERR_404_MODULE_NOT_FOUND)
    _assign(lesson, _clean_lesson(data), LESSON_FIELDS)
    lesson.save()
    return lesson


def delete_lesson(user, lesson_id) -> None:
    editable_lesson(user, lesson_id).delete()


# ── quizzes and questions ─────────────────────────────────────────────────


def create_quiz(user, data: dict) -> Quiz:
    from ..conf import courses_settings

    lesson_id, module_id = data.get("lesson_id"), data.get("module_id")
    if bool(lesson_id) == bool(module_id):
        raise CoursesError(400, ERR_400_QUIZ_TARGET_INVALID)
    if lesson_id:
        lesson = editable_lesson(user, lesson_id)
        quiz = Quiz(course_id=lesson.course_id, lesson=lesson)
    else:
        module = editable_module(user, module_id)
        quiz = Quiz(course_id=module.course_id, module=module)
    quiz.pass_mark = int(courses_settings.DEFAULT_PASS_MARK)
    quiz.max_attempts = int(courses_settings.DEFAULT_MAX_ATTEMPTS)
    _assign(quiz, data, QUIZ_FIELDS)
    quiz.save()
    return quiz


def editable_quiz(user, quiz_id) -> Quiz:
    quiz = Quiz.objects.filter(pk=quiz_id, course__in=editable_courses(user)).first()
    if quiz is None:
        raise CoursesError(404, ERR_404_QUIZ_NOT_FOUND)
    return quiz


def update_quiz(user, quiz_id, data: dict) -> Quiz:
    quiz = editable_quiz(user, quiz_id)
    _assign(quiz, data, QUIZ_FIELDS)
    quiz.save()
    return quiz


def delete_quiz(user, quiz_id) -> None:
    editable_quiz(user, quiz_id).delete()


def _invalid(reason: str) -> CoursesError:
    return CoursesError(400, ERR_400_QUESTION_INVALID, {"reason": reason})


def check_question(question: Question) -> None:
    """The kind decides the shape of ``choices`` and ``correct``."""
    kind = question.kind
    choices = question.choices or []
    if kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE):
        if not isinstance(choices, list) or not 2 <= len(choices) <= MAX_CHOICES:
            raise _invalid("choices_count")
        ids = [c.get("id") for c in choices if isinstance(c, dict)]
        if len(ids) != len(choices) or len(set(ids)) != len(ids) or not all(ids):
            raise _invalid("choice_ids")
        correct = question.correct
        if not isinstance(correct, list) or not correct or not set(correct) <= set(ids):
            raise _invalid("correct_not_in_choices")
        if len(set(correct)) != len(correct):
            raise _invalid("correct_duplicates")
        if kind == QuestionKind.SINGLE and len(correct) != 1:
            raise _invalid("single_needs_one")
    elif kind == QuestionKind.TRUE_FALSE:
        if not isinstance(question.correct, bool):
            raise _invalid("true_false_needs_bool")
        question.choices = []
    elif kind == QuestionKind.SHORT_TEXT:
        accepted = question.correct
        if (not isinstance(accepted, list) or not 1 <= len(accepted) <= MAX_ACCEPTED_ANSWERS
                or not all(isinstance(a, str) and a.strip() for a in accepted)):
            raise _invalid("accepted_answers")
        question.choices = []
    else:
        raise _invalid("kind_unknown")


def create_question(user, quiz_id, data: dict) -> Question:
    quiz = editable_quiz(user, quiz_id)
    question = Question(quiz=quiz)
    _assign(question, data, QUESTION_FIELDS)
    check_question(question)
    question.save()
    return question


def editable_question(user, question_id) -> Question:
    question = Question.objects.filter(
        pk=question_id, quiz__course__in=editable_courses(user)
    ).first()
    if question is None:
        raise CoursesError(404, ERR_404_QUESTION_NOT_FOUND)
    return question


def update_question(user, question_id, data: dict) -> Question:
    question = editable_question(user, question_id)
    _assign(question, data, QUESTION_FIELDS)
    check_question(question)
    question.save()
    return question


def delete_question(user, question_id) -> None:
    editable_question(user, question_id).delete()


def editable_certificate(user, number: str) -> Certificate:
    certificate = Certificate.objects.select_related("course").filter(
        number=str(number).strip().upper(), course__in=editable_courses(user)
    ).first()
    if certificate is None:
        raise CoursesError(404, ERR_404_CERTIFICATE_NOT_FOUND)
    return certificate
