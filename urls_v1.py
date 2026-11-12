"""v1 URL set for stapel-courses (plain paths, no router)."""
from typing import NamedTuple

from django.urls import path

from . import views as v

COURSE = "courses/<slug:slug>/"

urlpatterns = [
    path("courses/", v.CatalogView.as_view(), name="courses-catalog"),
    path(COURSE, v.CourseOutlineView.as_view(), name="courses-outline"),
    path(f"{COURSE}enroll/", v.EnrollView.as_view(), name="courses-enroll"),
    path(f"{COURSE}progress/", v.CourseProgressView.as_view(), name="courses-progress"),
    path(f"{COURSE}lessons/<int:lesson_id>/", v.LessonView.as_view(), name="courses-lesson"),
    path(f"{COURSE}lessons/<int:lesson_id>/progress/", v.LessonProgressView.as_view(),
         name="courses-lesson-progress"),
    path("me/enrollments/", v.MyEnrollmentsView.as_view(), name="courses-my-enrollments"),
    path("me/certificates/", v.MyCertificatesView.as_view(), name="courses-my-certificates"),
    path("quizzes/<int:quiz_id>/", v.QuizView.as_view(), name="courses-quiz"),
    path("quizzes/<int:quiz_id>/attempts/", v.QuizAttemptsView.as_view(), name="courses-quiz-attempts"),
    path("attempts/<int:attempt_id>/", v.AttemptView.as_view(), name="courses-attempt"),
    path("attempts/<int:attempt_id>/submit/", v.AttemptSubmitView.as_view(), name="courses-attempt-submit"),
    path("certificates/<str:number>/", v.CertificateVerifyView.as_view(), name="courses-certificate-verify"),
    path("author/access-strategies/", v.AuthorAccessStrategiesView.as_view(),
         name="courses-author-access-strategies"),
    path("author/courses/", v.AuthorCoursesView.as_view(), name="courses-author-courses"),
    path("author/courses/<int:course_id>/", v.AuthorCourseView.as_view(), name="courses-author-course"),
    path("author/courses/<int:course_id>/publish/", v.AuthorCoursePublishView.as_view(),
         name="courses-author-course-publish"),
    path("author/courses/<int:course_id>/archive/", v.AuthorCourseArchiveView.as_view(),
         name="courses-author-course-archive"),
    path("author/courses/<int:course_id>/modules/", v.AuthorModulesView.as_view(),
         name="courses-author-modules"),
    path("author/courses/<int:course_id>/enrollments/", v.AuthorEnrollmentsView.as_view(),
         name="courses-author-enrollments"),
    path("author/courses/<int:course_id>/certificates/", v.AuthorCertificatesView.as_view(),
         name="courses-author-certificates"),
    path("author/modules/<int:module_id>/", v.AuthorModuleView.as_view(), name="courses-author-module"),
    path("author/modules/<int:module_id>/lessons/", v.AuthorLessonsView.as_view(),
         name="courses-author-lessons"),
    path("author/lessons/<int:lesson_id>/", v.AuthorLessonView.as_view(), name="courses-author-lesson"),
    path("author/lessons/<int:lesson_id>/review/", v.AuthorLessonReviewView.as_view(),
         name="courses-author-lesson-review"),
    path("author/reviews/", v.AuthorReviewsView.as_view(), name="courses-author-reviews"),
    path("author/quizzes/", v.AuthorQuizzesView.as_view(), name="courses-author-quizzes"),
    path("author/quizzes/<int:quiz_id>/", v.AuthorQuizView.as_view(), name="courses-author-quiz"),
    path("author/quizzes/<int:quiz_id>/questions/", v.AuthorQuestionsView.as_view(),
         name="courses-author-questions"),
    path("author/questions/<int:question_id>/", v.AuthorQuestionView.as_view(),
         name="courses-author-question"),
    path("author/enrollments/<int:enrollment_id>/transition/", v.AuthorEnrollmentTransitionView.as_view(),
         name="courses-author-enrollment-transition"),
    path("author/certificates/<str:number>/revoke/", v.AuthorCertificateRevokeView.as_view(),
         name="courses-author-certificate-revoke"),
]


class GateEntry(NamedTuple):
    """One gated URL block: which flags gate which url patterns."""

    name: str
    flags: tuple
    patterns: tuple


#: No axis unmounts an endpoint (every axis is behavioural), so the surface
#: is one always-on block.
GATE_REGISTRY: dict = {
    "courses.api": GateEntry("courses.api", (), tuple(urlpatterns)),
}
