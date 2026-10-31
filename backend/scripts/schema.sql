-- ==============================================================================
-- Isomorphic Exam Synthesizer - Database Initialization Schema (TASK-002)
-- Targets: PostgreSQL 15+ on Supabase (Region: Southeast Asia / Singapore)
-- Features: 10 Tables, Strict Relational RLS, Google OAuth Trigger, Invariant Index
-- After initialization, apply backend/migrations in order. Migration 006 installs
-- canonical immutability and legacy/display answer-key compatibility triggers.
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
  regeneration_id UUID NULL,
  validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one current record per version/source pair; atomic lifecycle RPCs must
-- additionally ensure that replacement failures do not leave zero current rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question 
  ON public.version_questions (version_id, source_question_id) 
  WHERE is_current = TRUE;

-- Table 8: Answer Keys (Matrix of correct options after shuffling)
CREATE TABLE IF NOT EXISTS public.answer_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id UUID NOT NULL REFERENCES public.exam_versions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  correct_option TEXT NOT NULL,
  display_no INT NOT NULL,
  display_correct_key TEXT NOT NULL,
  canonical_question_no INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table 9: Review Logs (Audit trail of teacher review decisions)
CREATE TABLE IF NOT EXISTS public.review_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_question_id UUID NOT NULL REFERENCES public.version_questions(id) ON DELETE CASCADE,
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  -- Nullable storage permits unknown historical actors on upgraded databases.
  -- Fresh databases have no such history: the CHECK below requires an actor.
  -- Migration 006 uses CHECK ... NOT VALID to retain pre-existing NULLs only.
  user_id UUID REFERENCES public.users(id),
  action_type public.review_action_type NOT NULL,
  reason TEXT,
  latency_ms INT,
  api_calls_used INT,
  regenerated_from_id UUID REFERENCES public.version_questions(id),
  CONSTRAINT ck_review_logs_actor_required CHECK (user_id IS NOT NULL),
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
  ('exam-sources', 'exam-sources', FALSE),
  ('exam-export-bundles', 'exam-export-bundles', FALSE)
ON CONFLICT (id) DO NOTHING;

-- Storage Objects Access Policy
CREATE POLICY "User storage isolated access" ON storage.objects
  FOR ALL USING (
    bucket_id IN ('exam-raw-files', 'exam-sources', 'exam-export-bundles')
    AND (storage.foldername(name))[1] IN (
      SELECT id::text FROM public.exam_sessions WHERE user_id = auth.uid()
    )
  ) WITH CHECK (
    bucket_id IN ('exam-raw-files', 'exam-sources', 'exam-export-bundles')
    AND (storage.foldername(name))[1] IN (
      SELECT id::text FROM public.exam_sessions WHERE user_id = auth.uid()
    )
  );

-- ------------------------------------------------------------------------------
-- 6. STORED PROCEDURES / RPC FUNCTIONS (TASK-202 Atomic Replace)
-- ------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.replace_source_questions(
  p_session_id UUID,
  p_questions JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_role TEXT := COALESCE(
    current_setting('request.jwt.claim.role', true),
    (current_setting('request.jwt.claims', true)::jsonb ->> 'role')
  );
  v_q JSONB;
  v_count INT := 0;
BEGIN
  -- 1. Atomic row lock and session lookup
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Strict caller authorization
  IF auth.uid() IS NOT NULL THEN
    IF v_session_user_id != auth.uid() THEN
      RAISE EXCEPTION 'Access denied: not session owner' USING ERRCODE = '42501';
    END IF;
  ELSIF v_role = 'service_role' OR session_user IN ('postgres', 'supabase_admin') THEN
    NULL; -- Trusted internal backend service role or direct database administrator
  ELSE
    RAISE EXCEPTION 'Unauthorized: caller must be authenticated or have service role' USING ERRCODE = '42501';
  END IF;

  -- 3. State machine validation
  IF v_session_status != 'draft' THEN
    RAISE EXCEPTION 'Cannot ingest questions: session is not in draft status' USING ERRCODE = '22023';
  END IF;

  -- 4. Atomic cascade cleanup of existing blueprints and questions
  DELETE FROM public.question_blueprints
  WHERE source_question_id IN (
    SELECT id FROM public.source_questions WHERE session_id = p_session_id
  );

  DELETE FROM public.source_questions
  WHERE session_id = p_session_id;

  -- 5. Bulk insert validated questions
  FOR v_q IN SELECT * FROM jsonb_array_elements(p_questions)
  LOOP
    INSERT INTO public.source_questions (
      session_id,
      question_no,
      raw_content,
      options,
      correct_key,
      solution_md,
      has_missing_answer,
      has_security_warning
    ) VALUES (
      p_session_id,
      (v_q->>'question_no')::INT,
      v_q->>'raw_content',
      v_q->'options',
      v_q->>'correct_key',
      v_q->>'solution_md',
      COALESCE((v_q->>'has_missing_answer')::BOOLEAN, FALSE),
      COALESCE((v_q->>'has_security_warning')::BOOLEAN, FALSE)
    );
    v_count := v_count + 1;
  END LOOP;

  -- 6. Update session metadata timestamp
  UPDATE public.exam_sessions
  SET updated_at = now()
  WHERE id = p_session_id;

  RETURN jsonb_build_object('success', TRUE, 'count', v_count);
END;
$$;

-- Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) FROM anon;
GRANT EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) TO service_role;

-- Procedure: confirm_exam_source (TASK-205 Fix)
-- Purpose: Atomically lock exam session in draft state, verify questions count, verify concurrency/updated_at,
-- verify 100% of questions have active blueprints, lock blueprints with confirmed_at, and transition session
-- to 'blueprinted'. SEC-02 security warnings are handled via silent audit logging at the application layer
-- (ADR-004); this RPC no longer blocks confirmation when security warnings are present.
CREATE OR REPLACE FUNCTION public.confirm_exam_source(
  p_session_id UUID,
  p_expected_question_count INT,
  p_acknowledged_security_warnings BOOLEAN DEFAULT FALSE,
  p_expected_updated_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_session_updated_at TIMESTAMPTZ;
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
  v_current_count INT;
  v_missing_count INT;
  v_security_warning_count INT;
  v_now TIMESTAMPTZ := now();
  v_bp_count INT := 0;
BEGIN
  -- 1. Row lock session to prevent race conditions (e.g. concurrent confirm or re-ingest)
  SELECT user_id, status, updated_at INTO v_session_user_id, v_session_status, v_session_updated_at
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Strict caller authorization (session owner, service_role, or direct DBA)
  -- Uses session_user to prevent UID-less callers bypassing auth in SECURITY DEFINER
  IF auth.uid() IS NOT NULL THEN
    IF v_session_user_id != auth.uid() THEN
      RAISE EXCEPTION 'Access denied: not session owner' USING ERRCODE = '42501';
    END IF;
  ELSIF v_role = 'service_role' OR (v_role IS NULL AND session_user IN ('postgres', 'supabase_admin')) THEN
    NULL; -- Trusted internal backend service role or direct database administrator
  ELSE
    RAISE EXCEPTION 'Unauthorized: caller must be authenticated or have service role' USING ERRCODE = '42501';
  END IF;

  -- 3. State machine precondition: session must be in 'draft' status
  IF v_session_status != 'draft' THEN
    RAISE EXCEPTION 'Cannot confirm source: session is not in draft status (current: %)', v_session_status USING ERRCODE = '22023';
  END IF;

  -- 4. Concurrency check: session must not have been modified since read
  IF p_expected_updated_at IS NOT NULL AND v_session_updated_at != p_expected_updated_at THEN
    RAISE EXCEPTION 'Cannot confirm source: Session or source questions were modified concurrently (expected updated_at %, got %)', 
      p_expected_updated_at, v_session_updated_at USING ERRCODE = '22023';
  END IF;

  -- 5. Check question count, missing answers, and security warnings
  SELECT 
    COUNT(*), 
    COUNT(*) FILTER (WHERE has_missing_answer = TRUE),
    COUNT(*) FILTER (WHERE has_security_warning = TRUE)
  INTO v_current_count, v_missing_count, v_security_warning_count
  FROM public.source_questions
  WHERE session_id = p_session_id;

  IF v_current_count = 0 THEN
    RAISE EXCEPTION 'Cannot confirm source: session has no source questions' USING ERRCODE = '22023';
  END IF;

  IF p_expected_question_count IS NOT NULL AND v_current_count != p_expected_question_count THEN
    RAISE EXCEPTION 'Question count mismatch: expected %, found %', p_expected_question_count, v_current_count USING ERRCODE = '22023';
  END IF;

  IF v_missing_count > 0 THEN
    RAISE EXCEPTION 'Cannot confirm source: session has % questions with missing answers', v_missing_count USING ERRCODE = '22023';
  END IF;

  -- SEC-02 / ADR-004: Security warnings do not block confirmation (user-facing acknowledgment
  -- eliminated per ADR-004). The p_acknowledged_security_warnings parameter is retained for
  -- backward compatibility. When security warnings are present, a persistent audit record
  -- is atomically inserted into public.security_events.
  IF v_security_warning_count > 0 THEN
    INSERT INTO public.security_events (
      session_id,
      user_id,
      event_type,
      severity,
      sanitized_detail
    ) VALUES (
      p_session_id,
      v_session_user_id,
      'PROMPT_INJECTION_DETECTED',
      'WARN',
      jsonb_build_object(
        'action', 'confirm_source',
        'warning_questions_count', v_security_warning_count,
        'flagged_questions', (
          SELECT COALESCE(jsonb_agg(jsonb_build_object('id', id, 'question_no', question_no)), '[]'::jsonb)
          FROM public.source_questions
          WHERE session_id = p_session_id AND has_security_warning = TRUE
        ),
        'silent_audit', TRUE,
        'adr_version', 'ADR-004'
      )
    );
  END IF;

  -- 6. Lock blueprints: stamp confirmed_at and verify 100% of questions have an active blueprint
  WITH updated_bp AS (
    UPDATE public.question_blueprints
    SET confirmed_at = v_now, updated_at = v_now
    WHERE source_question_id IN (
      SELECT id FROM public.source_questions WHERE session_id = p_session_id
    )
    RETURNING id
  )
  SELECT COUNT(*) INTO v_bp_count FROM updated_bp;

  IF v_bp_count < v_current_count THEN
    RAISE EXCEPTION 'Cannot confirm source: missing blueprints for session questions (expected %, confirmed %)', 
      v_current_count, v_bp_count USING ERRCODE = '22023';
  END IF;

  -- 7. Transition session status to 'blueprinted'
  UPDATE public.exam_sessions
  SET status = 'blueprinted', updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'status', 'blueprinted',
    'confirmed_at', v_now,
    'total_questions', v_current_count,
    'total_blueprints', v_bp_count
  );
END;
$$;

-- Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) FROM anon;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) TO service_role;




