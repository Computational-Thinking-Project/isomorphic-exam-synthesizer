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
  confirmed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
-- 3. AUTOMATIC GOOGLE OAUTH USER SYNC TRIGGER (SEC-09)
-- ------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.users (id, email, name)
  VALUES (
    new.id,
    new.email,
    COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email)
  )
  ON CONFLICT (id) DO UPDATE 
    SET email = EXCLUDED.email, 
        name = EXCLUDED.name;
  RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ------------------------------------------------------------------------------
-- 4. ROW-LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------

-- Enable RLS on all 10 tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.question_blueprints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generation_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.version_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.answer_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;

-- 4.1. users
CREATE POLICY "Users can manage own profile" ON public.users
  FOR ALL USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- 4.2. exam_sessions
CREATE POLICY "Users can manage own exam sessions" ON public.exam_sessions
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 4.3. source_questions
CREATE POLICY "Users can manage source questions in their sessions" ON public.source_questions
  FOR ALL USING (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  ) WITH CHECK (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  );

-- 4.4. question_blueprints
CREATE POLICY "Users can manage blueprints in their questions" ON public.question_blueprints
  FOR ALL USING (
    source_question_id IN (
      SELECT sq.id FROM public.source_questions sq
      JOIN public.exam_sessions s ON sq.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  ) WITH CHECK (
    source_question_id IN (
      SELECT sq.id FROM public.source_questions sq
      JOIN public.exam_sessions s ON sq.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  );

-- 4.5. generation_configs
CREATE POLICY "Users can manage generation configs in their sessions" ON public.generation_configs
  FOR ALL USING (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  ) WITH CHECK (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  );

-- 4.6. exam_versions
CREATE POLICY "Users can manage exam versions in their sessions" ON public.exam_versions
  FOR ALL USING (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  ) WITH CHECK (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  );

-- 4.7. version_questions
CREATE POLICY "Users can manage version questions in their versions" ON public.version_questions
  FOR ALL USING (
    version_id IN (
      SELECT ev.id FROM public.exam_versions ev
      JOIN public.exam_sessions s ON ev.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  ) WITH CHECK (
    version_id IN (
      SELECT ev.id FROM public.exam_versions ev
      JOIN public.exam_sessions s ON ev.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  );

-- 4.8. answer_keys
CREATE POLICY "Users can manage answer keys in their versions" ON public.answer_keys
  FOR ALL USING (
    version_id IN (
      SELECT ev.id FROM public.exam_versions ev
      JOIN public.exam_sessions s ON ev.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  ) WITH CHECK (
    version_id IN (
      SELECT ev.id FROM public.exam_versions ev
      JOIN public.exam_sessions s ON ev.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  );

-- 4.9. review_logs
CREATE POLICY "Users can view review logs of their version questions" ON public.review_logs
  FOR ALL USING (
    version_question_id IN (
      SELECT vq.id FROM public.version_questions vq
      JOIN public.exam_versions ev ON vq.version_id = ev.id
      JOIN public.exam_sessions s ON ev.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  );

-- 4.10. security_events (Immutable Audit Log)
-- Read only own events; Insert only by service_role; Update & Delete completely disallowed
CREATE POLICY "Users can view own security events" ON public.security_events
  FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Service role can insert security events" ON public.security_events
  FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- ------------------------------------------------------------------------------
-- 5. STORAGE BUCKETS & RLS
-- ------------------------------------------------------------------------------

-- Insert private buckets
INSERT INTO storage.buckets (id, name, public)
VALUES 
  ('exam-raw-files', 'exam-raw-files', FALSE),
  ('exam-export-bundles', 'exam-export-bundles', FALSE)
ON CONFLICT (id) DO NOTHING;

-- Storage Objects Access Policy
CREATE POLICY "User storage isolated access" ON storage.objects
  FOR ALL USING (
    bucket_id IN ('exam-raw-files', 'exam-export-bundles')
    AND (storage.foldername(name))[1] IN (
      SELECT id::text FROM public.exam_sessions WHERE user_id = auth.uid()
    )
  ) WITH CHECK (
    bucket_id IN ('exam-raw-files', 'exam-export-bundles')
    AND (storage.foldername(name))[1] IN (
      SELECT id::text FROM public.exam_sessions WHERE user_id = auth.uid()
    )
  );
