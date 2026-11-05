-- Migration 004: Confirm Source Artifacts RPC — inventory and reference (TASK-204 / Q03)
--
-- PURPOSE
--   This file documents the canonical RPC surface that the Python backend uses
--   for source confirmation (Stage 1 → Stage 2 boundary).  The authoritative
--   implementation lives in migration 006_stage3_review_and_shuffle.sql which
--   must be applied before this inventory is relevant.
--
--   Run order (ascending):
--     002_replace_source_questions_rpc.sql      ← replace_source_questions
--     003_confirm_exam_source_rpc.sql           ← legacy confirm_exam_source (DEPRECATED)
--     004_confirm_source_artifacts_rpc.sql      ← THIS FILE (inventory / guard)
--     006_stage3_review_and_shuffle.sql         ← confirm_source_artifacts and all
--                                                   canonical artifact RPCs (authoritative)
--
-- RPC INVENTORY (from 006, service_role-only unless noted)
--
--   confirm_source_artifacts(UUID, UUID, UUID, TIMESTAMPTZ, JSONB) → JSONB
--     Atomically locks session, verifies owner, checks draft state, compares
--     p_expected_updated_at against exam_sessions.updated_at (revision check),
--     validates per-question fingerprints under lock, inserts
--     source_artifact_confirmations/revisions/heads in one transaction, stamps
--     blueprinted status, and returns a full SourceConfirmation receipt.
--     Idempotent: same confirmation_id + same payload → replayed=true receipt.
--     Error codes: ARTIFACT_STALE (revision mismatch), ARTIFACT_SOURCE_MISMATCH,
--       ARTIFACT_OWNER_MISMATCH, ARTIFACT_LOCKED, ARTIFACT_IDEMPOTENCY_CONFLICT.
--
--   get_source_artifacts(UUID) → JSONB
--     Read-only: authenticated (owner) or service_role.
--     Returns confirmation receipt + pending_source_question_ids + production states.
--     Raises ARTIFACT_STALE when live source_questions diverge from confirmed revision.
--     Raises ARTIFACT_NOT_FOUND when session has no confirmation or owner mismatch.
--
--   claim_source_production(UUID, UUID, UUID) → JSONB      [service_role]
--   fail_source_production(UUID, UUID, UUID, TEXT) → JSONB [service_role]
--   publish_canonical_blueprint(UUID, JSONB) → JSONB        [service_role]
--
-- GRANTS SUMMARY (enforced by 006)
--   confirm_source_artifacts  → service_role only
--   get_source_artifacts      → authenticated + service_role
--   claim/fail/publish        → service_role only
--   source_artifact_* tables  → no direct access (RLS enabled, all denied)
--
-- INTEGRATION TEST ENVIRONMENT (Q03)
--   See backend/tests/migrations/README.md for setup instructions.
--   Key requirements:
--     1. Apply migrations 002, 003, 006 in order on a fresh PostgreSQL 15 instance.
--     2. Seed auth.users, public.users, exam_sessions, source_questions.
--     3. Set FAKE_AI_PROVIDER=1 (or use the MockAIClient fixture) to prevent
--        any outbound AI requests during integration tests.
--     4. Confirm RUN_POSTGRES_MIGRATION_TESTS=1 before running test_source_artifacts.py.
--
-- FAKE AI PROVIDER (Q03)
--   To block real AI calls in integration tests, set environment variables:
--     GEMINI_API_KEYS=""    (empty → BlueprintService falls back to MockAIClient)
--   OR monkeypatch source_artifacts.blueprint_service to return None (disables
--   background production) and use a SqlClient-backed Extractor returning fixture
--   blueprints from backend/tests/fixtures/ai_pipeline.json.
--
-- This file is intentionally a documentation/guard migration; it has no DDL.
-- If applied to a database that already has the 006 objects, it is a no-op.

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'confirm_source_artifacts'
  ) THEN
    RAISE EXCEPTION
      'confirm_source_artifacts RPC not found — apply 006_stage3_review_and_shuffle.sql first';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'get_source_artifacts'
  ) THEN
    RAISE EXCEPTION
      'get_source_artifacts RPC not found — apply 006_stage3_review_and_shuffle.sql first';
  END IF;
END $$;

