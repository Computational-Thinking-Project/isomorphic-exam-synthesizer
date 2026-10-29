-- ==============================================================================
-- Migration 004: Stage 3 Review Lifecycle, Invariants, and Regeneration Idempotency
-- Tasks: TASK-301 (API Thẩm định 1-1) & TASK-302 (Canonical Schema Migration)
-- Targets: PostgreSQL 15+ (Supabase)
-- Safe & Idempotent: can be executed repeatedly without errors
-- ==============================================================================

-- 1. Ensure Columns on exam_sessions
ALTER TABLE public.exam_sessions
  ADD COLUMN IF NOT EXISTS gemini_review_calls INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL;

-- 2. Ensure Columns on version_questions
ALTER TABLE public.version_questions
  ADD COLUMN IF NOT EXISTS canonical_question_no INT,
  ADD COLUMN IF NOT EXISTS canonical_options JSONB,
  ADD COLUMN IF NOT EXISTS canonical_correct_key TEXT,
  ADD COLUMN IF NOT EXISTS canonical_solution_md TEXT,
  ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS regenerated_from_id UUID REFERENCES public.version_questions(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS is_reverted BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS regeneration_id UUID NULL,
  ADD COLUMN IF NOT EXISTS status public.question_status NOT NULL DEFAULT 'pending_review',
  ADD COLUMN IF NOT EXISTS validation_report JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 3. Invariant Constraint: At any time, exactly one current record exists per version/source pair
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question 
  ON public.version_questions (version_id, source_question_id) 
  WHERE is_current = TRUE;

-- 4. Idempotency Constraint: Unique non-null regeneration_id to guarantee zero double-insert
CREATE UNIQUE INDEX IF NOT EXISTS uq_version_questions_regeneration 
  ON public.version_questions (regeneration_id) 
  WHERE regeneration_id IS NOT NULL;

-- 5. Stale Guard Performance Index: Fast lookup for stale regenerating variants
CREATE INDEX IF NOT EXISTS idx_version_questions_stale_guard 
  ON public.version_questions (status, updated_at) 
  WHERE status = 'regenerating';

-- 6. Ensure review_logs table structure
CREATE TABLE IF NOT EXISTS public.review_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  version_question_id UUID NULL REFERENCES public.version_questions(id) ON DELETE SET NULL,
  user_id UUID NOT NULL REFERENCES public.users(id),
  action_type public.review_action_type NOT NULL,
  reason TEXT NULL,
  api_calls_used INT NULL,
  regenerated_from_id UUID NULL REFERENCES public.version_questions(id) ON DELETE RESTRICT,
  latency_ms INT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index on review_logs
CREATE INDEX IF NOT EXISTS idx_review_logs_session_created 
  ON public.review_logs (session_id, created_at DESC);

