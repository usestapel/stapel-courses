# Errors — Español

`72` error keys. Canonical texts live in the code (`register_service_errors`); localized texts in `translations/errors.es.json`.

| Código | Estado | Parámetros | Acción | Texto |
|---|---|---|---|---|
| `error.400.bad_request` | 400 | — | `fix_input` | Solicitud incorrecta |
| `error.400.captcha_invalid` | 400 | — | `retry` | La verificación del captcha ha fallado. Inténtalo de nuevo. |
| `error.400.captcha_required` | 400 | — | `retry` | Se requiere el token del captcha. |
| `error.400.course_access_unknown` | 400 | `access` | `fix_input` | Modo de acceso desconocido {access} |
| `error.400.course_price_required` | 400 | — | `fix_input` | Un curso vendido mediante pedidos necesita precio y moneda |
| `error.400.course_slug_frozen` | 400 | — | `fix_input` | La dirección de un curso publicado no se puede cambiar |
| `error.400.course_slug_taken` | 400 | `slug` | `fix_input` | La dirección {slug} ya la usa otro curso |
| `error.400.expected_list` | 400 | — | `fix_input` | Se esperaba una lista de elementos |
| `error.400.field.blank` | 400 | `field` | `fix_input` | {field} no puede estar vacío |
| `error.400.field.does_not_exist` | 400 | `field` | `fix_input` | {field} no existe |
| `error.400.field.invalid` | 400 | `field` | `fix_input` | {field} no es válido |
| `error.400.field.invalid_choice` | 400 | `field` | `fix_input` | {field} no es una opción válida |
| `error.400.field.max_length` | 400 | `field`, `max_length` | `fix_input` | {field} debe tener como máximo {max_length} caracteres |
| `error.400.field.max_value` | 400 | `field`, `max_value` | `fix_input` | {field} debe ser como máximo {max_value} |
| `error.400.field.min_length` | 400 | `field`, `min_length` | `fix_input` | {field} debe tener al menos {min_length} caracteres |
| `error.400.field.min_value` | 400 | `field`, `min_value` | `fix_input` | {field} debe ser como mínimo {min_value} |
| `error.400.field.null` | 400 | `field` | `fix_input` | {field} no puede ser nulo |
| `error.400.field.required` | 400 | `field` | `fix_input` | {field} es obligatorio |
| `error.400.field.unique` | 400 | `field` | `fix_input` | {field} debe ser único |
| `error.400.invalid_ad_id` | 400 | — | `fix_input` | ID de anuncio no válido |
| `error.400.lesson_block_invalid` | 400 | `index`, `reason` | `fix_input` | El bloque de contenido {index} no es válido ({reason}) |
| `error.400.question_invalid` | 400 | `reason` | `fix_input` | La pregunta no es válida ({reason}) |
| `error.400.quiz_answer_invalid` | 400 | `question_id` | `fix_input` | La respuesta a la pregunta {question_id} no le corresponde |
| `error.400.quiz_target_invalid` | 400 | — | `fix_input` | Un cuestionario pertenece exactamente a una lección o un módulo del curso |
| `error.400.too_many_ids` | 400 | `requested`, `limit` | `fix_input` | Demasiados identificadores: {requested} solicitados, como máximo {limit} por solicitud por lotes |
| `error.400.validation_error` | 400 | — | `fix_input` | Error de validación |
| `error.400.verification_failed` | 400 | — | `verify` | La verificación ha fallado |
| `error.400.verification_invalid_factor` | 400 | — | `verify` | Este factor de verificación no está disponible |
| `error.401.unauthorized` | 401 | — | `reauthenticate` | Se requiere autenticación |
| `error.402.payment_required` | 402 | — | `retry` | Se requiere pago |
| `error.403.course_authoring_forbidden` | 403 | — | `retry` | No puedes editar este curso |
| `error.403.course_entitlement_required` | 403 | — | `retry` | Tu plan no incluye este curso |
| `error.403.course_purchase_required` | 403 | — | `retry` | Compra este curso para empezar a aprender |
| `error.403.enrollment_requires_account` | 403 | — | `reauthenticate` | Inicia sesión para inscribirte |
| `error.403.forbidden` | 403 | — | `retry` | No tienes permiso para realizar esta acción |
| `error.403.lesson_locked` | 403 | `reason`, `unlocks_at`, `after_lesson_id`, `after_quiz_id` | `retry` | Esta lección aún no está abierta ({reason}; se abre el {unlocks_at}; tras la lección {after_lesson_id}; tras el cuestionario {after_quiz_id}) |
| `error.403.lesson_review_required` | 403 | — | `retry` | Esta lección se completa cuando un revisor la acepta |
| `error.403.network_blocked` | 403 | — | `contact_support` | No se permiten solicitudes desde esta red. |
| `error.403.verification_enrollment_required` | 403 | — | `verify` | Es necesario registrar un factor de verificación. |
| `error.403.verification_required` | 403 | — | `verify` | Se requiere verificación adicional |
| `error.404.ad_not_found` | 404 | — | `retry` | Anuncio no encontrado |
| `error.404.certificate_not_found` | 404 | — | `retry` | Certificado no encontrado |
| `error.404.course_module_not_found` | 404 | — | `retry` | Módulo no encontrado |
| `error.404.course_not_found` | 404 | — | `retry` | Curso no encontrado |
| `error.404.enrollment_not_found` | 404 | — | `verify` | Inscripción no encontrada |
| `error.404.lesson_not_found` | 404 | — | `retry` | Lección no encontrada |
| `error.404.not_found` | 404 | — | `retry` | Recurso solicitado no encontrado |
| `error.404.question_not_found` | 404 | — | `retry` | Pregunta no encontrada |
| `error.404.quiz_attempt_not_found` | 404 | — | `retry` | Intento no encontrado |
| `error.404.quiz_not_found` | 404 | — | `retry` | Cuestionario no encontrado |
| `error.404.verification_challenge_not_found` | 404 | — | `verify` | Desafío de verificación no encontrado o caducado |
| `error.405.method_not_allowed` | 405 | — | `retry` | Método no permitido |
| `error.406.not_acceptable` | 406 | — | `retry` | No aceptable |
| `error.408.request_timeout` | 408 | — | `retry` | Tiempo de espera de la solicitud agotado |
| `error.409.conflict` | 409 | — | `fix_input` | El recurso ya existe |
| `error.409.course_not_draft` | 409 | — | `fix_input` | Solo se puede eliminar un curso en borrador |
| `error.409.course_not_published` | 409 | — | `fix_input` | Este curso no está abierto a inscripciones |
| `error.409.course_transition_invalid` | 409 | `from`, `to` | `fix_input` | El curso no puede pasar de {from} a {to} |
| `error.409.enrollment_transition_invalid` | 409 | `from`, `to` | `verify` | La inscripción no puede pasar de {from} a {to} |
| `error.409.quiz_attempts_exhausted` | 409 | `max` | `fix_input` | No quedan intentos (como máximo {max}) |
| `error.409.quiz_empty` | 409 | — | `fix_input` | Este cuestionario todavía no tiene preguntas |
| `error.410.gone` | 410 | — | `retry` | El recurso se ha eliminado permanentemente |
| `error.413.payload_too_large` | 413 | — | `retry` | El cuerpo de la solicitud es demasiado grande |
| `error.415.unsupported_media_type` | 415 | — | `retry` | Tipo de contenido no compatible |
| `error.422.unprocessable_entity` | 422 | — | `wait_and_retry` | Entidad no procesable |
| `error.423.locked` | 423 | — | `wait_and_retry` | El recurso está bloqueado |
| `error.423.verification_locked` | 423 | — | `wait_and_retry` | Demasiados intentos fallidos — verificación bloqueada |
| `error.429.rate_limit` | 429 | `retry_after_display`, `retry_after`, `retry_after_minutes` | `wait_and_retry` | Demasiados intentos. Inténtalo de nuevo en {retry_after_display} ({retry_after} s, unos {retry_after_minutes} min). |
| `error.429.too_many_requests` | 429 | — | `wait_and_retry` | Demasiadas solicitudes. Inténtalo de nuevo más tarde. |
| `error.500.internal` | 500 | — | `contact_support` | Algo salió mal |
| `error.503.entitlement_unavailable` | 503 | — | `wait_and_retry` | Ahora no se puede comprobar tu plan; inténtalo de nuevo en breve |
| `error.503.mandate_unavailable` | 503 | — | `retry` | No se puede verificar el mandato del espacio de trabajo |
