-- ==============================================================================
-- Migration 003b: Baseline Schema Reconciliation (Fix Issue #75)
-- Purpose: Bridge the gap between the initial 5-table deployment (users, exam_sessions,
-- source_questions, question_blueprints, exam_versions) and the prerequisites
-- required by migrations 004 through 022 without re-running non-idempotent schema.sql.
-- ==============================================================================

BEGIN;

-- 1. Ensure required enum types exist
DO $$ BEGIN
  CREATE TYPE public.question_status AS ENUM (
    'pending_review', 'approved', 'rejected', 'regenerating'
  );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
  CREATE TYPE public.review_action_type AS ENUM (
    'ACCEPT', 'REJECT', 'REVERT', 'REJECT_FAILED'
  );
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- 2. Create missing baseline tables required by 004, 005, and 006
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

-- 3. Row-Level Security
ALTER TABLE public.generation_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.version_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.answer_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;

-- 4. Role Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.generation_configs, public.version_questions, public.answer_keys, public.review_logs TO authenticated, service_role;
GRANT SELECT, INSERT ON TABLE public.security_events TO authenticated, service_role;

COMMIT;
