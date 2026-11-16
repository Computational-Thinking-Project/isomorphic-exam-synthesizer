# Issue #75 — ACL remediation and deployment handoff (M2)

- Role: author; workflow v0.1 proposed, INPUT-20261109; docs source 7b7387f.
- Source: Issue75 and user-approved implementation plan; W4_ASSIGNMENT/DB0 context.
- Base: 72507c84019021deb42f3668ab893edfdce248c0; branch fix/issue-75-users-acl.
- Reviewer: TBD, not assigned by this agent. ETA: not assigned.
- Authority: local patch/tests/docs. No Production SQL, deployment, messaging,
  approval, merge or issue closure. Existing UI checkout preserved.
- Scope: 023 ACL only, regression fixture and proposed 19-step operator package.
  No API, Auth trigger, RLS redesign, 020 inclusion or edits to 18 old SQL blobs.

## Implementation order
1. Reproduce unsafe users grants in disposable PostgreSQL.
2. Revoke targeted grants transactionally, version-guard MAINTAIN and reject
   residual effective grants; preserve SELECT/service_role/Auth/RLS.
3. Test PostgreSQL15 and17, full candidate, replay, failure atomicity, A/B and Auth.
4. Review immutable final patch separately; run applicable static/API regressions.
5. Hand off proposed manifest and operator runbook. Deployment stays NO-GO.

## Inputs (single tracking location)
| ID | Provider → consumer | Required evidence | Status / next step |
|---|---|---|---|
| I-ISS75-01 | DB owner → operator/reviewer | Version, actual catalog/ledger/grants, compatible data | Requested in plan; not delivered; owner confirmation/ETA pending |
| I-ISS75-02 | Runtime owner → operator/reviewer | Running SHA/image and manifest compatibility, release route | Not delivered; owner confirmation/ETA pending |
| I-ISS75-03 | DB owner/reviewer → operator | Backup/isolated restore, representative rehearsal, independent approval, approved 19 steps/operator, explicit GO | Pending; deployment blocked |

## Checks / handoff
Author validation (2026-11-15): focused final suite 14/14 PASS on PostgreSQL15 (76.950s) and 14/14 PASS on PostgreSQL17 (75.633s). API session/confirmation/auth 205 PASS (mock, 3.08s); Ruff PASS; mypy 114 files PASS; git diff --check PASS; original 18 manifest checksums unchanged. Broader PostgreSQL15 regressions: 63 run, 62 PASS / 1 optional worker SKIP, 253.856s. Modules: test_w4_baseline_chain, test_w4_source_readiness_config, test_stage3_schema, test_source_confirmation_revision (RUN_POSTGRES_MIGRATION_TESTS=1, PYTHONPATH=backend;backend/tests/migrations, python -X utf8 -m unittest MODULES -q). The skip requires a separately pinned worker checkout and is not worker/live acceptance evidence. Synthetic fixtures and mocked API tests
do not establish Production readiness. Follow the runbook for actual acceptance.
Issue75 remains open. No cloud mutation, push or PR publication is claimed.


Commands: RUN_POSTGRES_MIGRATION_TESTS=1, PYTHONPATH=backend,
POSTGRES_MIGRATION_TEST_IMAGE=postgres:15-alpine or postgres:17-alpine;
python -X utf8 -m unittest discover -s backend/tests/migrations
-p test_issue75_baseline_reconciliation.py -v.
API: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python -m pytest
-p pytest_asyncio.plugin backend/tests/api/test_sessions.py
backend/tests/api/test_confirm_source.py backend/tests/api/test_auth.py -q.
Static: python -m ruff check backend/app scripts/blueprint and both changed tests;
python -m mypy backend/app --ignore-missing-imports; git diff --check.

Initial 13-case runs failed on both versions because PostgreSQL table-level
REVOKE REFERENCES also removed the same grantee's column grant. Corrected the
fixture to test residual PUBLIC column grants; T17 separately verifies the
direct-column removal behavior and missing-SELECT atomic rollback. No assertion
was weakened: effective column REFERENCES must be false on success.

Separate author bypass/regression pass: reviewed direct grants, PUBLIC,
inherited service role and column grants, version branches, missing SELECT,
Auth SECURITY DEFINER trigger, and replay boundaries. This is self-review,
not independent review or GitHub Approve. assess-patch-risk/independent final
review and Production acceptance remain pending. No browser/cloud work performed.
