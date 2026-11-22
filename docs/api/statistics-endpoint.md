# Teacher usage statistics

`GET /api/users/me/statistics` requires the existing Supabase bearer token. It takes no parameters. The caller's JWT and `exam_sessions` ownership determine the result.

The response contains nonnegative integers for `total_sessions`, `in_progress_sessions`, `approved_not_exported_sessions`, and `exported_sessions`. The required `by_status` object contains these buckets:

- In progress: `draft`, `blueprinted`, `configured`, `generating`, `partial_generated`, `generated`, and `reviewed`.
- Final approval pending export: `approved`.
- Export package completed: `exported`.
- Remaining buckets: `failed` and `unknown` (null or unrecognized status).

The total is the sum of every bucket. Each retained session, including each retained clone, contributes once across all dates. An empty account returns all zeros. The result uses one PostgreSQL statement snapshot. Export status records package completion. Download activity is outside this metric.

Successful responses are private and carry `Cache-Control: private, no-store`. Invalid credentials follow existing auth handling. An unavailable or invalid database result returns 503. The current CRUD rate limit applies.

Apply the statistics RPC migration before deploying the route and page. Verify execution as two authenticated test identities and verify that anonymous execution fails.

Gemini usage is excluded because Stage 2 counts reservations before dispatch and Stage 3 uses a separate budget. The stored session retry counter lacks a verified increment contract.
