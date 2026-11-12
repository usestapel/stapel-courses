# CONFIG.MD — stapel-courses

Config registry for **stapel-courses**. One row per configuration key the
module reads, its **source** (`env` = the process environment / the
`STAPEL_COURSES` settings dict; `settings` = the settings module only), what
it is for, whether it is required, and its default.

Every key is read through `courses_settings` (`stapel_courses.conf`,
namespace `STAPEL_COURSES`). Resolution order per key:
`settings.STAPEL_COURSES` dict → a flat Django setting of the same name →
environment variable → the default below. `DEFAULT_ACCESS`,
`ENROLLMENT_REQUIRES_ACCOUNT`, `PURCHASE_ACTIVATION`, `DEFAULT_DRIP`,
`DEFAULT_SEQUENTIAL`, `AUTHORING` and `CERTIFICATES` are CTO-facing config
axes.

## stapel-courses

| Key | Source | Purpose | Required | Default |
|-----|--------|---------|----------|---------|
| ACCESS_STRATEGIES | settings | access strategies `{name: dotted path or None}` merged over free / enrolled / purchased / entitlement; a dotted path under a built-in name replaces it. Checked by E001. | no | {} |
| DEFAULT_ACCESS | env | axis: the access strategy a new course starts with. Unknown name is E002. | no | enrolled |
| DEFAULT_DRIP | env | axis: the drip mode a new course starts with (none, days, date). E005. | no | none |
| DEFAULT_SEQUENTIAL | env | axis: a new course unlocks lessons strictly in order. | no | false |
| AUTHORING | env | axis: who creates courses (staff, members). E005. | no | staff |
| ENROLLMENT_REQUIRES_ACCOUNT | env | axis: a guest gets `error.403.enrollment_requires_account` on enroll / progress / attempts. | no | true |
| PURCHASABLE_TYPE | env | the orders purchasable type a course line carries. | no | course |
| PURCHASE_ACTIVATION | env | axis: which order fact activates a bought course (paid, confirmed, placed). E005. | no | paid |
| ENTITLEMENT_FUNCTION | env | the comm Function asked `{user_id, key}` for the entitlement strategy. | no | billing.check_entitlement |
| ENTITLEMENT_KEY_TEMPLATE | env | `{slug}` / `{course_id}` template of the entitlement key when a course names none. | no | course:{slug} |
| ENTITLEMENT_CACHE_SECONDS | env | how long an entitlement answer is cached; 0 = ask every time. | no | 300 |
| BLOCK_TYPES | settings | lesson block validators `{type: dotted path or None}` merged over text / video / attachment / embed. E004. | no | {} |
| CARDS_FUNCTION | env | the comm Function asked `{user_ids}` for learner display cards on the author/staff views (profiles.public_cards contract); empty = `user_id` only. | no | profiles.public_cards |
| EMBED_HOSTS | settings | hosts an embed block may point at; empty = any https host. | no | [] |
| DEFAULT_PASS_MARK | env | pass mark (percent) of a new quiz. | no | 70 |
| DEFAULT_MAX_ATTEMPTS | env | attempt limit of a new quiz; 0 = unlimited. | no | 3 |
| COMPLETION_RULE | settings | dotted path `(enrollment) -> bool` deciding completion. E006. | no | stapel_courses.services.progress.default_completion_rule |
| CERTIFICATES | env | axis: issue a certificate on completion. | no | true |
| PUBLIC_VERIFY_FIELDS | settings | fields the public verification shows besides number and validity (holder_name, course_title, course_slug, issued_at). E003. | no | ["course_title", "issued_at"] |
| CERTIFICATE_NUMBER_PREFIX | env | prefix of certificate numbers. | no | CERT |
| HOLDER_NAME_RESOLVER | settings | dotted path `(user_id) -> str`, the name printed on a certificate. E006. | no | stapel_courses.services.certificates.default_holder_name |
| NOTIFY | env | best-effort notifications courses.enrollment_activated / .completed / .certificate_issued. | no | true |
| COURSE_URL_TEMPLATE | env | `{slug}` / `{course_id}` link for notifications and the purchasable `url`; empty = no link. | no | "" |
| CERTIFICATE_URL_TEMPLATE | env | `{number}` / `{slug}` / `{course_id}` link for the certificate notification; empty = no link. | no | "" |
