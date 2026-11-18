# Frontend integration contract — local API v1

Do not start Phase 8 from invented responses. The generated [OpenAPI](openapi.json)
is the executable request contract; regenerate it from `create_app().openapi()` when
backend routes change. Response models for project/version/job are typed; diagnostic
engine payloads remain versioned heterogeneous objects. Generate client types with
an OpenAPI tool selected for the frontend stack; no bespoke incomplete TypeScript
generator is shipped. The document includes the session cookie scheme and required
CSRF headers. Public system endpoints are `/health`, `/version`, and
`/api/v1/capabilities`; unsupported capabilities must be shown as unavailable.

## Session and guest lifecycle

Start with POST `/api/v1/auth/guest` or register/login using JSON
`{"username":"local-user","password":"a-long-local-password"}`. Keep cookies
(`credentials: "same-origin"`), retain the returned CSRF token in memory and add
`X-CSRF-Token` to mutations. Never put passwords or session tokens in URLs/logs.
GET `/auth/session` restores identity; GET `/auth/csrf` rotates a token after reload.
POST `/auth/logout` revokes the session. DELETE `/auth/account` deletes guest or
account data; 202 means cancellation/deletion is pending. Session 401 clears local
resource state and returns to login/guest entry; never display cached private data
under a different session. Accounts and guests do not merge automatically.

## Screens and workflows

| Route responsibility | Actual endpoint(s) under `/api/v1` | Behavior |
|---|---|---|
| Projects | POST/GET `/projects`; GET/PATCH/DELETE `/projects/{id}` | PATCH body `{"name":"New name"}`; list limit/offset; deleting busy project returns 409 |
| Demo | POST `/datasets/demo` | Body `{"name":"Demo"}`; returns new project and metadata |
| Upload | POST `/datasets` | JSON project_id, csv, target, strategy, optional group/time/seed; validates before storing |
| Dataset | GET `/datasets/{id}` | project_id query required; metadata only |
| Preview | GET `/datasets/{id}/preview` | reviewed=true and limit 1–20; raw sensitive rows, no automatic display |
| Versions | GET `/datasets/{id}/versions`; GET `/datasets/{id}/export` | export reconstruction requires reviewed=true; comparison is `/datasets/{id}/compare/{other_id}` |
| Derivation | POST `/interventions/preview`, `/interventions/apply` | project_id, version_id, typed plan; apply requires reviewed=true |
| Learned preprocessing | POST `/datasets/{id}/preprocessing`; GET `/preprocessing/{id}` | ordered features, imputation and scaling; fit training only |
| Transformed preview | POST `/preprocessing/{id}/preview` | project_id/version_id/reviewed query; bounded raw values |
| Search | POST `/plans/search` | project_id/version_id; bounded measured structural candidates, review only |
| Analyze | POST `/analyses` | project_id, version_id, engines; returns queued job |
| Job | GET `/jobs/{id}`; POST `/jobs/{id}/cancel` | project_id query; nullable error/result_id/experiment_id |
| Findings | GET `/analyses/{id}`, `/findings`, `/health`, `/recommendations` | summary by default; detailed review required to see evidence/record IDs |
| Experiment | POST `/experiments`; GET `/experiments/{id}` | authorized=false previews; true returns job and experiment_id; poll job first |
| Reports | GET `/reports`; GET/DELETE `/reports/{analysis_id}` | project_id; export format json/markdown/engine-csv; privacy summary/redacted/detailed |
| Dataset deletion | DELETE `/datasets/{id}` | removes lineage and conservatively clears project-derived results/jobs |

Use OpenAPI paths as authoritative when composing full version/compare URLs. Lists
use limit 1–100 and nonnegative offset. Empty lists are normal, not backend failures.
Unsupported engine statuses must remain visible; never replace missing measurements
with zero. Recommendations refer to measured findings and authorize no mutations.

For example, after demo creation submit
`{"project_id":"<returned id>","version_id":"<returned id>","engines":["profile","leakage"]}`
to `/analyses`. Poll the returned job with the same project_id every 1–2 seconds;
back off on 429. Events contain sequence and actual completed engine/fit counts.
They do not predict remaining runtime. queued → running → completed/failed/cancelled
or interrupted. Cancelling running work sets cancel_requested while state remains
running until a computation boundary. Do not label that request as cancelled early.
A completed job's result_id points to the persisted analysis or experiment result;
use experiment_id to retrieve experiment metadata/outcomes. Restart interruption is
not success and requires an explicit new submission. Identical active experiment
requests return the same job; completed requests may be deliberately rerun.

## Reports, errors and presentation

Report JSON schema 2.0 retains existing fields and adds computed summary tables,
health coverage/recommendation series and execution metadata. Full engine findings,
versions and experiment outcomes are retrieved separately; missing joins are listed
as unavailable, not fabricated. Chart values originate in actual health and engine
outputs. Health and priority scores are experimental heuristics. Display coverage
and unassessed dimensions alongside scores; strong predictors and suspected labels
remain review findings. Engine CSV and Markdown are deliberately summary exports.
Owner-only detailed JSON provides evidence. CSV cells in this export are fixed
engine/status tokens; arbitrary user values are not exported as spreadsheet formulas.

Errors use `{"error":{"code":"...","message":"..."}}`; validation returns
invalid_request (422), session401, CSRF/origin403, ownership404, busy409, size413,
rate/queue429. Preserve X-Request-ID for support, not raw requests. No stack trace
or local path should be shown. Report previews are explicitly privacy-sensitive.
Exports use response bytes and a safe generated download name; do not put dataset
names in HTML without escaping. No frontend was implemented in this milestone.
