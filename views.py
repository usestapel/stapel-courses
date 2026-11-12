"""DRF views for stapel-courses — thin over ``services``.

Every view declares its guest stance. Catalog, outline, lesson reads and the
certificate verification admit anonymous requests (content stays gated by
the course's access strategy). Enrolling, progress and quiz attempts admit a
guest session statically and enforce ``ENROLLMENT_REQUIRES_ACCOUNT`` in the
body. Author views refuse guests and scope to the caller's courses (staff
see all); a course you may not edit is the same 404 as an absent one.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from stapel_core.django.api.errors import StapelResponse
from stapel_core.django.api.permissions import (
    ANONYMOUS_ALLOWED,
    ANONYMOUS_DENIED,
    IsNotAnonymousUser,
)
from stapel_core.django.api.views import StapelAPIView
from stapel_core.flows import flow_step

from .flows import AUTHOR, LEARN, QUIZ, VERIFY
from .models import CourseLevel, CourseStatus, EnrollmentStatus
from .pagination import CatalogAnchorPagination, IdAnchorPagination
from .presenters import (
    get_attempt_presenter,
    get_certificate_presenter,
    get_course_presenter,
    get_enrollment_presenter,
    get_lesson_presenter,
    get_quiz_presenter,
)
from .serializers import (
    AttemptSerializer,
    AttemptSubmitRequestSerializer,
    AuthorCoursePageSerializer,
    AuthorCourseSerializer,
    AuthorCourseTreeSerializer,
    AuthorLessonSerializer,
    AuthorModuleSerializer,
    AuthorQuestionSerializer,
    AuthorQuizSerializer,
    CertificatePageSerializer,
    CertificateRevokeRequestSerializer,
    CertificateSerializer,
    CertificateVerificationSerializer,
    CourseCardSerializer,
    CourseOutlineSerializer,
    CoursePageSerializer,
    CourseProgressSerializer,
    EnrollmentGrantRequestSerializer,
    EnrollmentPageSerializer,
    EnrollmentSerializer,
    EnrollmentTransitionRequestSerializer,
    LessonProgressRequestSerializer,
    LessonProgressSerializer,
    LessonReviewRequestSerializer,
    LessonSerializer,
    QuizSerializer,
)
from .services import user_id_of
from .services import authoring
from .services import catalog as catalog_service
from .services import certificates as certificate_service
from .services import enrollments as enrollment_service
from .services import gate
from .services import progress as progress_service
from .services import quizzes as quiz_service

TAGS = ["Courses"]
AUTHOR_TAGS = ["Courses authoring"]

LEARNER_WRITE = [permissions.IsAuthenticated]
AUTHOR_PERMISSIONS = [permissions.IsAuthenticated, IsNotAnonymousUser]


def _anchor_parameters(paginator):
    return [
        OpenApiParameter("anchor", str, OpenApiParameter.QUERY, required=False,
                         description="Opaque anchor from next_anchor/prev_anchor (exclusive)."),
        OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False,
                         description=f"Page size, default {paginator.page_size}, "
                                     f"max {paginator.max_page_size}."),
        OpenApiParameter("direction", str, OpenApiParameter.QUERY, required=False,
                         enum=["next", "prev"], description="Walk direction from the anchor."),
    ]


ENROLLMENT_STATUS_PARAMETER = OpenApiParameter(
    "status", str, OpenApiParameter.QUERY, required=False, many=True,
    enum=[value for value, _ in EnrollmentStatus.choices],
    description="Filter by status (repeatable).",
)


class _CoursesView(StapelAPIView):
    def _paginate(self, request, qs, paginator_class, render):
        paginator = paginator_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(render(page))


def _enrollment_data(enrollment):
    return EnrollmentSerializer(get_enrollment_presenter()().present(enrollment)).data


# ── learner ───────────────────────────────────────────────────────────────


@extend_schema(tags=TAGS)
class CatalogView(_CoursesView):
    """Published courses, newest first."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED

    @extend_schema(
        operation_id="courses_catalog_list",
        parameters=[
            OpenApiParameter("level", str, OpenApiParameter.QUERY, required=False,
                             enum=[v for v, _ in CourseLevel.choices]),
            OpenApiParameter("scope", str, OpenApiParameter.QUERY, required=False,
                             description="Opaque cohort/workspace id the course is scoped to."),
            *_anchor_parameters(CatalogAnchorPagination),
        ],
        responses={200: CoursePageSerializer},
    )
    @flow_step(LEARN, order=1, note="Browse the catalog")
    def get(self, request):
        qs = catalog_service.catalog(request.query_params.get("level"), request.query_params.get("scope"))
        presenter = get_course_presenter()()
        return self._paginate(
            request, qs, CatalogAnchorPagination,
            lambda page: CourseCardSerializer(presenter.cards(page), many=True).data,
        )


@extend_schema(tags=TAGS)
class CourseOutlineView(_CoursesView):
    """A course, my enrollment and its outline with a lock reason per lesson."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = CourseOutlineSerializer

    @extend_schema(operation_id="courses_course_retrieve", responses={200: CourseOutlineSerializer})
    @flow_step(LEARN, order=2, note="Open the outline: what is open, what is locked and why")
    def get(self, request, slug):
        course = gate.visible_course(slug, request.user)
        view = gate.course_view(course, request.user)
        can_enroll = enrollment_service.can_self_enroll(request.user, course, view.enrollment)
        return self.serialized_response(get_course_presenter()().outline(view, can_enroll))


@extend_schema(tags=TAGS)
class EnrollView(_CoursesView):
    """Enroll myself; the course's access strategy decides whether and how."""

    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = EnrollmentSerializer

    @extend_schema(operation_id="courses_course_enroll", request=None,
                   responses={201: EnrollmentSerializer, 200: EnrollmentSerializer})
    @flow_step(LEARN, order=3, note="Enroll (free, or through a plan entitlement)")
    def post(self, request, slug):
        course = gate.visible_course(slug, request.user)
        enrollment, changed = enrollment_service.self_enroll(request.user, course)
        presenter = get_enrollment_presenter()()
        return self.serialized_response(presenter.present(enrollment), status=201 if changed else 200)


@extend_schema(tags=TAGS)
class LessonView(_CoursesView):
    """A lesson's content — only when the gate opens it (else 403 lesson_locked)."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = LessonSerializer

    @extend_schema(operation_id="courses_lesson_retrieve", responses={200: LessonSerializer})
    @flow_step(LEARN, order=5, note="Read a lesson: text, video by media id, attachments, embeds")
    def get(self, request, slug, lesson_id):
        course = gate.visible_course(slug, request.user)
        view = gate.course_view(course, request.user)
        lesson = gate.require_lesson(view, lesson_id)
        return self.serialized_response(get_lesson_presenter()().present(view, lesson))


@extend_schema(tags=TAGS)
class LessonProgressView(_CoursesView):
    """Upsert my progress on a lesson (forward-only status, last position)."""

    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = LessonProgressRequestSerializer
    response_serializer_class = LessonProgressSerializer

    @extend_schema(operation_id="courses_lesson_progress", request=LessonProgressRequestSerializer,
                   responses={200: LessonProgressSerializer})
    @flow_step(LEARN, order=6, note="Save progress; completing the last item completes the course")
    def post(self, request, slug, lesson_id):
        data = self.validated_request_data(request)
        course = gate.visible_course(slug, request.user)
        row, enrollment = progress_service.record(
            request.user, course, lesson_id,
            status=data.get("status"), position_seconds=data.get("position_seconds"),
        )
        if enrollment is not None:
            enrollment.refresh_from_db()
        return self.serialized_response(get_lesson_presenter()().progress(row, enrollment))


@extend_schema(tags=TAGS)
class CourseProgressView(_CoursesView):
    """My progress on one course: every lesson row and every quiz standing."""

    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = CourseProgressSerializer

    @extend_schema(operation_id="courses_course_progress", responses={200: CourseProgressSerializer})
    @flow_step(LEARN, order=9, note="See my progress: every lesson and quiz standing")
    def get(self, request, slug):
        course = gate.visible_course(slug, request.user)
        view = gate.course_view(course, request.user)
        return self.serialized_response(get_lesson_presenter()().course_progress(view))


@extend_schema(tags=TAGS)
class MyEnrollmentsView(_CoursesView):
    """My courses, newest enrollment first."""

    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED

    @extend_schema(
        operation_id="courses_my_enrollments_list",
        parameters=[ENROLLMENT_STATUS_PARAMETER, *_anchor_parameters(IdAnchorPagination)],
        responses={200: EnrollmentPageSerializer},
    )
    @flow_step(LEARN, order=10, note="My courses, newest first")
    def get(self, request):
        qs = catalog_service.my_enrollments(user_id_of(request.user), request.query_params.getlist("status"))
        presenter = get_enrollment_presenter()()
        return self._paginate(
            request, qs, IdAnchorPagination,
            lambda page: EnrollmentSerializer([presenter.present(e) for e in page], many=True).data,
        )


@extend_schema(tags=TAGS)
class MyCertificatesView(_CoursesView):
    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED

    @extend_schema(operation_id="courses_my_certificates_list",
                   parameters=_anchor_parameters(IdAnchorPagination),
                   responses={200: CertificatePageSerializer})
    @flow_step(LEARN, order=11, note="My certificates")
    def get(self, request):
        qs = catalog_service.my_certificates(user_id_of(request.user))
        presenter = get_certificate_presenter()()
        return self._paginate(
            request, qs, IdAnchorPagination,
            lambda page: CertificateSerializer([presenter.present(c) for c in page], many=True).data,
        )


@extend_schema(tags=TAGS)
class QuizView(_CoursesView):
    """A quiz's rules and my standing — never its questions."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = QuizSerializer

    @extend_schema(operation_id="courses_quiz_retrieve", responses={200: QuizSerializer})
    @flow_step(QUIZ, order=1, note="See the pass mark and the attempts left")
    def get(self, request, quiz_id):
        return self.serialized_response(
            get_quiz_presenter()().present(quiz_service.quiz_summary(request.user, quiz_id))
        )


@extend_schema(tags=TAGS)
class QuizAttemptsView(_CoursesView):
    """Start an attempt, or get the open one back (idempotent)."""

    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = AttemptSerializer

    @extend_schema(operation_id="courses_quiz_attempt_start", request=None,
                   responses={201: AttemptSerializer, 200: AttemptSerializer})
    @flow_step(QUIZ, order=2, note="Start an attempt: questions without their answers")
    def post(self, request, quiz_id):
        attempt, created = quiz_service.start(request.user, quiz_id)
        return self.serialized_response(
            get_attempt_presenter()().present(attempt), status=201 if created else 200
        )


@extend_schema(tags=TAGS)
class AttemptView(_CoursesView):
    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = AttemptSerializer

    @extend_schema(operation_id="courses_attempt_retrieve", responses={200: AttemptSerializer})
    @flow_step(QUIZ, order=4, note="Re-open an attempt: same order, same result")
    def get(self, request, attempt_id):
        attempt = quiz_service.get_attempt(request.user, attempt_id)
        return self.serialized_response(get_attempt_presenter()().present(attempt))


@extend_schema(tags=TAGS)
class AttemptSubmitView(_CoursesView):
    permission_classes = LEARNER_WRITE
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = AttemptSubmitRequestSerializer
    response_serializer_class = AttemptSerializer

    @extend_schema(operation_id="courses_attempt_submit", request=AttemptSubmitRequestSerializer,
                   responses={200: AttemptSerializer})
    @flow_step(QUIZ, order=3, note="Submit: graded on the server, replay returns the same result")
    def post(self, request, attempt_id):
        data = self.validated_request_data(request)
        attempt, _ = quiz_service.submit(request.user, attempt_id, [dict(a) for a in data["answers"]])
        return self.serialized_response(get_attempt_presenter()().present(attempt))


@extend_schema(tags=TAGS)
class CertificateVerifyView(_CoursesView):
    """Public verification by number; only the configured fields are shown."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = CertificateVerificationSerializer

    @extend_schema(operation_id="courses_certificate_verify",
                   responses={200: CertificateVerificationSerializer})
    @flow_step(VERIFY, order=1, note="Check a certificate number")
    def get(self, request, number):
        view = certificate_service.public_view(number)
        return self.serialized_response(get_certificate_presenter()().verification(view))


# ── author / staff ────────────────────────────────────────────────────────


class _AuthorView(_CoursesView):
    permission_classes = AUTHOR_PERMISSIONS
    stapel_anonymous_access = ANONYMOUS_DENIED


@extend_schema(tags=AUTHOR_TAGS)
class AuthorCoursesView(_AuthorView):
    request_serializer_class = AuthorCourseSerializer
    response_serializer_class = AuthorCourseSerializer

    @extend_schema(
        operation_id="courses_author_courses_list",
        parameters=[
            OpenApiParameter("status", str, OpenApiParameter.QUERY, required=False,
                             enum=[v for v, _ in CourseStatus.choices]),
            *_anchor_parameters(IdAnchorPagination),
        ],
        responses={200: AuthorCoursePageSerializer},
    )
    @flow_step(AUTHOR, order=1, note="List the courses I may edit")
    def get(self, request):
        qs = authoring.editable_courses(request.user)
        status = request.query_params.get("status")
        if status in CourseStatus.values:
            qs = qs.filter(status=status)
        return self._paginate(
            request, qs, IdAnchorPagination,
            lambda page: AuthorCourseSerializer(page, many=True).data,
        )

    @extend_schema(operation_id="courses_author_courses_create", request=AuthorCourseSerializer,
                   responses={201: AuthorCourseSerializer})
    @flow_step(AUTHOR, order=2, note="Create a draft course")
    def post(self, request):
        data = self.validated_request_data(request)
        return self.serialized_response(authoring.create_course(request.user, dict(data)), status=201)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorCourseView(_AuthorView):
    request_serializer_class = AuthorCourseSerializer
    response_serializer_class = AuthorCourseSerializer

    @extend_schema(operation_id="courses_author_course_retrieve",
                   responses={200: AuthorCourseTreeSerializer})
    @flow_step(AUTHOR, order=10, note="Open the course tree with lessons and quizzes")
    def get(self, request, course_id):
        course = authoring.editable_course(request.user, course_id)
        modules = [
            {
                "id": module.pk, "title": module.title, "position": module.position,
                "lessons": list(module.lessons.all()),
                "quizzes": list(module.quizzes.all()) + [
                    q for lesson in module.lessons.all() for q in lesson.quizzes.all()
                ],
            }
            for module in course.modules.all()
        ]
        return StapelResponse(AuthorCourseTreeSerializer({"course": course, "modules": modules}))

    @extend_schema(operation_id="courses_author_course_update", request=AuthorCourseSerializer,
                   responses={200: AuthorCourseSerializer})
    @flow_step(AUTHOR, order=11, note="Edit the course")
    def patch(self, request, course_id):
        data = self.validated_request_data(request, partial=True)
        return self.serialized_response(authoring.update_course(request.user, course_id, dict(data)))

    @extend_schema(operation_id="courses_author_course_destroy", responses={204: None})
    @flow_step(AUTHOR, order=12, note="Delete a draft course nobody enrolled in")
    def delete(self, request, course_id):
        authoring.delete_course(request.user, course_id)
        return StapelResponse(status=204)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorCoursePublishView(_AuthorView):
    response_serializer_class = AuthorCourseSerializer

    @extend_schema(operation_id="courses_author_course_publish", request=None,
                   responses={200: AuthorCourseSerializer})
    @flow_step(AUTHOR, order=4, note="Publish the course")
    def post(self, request, course_id):
        return self.serialized_response(
            authoring.move_course(request.user, course_id, CourseStatus.PUBLISHED)
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorCourseArchiveView(_AuthorView):
    response_serializer_class = AuthorCourseSerializer

    @extend_schema(operation_id="courses_author_course_archive", request=None,
                   responses={200: AuthorCourseSerializer})
    @flow_step(AUTHOR, order=9, note="Archive the course: out of the catalog, learners keep it")
    def post(self, request, course_id):
        return self.serialized_response(
            authoring.move_course(request.user, course_id, CourseStatus.ARCHIVED)
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorModulesView(_AuthorView):
    request_serializer_class = AuthorModuleSerializer
    response_serializer_class = AuthorModuleSerializer

    @extend_schema(operation_id="courses_author_modules_create", request=AuthorModuleSerializer,
                   responses={201: AuthorModuleSerializer})
    @flow_step(AUTHOR, order=3, note="Add modules, lessons, quizzes and questions")
    def post(self, request, course_id):
        data = self.validated_request_data(request)
        return self.serialized_response(
            authoring.create_module(request.user, course_id, dict(data)), status=201
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorModuleView(_AuthorView):
    request_serializer_class = AuthorModuleSerializer
    response_serializer_class = AuthorModuleSerializer

    @extend_schema(operation_id="courses_author_module_update", request=AuthorModuleSerializer,
                   responses={200: AuthorModuleSerializer})
    @flow_step(AUTHOR, order=13, note="Rename or reorder a module")
    def patch(self, request, module_id):
        data = self.validated_request_data(request, partial=True)
        return self.serialized_response(authoring.update_module(request.user, module_id, dict(data)))

    @extend_schema(operation_id="courses_author_module_destroy", responses={204: None})
    @flow_step(AUTHOR, order=14, note="Delete a module")
    def delete(self, request, module_id):
        authoring.delete_module(request.user, module_id)
        return StapelResponse(status=204)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorLessonsView(_AuthorView):
    request_serializer_class = AuthorLessonSerializer
    response_serializer_class = AuthorLessonSerializer

    @extend_schema(operation_id="courses_author_lessons_create", request=AuthorLessonSerializer,
                   responses={201: AuthorLessonSerializer})
    @flow_step(AUTHOR, order=15, note="Add a lesson with typed content blocks")
    def post(self, request, module_id):
        data = self.validated_request_data(request)
        return self.serialized_response(
            authoring.create_lesson(request.user, module_id, dict(data)), status=201
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorLessonView(_AuthorView):
    request_serializer_class = AuthorLessonSerializer
    response_serializer_class = AuthorLessonSerializer

    @extend_schema(operation_id="courses_author_lesson_update", request=AuthorLessonSerializer,
                   responses={200: AuthorLessonSerializer})
    @flow_step(AUTHOR, order=16, note="Edit a lesson")
    def patch(self, request, lesson_id):
        data = self.validated_request_data(request, partial=True)
        return self.serialized_response(authoring.update_lesson(request.user, lesson_id, dict(data)))

    @extend_schema(operation_id="courses_author_lesson_destroy", responses={204: None})
    @flow_step(AUTHOR, order=17, note="Delete a lesson")
    def delete(self, request, lesson_id):
        authoring.delete_lesson(request.user, lesson_id)
        return StapelResponse(status=204)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorLessonReviewView(_AuthorView):
    """The simple reviewer verdict on a ``review_required`` lesson."""

    request_serializer_class = LessonReviewRequestSerializer
    response_serializer_class = LessonProgressSerializer

    @extend_schema(operation_id="courses_author_lesson_review", request=LessonReviewRequestSerializer,
                   responses={200: LessonProgressSerializer})
    @flow_step(AUTHOR, order=6, note="Accept or return a submitted lesson")
    def post(self, request, lesson_id):
        data = self.validated_request_data(request)
        lesson = authoring.editable_lesson(request.user, lesson_id)
        row = progress_service.review(lesson.course, lesson.pk, data["user_id"], passed=data["passed"])
        enrollment = lesson.course.enrollments.filter(user_id=data["user_id"]).first()
        return self.serialized_response(get_lesson_presenter()().progress(row, enrollment))


@extend_schema(tags=AUTHOR_TAGS)
class AuthorQuizzesView(_AuthorView):
    request_serializer_class = AuthorQuizSerializer
    response_serializer_class = AuthorQuizSerializer

    @extend_schema(operation_id="courses_author_quizzes_create", request=AuthorQuizSerializer,
                   responses={201: AuthorQuizSerializer})
    @flow_step(AUTHOR, order=18, note="Add a quiz to a lesson or a module")
    def post(self, request):
        data = self.validated_request_data(request)
        return self.serialized_response(authoring.create_quiz(request.user, dict(data)), status=201)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorQuizView(_AuthorView):
    """A quiz with its questions and their right answers (authors only)."""

    request_serializer_class = AuthorQuizSerializer
    response_serializer_class = AuthorQuizSerializer

    @extend_schema(operation_id="courses_author_quiz_retrieve", responses={200: AuthorQuizSerializer})
    @flow_step(AUTHOR, order=19, note="Open a quiz with its right answers")
    def get(self, request, quiz_id):
        return self.serialized_response(authoring.editable_quiz(request.user, quiz_id))

    @extend_schema(operation_id="courses_author_quiz_update", request=AuthorQuizSerializer,
                   responses={200: AuthorQuizSerializer})
    @flow_step(AUTHOR, order=20, note="Edit a quiz's rules")
    def patch(self, request, quiz_id):
        data = self.validated_request_data(request, partial=True)
        return self.serialized_response(authoring.update_quiz(request.user, quiz_id, dict(data)))

    @extend_schema(operation_id="courses_author_quiz_destroy", responses={204: None})
    @flow_step(AUTHOR, order=21, note="Delete a quiz")
    def delete(self, request, quiz_id):
        authoring.delete_quiz(request.user, quiz_id)
        return StapelResponse(status=204)


def _question_data(data) -> dict:
    data = dict(data)
    if "choices" in data:
        data["choices"] = [dict(c) for c in data["choices"]]
    return data


@extend_schema(tags=AUTHOR_TAGS)
class AuthorQuestionsView(_AuthorView):
    request_serializer_class = AuthorQuestionSerializer
    response_serializer_class = AuthorQuestionSerializer

    @extend_schema(operation_id="courses_author_questions_create", request=AuthorQuestionSerializer,
                   responses={201: AuthorQuestionSerializer})
    @flow_step(AUTHOR, order=22, note="Add a question")
    def post(self, request, quiz_id):
        data = self.validated_request_data(request)
        return self.serialized_response(
            authoring.create_question(request.user, quiz_id, _question_data(data)), status=201
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorQuestionView(_AuthorView):
    request_serializer_class = AuthorQuestionSerializer
    response_serializer_class = AuthorQuestionSerializer

    @extend_schema(operation_id="courses_author_question_update", request=AuthorQuestionSerializer,
                   responses={200: AuthorQuestionSerializer})
    @flow_step(AUTHOR, order=23, note="Edit a question")
    def patch(self, request, question_id):
        data = self.validated_request_data(request, partial=True)
        return self.serialized_response(
            authoring.update_question(request.user, question_id, _question_data(data))
        )

    @extend_schema(operation_id="courses_author_question_destroy", responses={204: None})
    @flow_step(AUTHOR, order=24, note="Delete a question")
    def delete(self, request, question_id):
        authoring.delete_question(request.user, question_id)
        return StapelResponse(status=204)


@extend_schema(tags=AUTHOR_TAGS)
class AuthorEnrollmentsView(_AuthorView):
    """A course's enrollments, and the staff/author grant."""

    request_serializer_class = EnrollmentGrantRequestSerializer
    response_serializer_class = EnrollmentSerializer

    @extend_schema(
        operation_id="courses_author_enrollments_list",
        parameters=[ENROLLMENT_STATUS_PARAMETER, *_anchor_parameters(IdAnchorPagination)],
        responses={200: EnrollmentPageSerializer},
    )
    @flow_step(AUTHOR, order=25, note="See who is enrolled")
    def get(self, request, course_id):
        course = authoring.editable_course(request.user, course_id)
        qs = catalog_service.course_enrollments(course, request.query_params.getlist("status"))
        presenter = get_enrollment_presenter()()
        return self._paginate(
            request, qs, IdAnchorPagination,
            lambda page: EnrollmentSerializer([presenter.present(e) for e in page], many=True).data,
        )

    @extend_schema(operation_id="courses_author_enrollments_grant",
                   request=EnrollmentGrantRequestSerializer,
                   responses={201: EnrollmentSerializer, 200: EnrollmentSerializer})
    @flow_step(AUTHOR, order=5, note="Grant a learner access by hand")
    def post(self, request, course_id):
        data = self.validated_request_data(request)
        course = authoring.editable_course(request.user, course_id)
        enrollment, changed = enrollment_service.staff_grant(
            course, data["user_id"], expires_at=data.get("expires_at")
        )
        return self.serialized_response(
            get_enrollment_presenter()().present(enrollment), status=201 if changed else 200
        )


@extend_schema(tags=AUTHOR_TAGS)
class AuthorEnrollmentTransitionView(_AuthorView):
    request_serializer_class = EnrollmentTransitionRequestSerializer
    response_serializer_class = EnrollmentSerializer

    @extend_schema(operation_id="courses_author_enrollment_transition",
                   request=EnrollmentTransitionRequestSerializer,
                   responses={200: EnrollmentSerializer})
    @flow_step(AUTHOR, order=26, note="Cancel, expire or reactivate an enrollment")
    def post(self, request, enrollment_id):
        data = self.validated_request_data(request)
        course_ids = list(authoring.editable_courses(request.user).values_list("pk", flat=True))
        enrollment = enrollment_service.staff_transition(
            enrollment_id, data["to"], reason=data.get("reason", ""), course_ids=course_ids,
        )
        return self.serialized_response(get_enrollment_presenter()().present(enrollment))


@extend_schema(tags=AUTHOR_TAGS)
class AuthorCertificateRevokeView(_AuthorView):
    request_serializer_class = CertificateRevokeRequestSerializer
    response_serializer_class = CertificateSerializer

    @extend_schema(operation_id="courses_author_certificate_revoke",
                   request=CertificateRevokeRequestSerializer,
                   responses={200: CertificateSerializer})
    @flow_step(AUTHOR, order=8, note="Revoke a certificate")
    def post(self, request, number):
        data = self.validated_request_data(request)
        certificate = authoring.editable_certificate(request.user, number)
        certificate_service.revoke(certificate, data.get("reason", ""))
        return self.serialized_response(get_certificate_presenter()().present(certificate))
