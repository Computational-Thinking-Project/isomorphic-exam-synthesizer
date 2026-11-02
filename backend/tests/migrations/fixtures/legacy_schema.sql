-- Snapshot of table definitions from dev 32d7644, before TASK-302.
-- ==============================================================================
-- Isomorphic Exam Synthesizer - Database Initialization Schema (TASK-002)
-- Targets: PostgreSQL 15+ on Supabase (Region: Southeast Asia / Singapore)
-- Features: 10 Tables, Strict Relational RLS, Google OAuth Trigger, Invariant Index
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. ENUM TYPES
-- ------------------------------------------------------------------------------

DO $$ BEGIN
  CREATE TYPE public.session_status AS ENUM (
    'draft',
    'blueprinted',
    'configured',
    'generating',
    'partial_generated',
    'generated',
    'reviewed',
    'approved',
    'exported',
    'failed'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  CREATE TYPE public.question_status AS ENUM (
    'pending_review',
    'approved',
    'rejected',
    'regenerating'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  CREATE TYPE public.review_action_type AS ENUM (
    'ACCEPT',
    'REJECT',
    'REVERT',
    'REJECT_FAILED'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

-- ------------------------------------------------------------------------------
-- 2. TABLES DEFINITION
-- ------------------------------------------------------------------------------

-- Table 1: Users (mirrors auth.users)
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 2: Exam Sessions (Master entity for an exam creation session)
CREATE TABLE IF NOT EXISTS public.exam_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT 'Toán',
  grade INT NOT NULL DEFAULT 12,
  status public.session_status NOT NULL DEFAULT 'draft',
  gemini_call_count INT NOT NULL DEFAULT 0,
  retry_count INT NOT NULL DEFAULT 0,
  gemini_review_calls INT NOT NULL DEFAULT 0,
  approved_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 3: Source Questions (Ingested from original document)
CREATE TABLE IF NOT EXISTS public.source_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  raw_content TEXT NOT NULL,
  options JSONB NOT NULL, -- e.g. {"A": "...", "B": "...", "C": "...", "D": "..."}
  correct_key TEXT NOT NULL, -- "A", "B", "C", or "D"
  solution_md TEXT,
  has_missing_answer BOOLEAN NOT NULL DEFAULT FALSE,
  has_security_warning BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 4: Question Blueprints (Extracted parameter domains & invariant rules)
CREATE TABLE IF NOT EXISTS public.question_blueprints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  variables JSONB NOT NULL DEFAULT '{}'::jsonb,
  domains JSONB NOT NULL DEFAULT '{}'::jsonb,
  invariants JSONB NOT NULL DEFAULT '[]'::jsonb,
  variation_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
  rule_summary TEXT,
  is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
  extraction_source TEXT NOT NULL DEFAULT 'AI_PIPELINE',
  confirmed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id)
);

-- Table 5: Generation Configs (Stage 2 session preferences)
CREATE TABLE IF NOT EXISTS public.generation_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  n_versions INT NOT NULL CHECK (n_versions BETWEEN 1 AND 4),
  active_variation_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
  ordering_preferences JSONB NOT NULL DEFAULT '{"shuffle_questions": true, "shuffle_options": true}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 6: Exam Versions (Each generated variant code: e.g., 101, 102, 103, 104)
CREATE TABLE IF NOT EXISTS public.exam_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  version_code TEXT NOT NULL,
  shuffle_seed TEXT,
  permutations JSONB,
  is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 7: Version Questions (Variant questions with Canonical Data Model)
CREATE TABLE IF NOT EXISTS public.version_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES public.exam_versions(id) ON DELETE CASCADE,
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  content TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_key TEXT NOT NULL,
  solution_md TEXT,
  canonical_question_no INT NOT NULL,
  canonical_options JSONB NOT NULL,
  canonical_correct_key TEXT NOT NULL,
  canonical_solution_md TEXT,
  status public.question_status NOT NULL DEFAULT 'pending_review',
  has_warning BOOLEAN NOT NULL DEFAULT FALSE,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  regenerated_from_id UUID REFERENCES public.version_questions(id) ON DELETE SET NULL,
  is_reverted BOOLEAN NOT NULL DEFAULT FALSE,
  validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Invariant Constraint: At any time, exactly one current record exists per version/source pair
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question
  ON public.version_questions (version_id, source_question_id)
  WHERE is_current = TRUE;

-- Table 8: Answer Keys (Matrix of correct options after shuffling)
CREATE TABLE IF NOT EXISTS public.answer_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES public.exam_versions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  correct_option TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 9: Review Logs (Audit trail of teacher review decisions)
CREATE TABLE IF NOT EXISTS public.review_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_question_id UUID NOT NULL REFERENCES public.version_questions(id) ON DELETE CASCADE,
  action_type public.review_action_type NOT NULL,
  reason TEXT,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 10: Security Events (Immutable Audit Log for prompt injection / security warnings)
CREATE TABLE IF NOT EXISTS public.security_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES public.exam_sessions(id) ON DELETE SET NULL,
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL, -- e.g. 'PROMPT_INJECTION_DETECTED', 'RATE_LIMIT_EXCEEDED'
  severity TEXT NOT NULL DEFAULT 'WARN', -- 'INFO', 'WARN', 'CRITICAL'
  sanitized_detail JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
