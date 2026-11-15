-- ==============================================================================
-- Migration 003b: Baseline Schema Reconciliation (Fix Issue #75)
-- Purpose: Bridge the gap between the initial 5-table deployment (users, exam_sessions,
-- source_questions, question_blueprints, exam_versions) and the prerequisites
-- required by migrations 004 through 022 without re-running non-idempotent schema.sql.
-- ==============================================================================

BEGIN;

-- 1. Verify prerequisite 5-table baseline existence
DO $$ BEGIN
  IF to_regclass('public.users') IS NULL
     OR to_regclass('public.exam_sessions') IS NULL
     OR to_regclass('public.source_questions') IS NULL
     OR to_regclass('public.question_blueprints') IS NULL
     OR to_regclass('public.exam_versions') IS NULL THEN
    RAISE EXCEPTION '003b: prerequisite 5-table baseline is missing';
  END IF;
END $$;

-- 2. Validate or create required enum types
DO $$
DECLARE
  v_missing text[];
BEGIN
  IF to_regtype('public.question_status') IS NOT NULL THEN
    SELECT array_agg(expected_label) INTO v_missing
    FROM unnest(ARRAY['pending_review', 'approved', 'rejected', 'regenerating']) AS expected_label
    WHERE expected_label NOT IN (
      SELECT enumlabel FROM pg_enum
      WHERE enumtypid = 'public.question_status'::regtype
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
      RAISE EXCEPTION '003b: existing question_status enum is incompatible, missing labels: %', v_missing;
    END IF;
  ELSE
    CREATE TYPE public.question_status AS ENUM (
      'pending_review', 'approved', 'rejected', 'regenerating'
    );
  END IF;
END $$;

DO $$
DECLARE
  v_missing text[];
BEGIN
  IF to_regtype('public.review_action_type') IS NOT NULL THEN
    SELECT array_agg(expected_label) INTO v_missing
    FROM unnest(ARRAY['ACCEPT', 'REJECT', 'REVERT', 'REJECT_FAILED']) AS expected_label
    WHERE expected_label NOT IN (
      SELECT enumlabel FROM pg_enum
      WHERE enumtypid = 'public.review_action_type'::regtype
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
      RAISE EXCEPTION '003b: existing review_action_type enum is incompatible, missing labels: %', v_missing;
    END IF;
  ELSE
    CREATE TYPE public.review_action_type AS ENUM (
      'ACCEPT', 'REJECT', 'REVERT', 'REJECT_FAILED'
    );
  END IF;
END $$;

-- 3. Targeted validation of existing objects if present
DO $$
BEGIN
  -- generation_configs validation
  IF to_regclass('public.generation_configs') IS NOT NULL THEN
    IF (SELECT relkind FROM pg_class WHERE oid = 'public.generation_configs'::regclass) <> 'r' THEN
      RAISE EXCEPTION '003b: public.generation_configs exists but is not a regular table';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'generation_configs'
        AND column_name = 'session_id' AND udt_name = 'uuid'
    ) THEN
      RAISE EXCEPTION '003b: incompatible generation_configs: session_id UUID column missing';
    END IF;
  END IF;

  -- version_questions validation
  IF to_regclass('public.version_questions') IS NOT NULL THEN
    IF (SELECT relkind FROM pg_class WHERE oid = 'public.version_questions'::regclass) <> 'r' THEN
      RAISE EXCEPTION '003b: public.version_questions exists but is not a regular table';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'version_questions'
        AND column_name = 'version_id' AND udt_name = 'uuid'
    ) OR NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'version_questions'
        AND column_name = 'source_question_id' AND udt_name = 'uuid'
    ) THEN
      RAISE EXCEPTION '003b: incompatible version_questions: missing required version_id or source_question_id columns';
    END IF;
  END IF;

  -- answer_keys validation
  IF to_regclass('public.answer_keys') IS NOT NULL THEN
    IF (SELECT relkind FROM pg_class WHERE oid = 'public.answer_keys'::regclass) <> 'r' THEN
      RAISE EXCEPTION '003b: public.answer_keys exists but is not a regular table';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'answer_keys'
        AND column_name = 'version_id' AND udt_name = 'uuid'
    ) THEN
      RAISE EXCEPTION '003b: incompatible answer_keys: missing version_id UUID column';
    END IF;
  END IF;

  -- review_logs validation
  IF to_regclass('public.review_logs') IS NOT NULL THEN
    IF (SELECT relkind FROM pg_class WHERE oid = 'public.review_logs'::regclass) <> 'r' THEN
      RAISE EXCEPTION '003b: public.review_logs exists but is not a regular table';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'review_logs'
        AND column_name = 'version_question_id' AND udt_name = 'uuid'
    ) THEN
      RAISE EXCEPTION '003b: incompatible review_logs: missing version_question_id UUID column';
    END IF;
  END IF;

  -- security_events validation
  IF to_regclass('public.security_events') IS NOT NULL THEN
    IF (SELECT relkind FROM pg_class WHERE oid = 'public.security_events'::regclass) <> 'r' THEN
      RAISE EXCEPTION '003b: public.security_events exists but is not a regular table';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'security_events'
        AND column_name = 'event_type'
    ) THEN
      RAISE EXCEPTION '003b: incompatible security_events: missing event_type column';
    END IF;
  END IF;
END $$;

-- 4. Create missing baseline tables required by 004, 005, and 006
CREATE TABLE IF NOT EXISTS public.generation_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  n_versions INT NOT NULL CHECK (n_versions BETWEEN 1 AND 4),
  active_variation_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
  ordering_preferences JSONB NOT NULL DEFAULT '{"shuffle_questions": false, "shuffle_options": false}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_configs_session_id UNIQUE (session_id)
);

CREATE TABLE IF NOT EXISTS public.version_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES public.exam_versions(id) ON DELETE CASCADE,
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  content TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_key TEXT NOT NULL,
  solution_md TEXT,
  canonical_question_no INT,
  canonical_options JSONB,
  canonical_correct_key TEXT,
  canonical_solution_md TEXT,
  status public.question_status NOT NULL DEFAULT 'pending_review',
  has_warning BOOLEAN NOT NULL DEFAULT FALSE,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  regenerated_from_id UUID REFERENCES public.version_questions(id) ON DELETE SET NULL,
  is_reverted BOOLEAN NOT NULL DEFAULT FALSE,
  regeneration_id UUID NULL,
  validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question 
  ON public.version_questions (version_id, source_question_id) 
  WHERE is_current = TRUE;

CREATE TABLE IF NOT EXISTS public.answer_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES public.exam_versions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  correct_option TEXT NOT NULL,
  display_no INT,
  display_correct_key TEXT,
  canonical_question_no INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.review_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_question_id UUID NOT NULL REFERENCES public.version_questions(id) ON DELETE CASCADE,
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.users(id),
  action_type public.review_action_type NOT NULL,
  reason TEXT,
  latency_ms INT,
  api_calls_used INT,
  regenerated_from_id UUID REFERENCES public.version_questions(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.security_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES public.exam_sessions(id) ON DELETE SET NULL,
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'WARN',
  sanitized_detail JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Row-Level Security & Policies
ALTER TABLE public.generation_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.version_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.answer_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;

-- Owner-read SELECT policy on generation_configs (required by GET /api/sessions/{session_id})
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'generation_configs'
      AND policyname IN ('generation_configs_owner_read', 'Users can manage generation configs in their sessions')
  ) THEN
    CREATE POLICY generation_configs_owner_read
    ON public.generation_configs
    FOR SELECT TO authenticated
    USING (
      EXISTS (
        SELECT 1 FROM public.exam_sessions s
        WHERE s.id = generation_configs.session_id
          AND s.user_id = auth.uid()
      )
    );
  END IF;
END $$;

-- Policies on security_events: owner read-only, service_role insert-only
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'security_events'
      AND policyname = 'Users can view own security events'
  ) THEN
    CREATE POLICY "Users can view own security events"
    ON public.security_events
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'security_events'
      AND policyname = 'Service role can insert security events'
  ) THEN
    CREATE POLICY "Service role can insert security events"
    ON public.security_events
    FOR INSERT TO service_role
    WITH CHECK (auth.role() = 'service_role');
  END IF;
END $$;

-- 6. Role Grants / Least Privilege Enforcement
-- Deny public and anon access to private schema tables
REVOKE ALL ON TABLE public.generation_configs, public.version_questions,
  public.answer_keys, public.review_logs, public.security_events
  FROM PUBLIC, anon;

-- Revoke direct DML from authenticated to prevent privilege regression or undoing later hardening (009/015)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.generation_configs, public.version_questions,
  public.answer_keys, public.review_logs, public.security_events
  FROM authenticated;

-- Grant verified minimum direct read privileges to authenticated
GRANT SELECT ON TABLE public.generation_configs, public.version_questions,
  public.answer_keys, public.review_logs, public.security_events
  TO authenticated;

-- Grant trusted service operations to service_role
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.generation_configs,
  public.version_questions, public.answer_keys, public.review_logs
  TO service_role;

GRANT SELECT, INSERT ON TABLE public.security_events TO service_role;

COMMIT;
