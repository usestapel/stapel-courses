"""Admin for stapel-courses.

Content (courses, modules, lessons, quizzes, questions) is edited here like
any business model. Enrollments move only through the service (actions),
never by a raw status edit, so every move is checked by the FSM and
announced on the bus. Progress, attempts and the purchase ledger are
read-only journals.
"""
from django.contrib import admin, messages

from .models import (
    Attempt,
    Certificate,
    Course,
    CoursePurchase,
    Enrollment,
    EnrollmentStatus,
    Lesson,
    LessonProgress,
    Module,
    Question,
    Quiz,
)


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ("title", "position")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "status", "access", "level", "author_id", "published_at")
    list_filter = ("status", "access", "level", "drip")
    search_fields = ("slug", "title", "author_id")
    readonly_fields = ("published_at", "created_at", "updated_at")
    inlines = [ModuleInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "module", "position", "free_preview", "required")
    list_filter = ("free_preview", "required", "review_required")
    search_fields = ("title",)


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "lesson", "module", "pass_mark", "max_attempts", "required")
    inlines = [QuestionInline]


def _transition_action(to_status: str):
    def action(modeladmin, request, queryset):
        from .services import CoursesError
        from .services.enrollments import staff_transition

        moved = refused = 0
        for enrollment in queryset:
            try:
                staff_transition(enrollment.pk, to_status, reason="admin")
                moved += 1
            except CoursesError:
                refused += 1
        if moved:
            modeladmin.message_user(request, f"{moved} enrollment(s) moved to {to_status}.")
        if refused:
            modeladmin.message_user(
                request, f"{refused} enrollment(s) cannot move to {to_status}.", messages.WARNING
            )

    action.__name__ = f"mark_{to_status}"
    action.short_description = f"Mark selected enrollments {to_status}"
    return action


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("course", "user_id", "status", "source", "progress_percent", "expires_at")
    list_filter = ("status", "source")
    search_fields = ("user_id", "order_id", "course__slug")
    readonly_fields = tuple(f.name for f in Enrollment._meta.fields)
    actions = [
        _transition_action(EnrollmentStatus.ACTIVE),
        _transition_action(EnrollmentStatus.CANCELLED),
        _transition_action(EnrollmentStatus.EXPIRED),
    ]

    def has_add_permission(self, request):
        return False


class _JournalAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LessonProgress)
class LessonProgressAdmin(_JournalAdmin):
    list_display = ("user_id", "course", "lesson", "status", "position_seconds", "updated_at")
    list_filter = ("status",)
    search_fields = ("user_id",)


@admin.register(Attempt)
class AttemptAdmin(_JournalAdmin):
    list_display = ("user_id", "quiz", "number", "status", "percent", "passed", "submitted_at")
    list_filter = ("status", "passed")
    search_fields = ("user_id",)


@admin.register(CoursePurchase)
class CoursePurchaseAdmin(_JournalAdmin):
    list_display = ("order_id", "course", "user_id", "state", "updated_at")
    list_filter = ("state",)
    search_fields = ("order_id", "user_id")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("number", "course_title", "user_id", "issued_at", "revoked_at")
    search_fields = ("number", "user_id")
    readonly_fields = ("number", "course", "user_id", "holder_name", "course_title", "issued_at")

    def has_add_permission(self, request):
        return False
