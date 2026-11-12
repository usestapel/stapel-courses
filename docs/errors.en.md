# Errors — English

`71` error keys. Canonical texts live in the code (`register_service_errors`); localized texts in `translations/errors.en.json`.

| Code | Status | Params | Remediation | Text |
|---|---|---|---|---|
| `error.400.bad_request` | 400 | — | `fix_input` | Bad request |
| `error.400.captcha_invalid` | 400 | — | `retry` | Captcha verification failed. Please try again. |
| `error.400.captcha_required` | 400 | — | `retry` | Captcha token is required. |
| `error.400.course_access_unknown` | 400 | `access` | `fix_input` | Unknown access mode {access} |
| `error.400.course_price_required` | 400 | — | `fix_input` | A course sold through orders needs a price and a currency |
| `error.400.course_slug_frozen` | 400 | — | `fix_input` | The address of a published course cannot change |
| `error.400.course_slug_taken` | 400 | `slug` | `fix_input` | The address {slug} is already used by another course |
| `error.400.expected_list` | 400 | — | `fix_input` | Expected a list of items |
| `error.400.field.blank` | 400 | `field` | `fix_input` | {field} may not be blank |
| `error.400.field.does_not_exist` | 400 | `field` | `fix_input` | {field} does not exist |
| `error.400.field.invalid` | 400 | `field` | `fix_input` | {field} is invalid |
| `error.400.field.invalid_choice` | 400 | `field` | `fix_input` | {field} is not a valid choice |
| `error.400.field.max_length` | 400 | `field`, `max_length` | `fix_input` | {field} must be at most {max_length} characters |
| `error.400.field.max_value` | 400 | `field`, `max_value` | `fix_input` | {field} must be at most {max_value} |
| `error.400.field.min_length` | 400 | `field`, `min_length` | `fix_input` | {field} must be at least {min_length} characters |
| `error.400.field.min_value` | 400 | `field`, `min_value` | `fix_input` | {field} must be at least {min_value} |
| `error.400.field.null` | 400 | `field` | `fix_input` | {field} may not be null |
| `error.400.field.required` | 400 | `field` | `fix_input` | {field} is required |
| `error.400.field.unique` | 400 | `field` | `fix_input` | {field} must be unique |
| `error.400.invalid_ad_id` | 400 | — | `fix_input` | Invalid advertisement ID |
| `error.400.lesson_block_invalid` | 400 | `index`, `reason` | `fix_input` | Content block {index} is invalid ({reason}) |
| `error.400.question_invalid` | 400 | `reason` | `fix_input` | The question is invalid ({reason}) |
| `error.400.quiz_answer_invalid` | 400 | `question_id` | `fix_input` | The answer to question {question_id} does not fit it |
| `error.400.quiz_target_invalid` | 400 | — | `fix_input` | A quiz belongs to exactly one lesson or module of the course |
| `error.400.validation_error` | 400 | — | `fix_input` | Validation error |
| `error.400.verification_failed` | 400 | — | `verify` | Verification failed |
| `error.400.verification_invalid_factor` | 400 | — | `verify` | This verification factor is not available |
| `error.401.unauthorized` | 401 | — | `reauthenticate` | Authentication required |
| `error.402.payment_required` | 402 | — | `retry` | Payment required |
| `error.403.course_authoring_forbidden` | 403 | — | `retry` | You cannot edit this course |
| `error.403.course_entitlement_required` | 403 | — | `retry` | Your plan does not include this course |
| `error.403.course_purchase_required` | 403 | — | `retry` | Buy this course to start learning |
| `error.403.enrollment_requires_account` | 403 | — | `reauthenticate` | Sign in to enroll |
| `error.403.forbidden` | 403 | — | `retry` | You do not have permission to perform this action |
| `error.403.lesson_locked` | 403 | `reason`, `unlocks_at`, `after_lesson_id`, `after_quiz_id` | `retry` | This lesson is not open yet ({reason}; opens at {unlocks_at}; after lesson {after_lesson_id}; after quiz {after_quiz_id}) |
| `error.403.lesson_review_required` | 403 | — | `retry` | This lesson is completed when a reviewer accepts it |
| `error.403.network_blocked` | 403 | — | `contact_support` | Requests from this network are not allowed |
| `error.403.verification_enrollment_required` | 403 | — | `verify` | Verification factor enrollment required |
| `error.403.verification_required` | 403 | — | `verify` | Additional verification required |
| `error.404.ad_not_found` | 404 | — | `retry` | Listing not found |
| `error.404.certificate_not_found` | 404 | — | `retry` | Certificate not found |
| `error.404.course_module_not_found` | 404 | — | `retry` | Module not found |
| `error.404.course_not_found` | 404 | — | `retry` | Course not found |
| `error.404.enrollment_not_found` | 404 | — | `verify` | Enrollment not found |
| `error.404.lesson_not_found` | 404 | — | `retry` | Lesson not found |
| `error.404.not_found` | 404 | — | `retry` | Requested resource not found |
| `error.404.question_not_found` | 404 | — | `retry` | Question not found |
| `error.404.quiz_attempt_not_found` | 404 | — | `retry` | Attempt not found |
| `error.404.quiz_not_found` | 404 | — | `retry` | Quiz not found |
| `error.404.verification_challenge_not_found` | 404 | — | `verify` | Verification challenge not found or expired |
| `error.405.method_not_allowed` | 405 | — | `retry` | Method not allowed |
| `error.406.not_acceptable` | 406 | — | `retry` | Not acceptable |
| `error.408.request_timeout` | 408 | — | `retry` | Request timeout |
| `error.409.conflict` | 409 | — | `fix_input` | Resource already exists |
| `error.409.course_not_draft` | 409 | — | `fix_input` | Only a draft course can be deleted |
| `error.409.course_not_published` | 409 | — | `fix_input` | This course is not open for enrollment |
| `error.409.course_transition_invalid` | 409 | `from`, `to` | `fix_input` | The course cannot move from {from} to {to} |
| `error.409.enrollment_transition_invalid` | 409 | `from`, `to` | `verify` | The enrollment cannot move from {from} to {to} |
| `error.409.quiz_attempts_exhausted` | 409 | `max` | `fix_input` | No attempts left (at most {max}) |
| `error.409.quiz_empty` | 409 | — | `fix_input` | This quiz has no questions yet |
| `error.410.gone` | 410 | — | `retry` | Resource has been permanently removed |
| `error.413.payload_too_large` | 413 | — | `retry` | Request body is too large |
| `error.415.unsupported_media_type` | 415 | — | `retry` | Unsupported media type |
| `error.422.unprocessable_entity` | 422 | — | `wait_and_retry` | Unprocessable entity |
| `error.423.locked` | 423 | — | `wait_and_retry` | Resource is locked |
| `error.423.verification_locked` | 423 | — | `wait_and_retry` | Too many failed attempts — verification locked |
| `error.429.rate_limit` | 429 | `retry_after_minutes` | `wait_and_retry` | Too many attempts. Try again in {retry_after_minutes} minutes. |
| `error.429.too_many_requests` | 429 | — | `wait_and_retry` | Too many requests. Please try again later. |
| `error.500.internal` | 500 | — | `contact_support` | Something went wrong |
| `error.503.entitlement_unavailable` | 503 | — | `wait_and_retry` | Your plan cannot be checked right now; try again shortly |
| `error.503.mandate_unavailable` | 503 | — | `retry` | Cannot verify workspace mandate right now |
