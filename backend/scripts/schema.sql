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
  regeneration_id UUID NULL,
  validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Invariant Constraint: At any time, exactly one current record exists per version/source pair
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question 
  ON public.version_questions (version_id, source_question_id) 
  WHERE is_current = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_version_questions_regeneration
  ON public.version_questions (regeneration_id) WHERE regeneration_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_version_questions_stale_guard
  ON public.version_questions (updated_at) WHERE status = 'regenerating';

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

CREATE UNIQUE INDEX IF NOT EXISTS uq_answer_keys_version_display
  ON public.answer_keys (version_id, display_no);

-- Table 9: Review Logs (Audit trail of teacher review decisions)
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






-- Migration 008: Stage 3 Review Lifecycle Stored Procedures & Attempt Ledger
-- Conforms strictly to review-rpc-contract.md (TASK-301 / TASK-302 Phase B).
-- Provides single-transaction atomic permit acquisition, replay prevention, operation binding,
-- state transition guards, session-wide reshuffle invalidation, and quota accounting.

-- 1. Create review_attempts table for durable ledger tracking
CREATE TABLE IF NOT EXISTS public.review_attempts (
    attempt_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL,
    session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('requested', 'granted', 'denied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_attempts_operation_id ON public.review_attempts(operation_id);
CREATE INDEX IF NOT EXISTS idx_review_attempts_session_id ON public.review_attempts(session_id);

-- Enable Row Level Security on review_attempts ledger
ALTER TABLE public.review_attempts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'review_attempts' AND policyname = 'review_attempts_owner_read'
    ) THEN
        CREATE POLICY review_attempts_owner_read ON public.review_attempts
            FOR SELECT TO authenticated
            USING (session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'review_attempts' AND policyname = 'review_attempts_service_write'
    ) THEN
        CREATE POLICY review_attempts_service_write ON public.review_attempts
            FOR ALL TO service_role
            USING (TRUE) WITH CHECK (TRUE);
    END IF;
END $$;


-- ============================================================================
-- 2. Stored Procedure: review_reserve_regeneration (Owner JWT / Service Role)
-- Atomic TX1: Locks session FOR UPDATE, enforces Model A concurrency, and marks question
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_reserve_regeneration(
    p_session_id UUID,
    p_question_id UUID,
    p_operation_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_current_calls INT;
    v_session_owner UUID;
    v_active_regen_id UUID;
    v_qid UUID;
    v_qstatus TEXT;
    v_is_current BOOLEAN;
    v_src_qid UUID;
    v_vid UUID;
    v_qno INT;
    v_can_qno INT;
    v_can_opts JSONB;
    v_can_key TEXT;
    v_can_sol TEXT;
    v_content TEXT;
    v_opts JSONB;
    v_key TEXT;
    v_sol TEXT;
BEGIN
    -- 1. Lock session row atomically to enforce concurrency and check quota
    SELECT status, gemini_review_calls, user_id
    INTO v_session_status, v_current_calls, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    -- Verify caller ownership if called via authenticated JWT
    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    -- Guard session status: locked when approved or exported
    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    -- Guard session busy when generating
    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- Guard session quota ceiling (30)
    IF v_current_calls >= 30 THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUOTA_EXHAUSTED');
    END IF;

    -- 2. Concurrency Model A: Max 1 active regenerating question per session
    SELECT q.id INTO v_active_regen_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE v.session_id = p_session_id
      AND q.status = 'regenerating'
      AND q.is_current = TRUE
    LIMIT 1;

    IF FOUND AND v_active_regen_id != p_question_id THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 3. Check question state and lock question row
    SELECT q.id, q.status, q.is_current, q.source_question_id, q.version_id, q.question_no,
           q.canonical_question_no, q.canonical_options, q.canonical_correct_key, q.canonical_solution_md,
           q.content, q.options, q.correct_key, q.solution_md
    INTO v_qid, v_qstatus, v_is_current, v_src_qid, v_vid, v_qno,
         v_can_qno, v_can_opts, v_can_key, v_can_sol,
         v_content, v_opts, v_key, v_sol
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    -- 4. Atomic lock & durable operation binding
    UPDATE public.version_questions
    SET status = 'regenerating',
        regeneration_id = p_operation_id,
        updated_at = NOW()
    WHERE id = p_question_id;

    UPDATE public.exam_sessions
    SET updated_at = NOW()
    WHERE id = p_session_id;

    RETURN jsonb_build_object(
        'success', true,
        'session_id', p_session_id,
        'question_id', p_question_id,
        'operation_id', p_operation_id,
        'source_question_id', v_src_qid,
        'version_id', v_vid,
        'question_no', v_qno,
        'canonical_question_no', v_can_qno,
        'current_calls', v_current_calls,
        'status', 'regenerating'
    );
END;
$$;


-- ============================================================================
-- 3. Stored Procedure: review_acquire_attempt (Worker / service_role)
-- Single-transaction permit acquisition with strict binding, replay protection, and quota ceiling
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_acquire_attempt(
    p_operation_id UUID,
    p_attempt_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_id UUID;
    v_question_id UUID;
    v_question_status TEXT;
    v_question_updated_at TIMESTAMPTZ;
    v_session_status TEXT;
    v_current_calls INT;
    v_attempt_status TEXT;
    v_op_attempts INT;
BEGIN
    -- Strict Operation Identity & Session Binding (TASK-302 contract)
    SELECT v.session_id, q.id, q.status, q.updated_at
    INTO v_session_id, v_question_id, v_question_status, v_question_updated_at
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.is_current = TRUE
    LIMIT 1;

    -- If not found on version_questions, check review_attempts ledger for prior acquired attempts
    IF v_session_id IS NULL THEN
        SELECT session_id INTO v_session_id
        FROM public.review_attempts
        WHERE operation_id = p_operation_id
        LIMIT 1;
    END IF;

    -- Reject if operation does not exist or cannot be bound (Fail-closed)
    IF v_session_id IS NULL THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', NULL,
            'session_status', 'not_found',
            'replayed', false,
            'rejection_reason', 'OPERATION_NOT_FOUND'
        );
    END IF;

    -- Verify question is in active regenerating status
    IF v_question_status IS NOT NULL AND v_question_status != 'regenerating' THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'invalid_state',
            'replayed', false,
            'rejection_reason', 'OPERATION_INACTIVE'
        );
    END IF;

    -- Check lease expiration (180-second stale timeout per TASK-302 contract)
    IF v_question_updated_at IS NOT NULL AND v_question_updated_at < (NOW() - INTERVAL '180 seconds') THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'expired',
            'replayed', false,
            'rejection_reason', 'OPERATION_EXPIRED'
        );
    END IF;

    -- Lock session row atomically to prevent concurrent quota races across workers
    SELECT status, gemini_review_calls
    INTO v_session_status, v_current_calls
    FROM public.exam_sessions
    WHERE id = v_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'not_found',
            'replayed', false,
            'rejection_reason', 'SESSION_NOT_FOUND'
        );
    END IF;

    -- Enforce session lock guard: reject approved or exported sessions
    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'SESSION_LOCKED'
        );
    END IF;

    -- Enforce session busy guard: reject if session is actively generating
    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'SESSION_BUSY'
        );
    END IF;

    -- Check replay on review_attempts ledger
    SELECT status INTO v_attempt_status
    FROM public.review_attempts
    WHERE attempt_id = p_attempt_id;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', true,
            'rejection_reason', 'ATTEMPT_REPLAYED'
        );
    END IF;

    -- Check operation attempt ceiling (max 4 attempts per reject operation)
    SELECT COUNT(*) INTO v_op_attempts
    FROM public.review_attempts
    WHERE operation_id = p_operation_id;

    IF v_op_attempts >= 4 THEN
        INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
        VALUES (p_attempt_id, p_operation_id, v_session_id, 'denied', NOW());

        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'OPERATION_EXHAUSTED'
        );
    END IF;

    -- Check session quota ceiling (max 30 attempts per session)
    IF v_current_calls >= 30 THEN
        INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
        VALUES (p_attempt_id, p_operation_id, v_session_id, 'denied', NOW());

        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 30,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'QUOTA_EXHAUSTED'
        );
    END IF;

    -- Increment session quota atomically and insert granted ledger entry
    UPDATE public.exam_sessions
    SET gemini_review_calls = v_current_calls + 1,
        updated_at = NOW()
    WHERE id = v_session_id;

    INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
    VALUES (p_attempt_id, p_operation_id, v_session_id, 'granted', NOW());

    RETURN jsonb_build_object(
        'operation_id', p_operation_id,
        'attempt_id', p_attempt_id,
        'dispatch_permitted', true,
        'calls_used', v_current_calls + 1,
        'remaining_calls', 30 - (v_current_calls + 1),
        'session_id', v_session_id,
        'session_status', v_session_status,
        'replayed', false
    );
END;
$$;


-- ============================================================================
-- 4. Stored Procedure: review_complete_regeneration (Worker / service_role)
-- Atomic TX2: Deactivates old question, inserts new question, invalidates finalization, and writes audit
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_complete_regeneration(
    p_operation_id UUID,
    p_candidate JSONB,
    p_user_id UUID,
    p_actual_calls INT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_existing_id UUID;
    v_old_id UUID;
    v_version_id UUID;
    v_source_id UUID;
    v_question_no INT;
    v_canonical_no INT;
    v_session_id UUID;
    v_new_id UUID;
    v_content TEXT;
    v_options JSONB;
    v_correct_key TEXT;
    v_solution_md TEXT;
    v_validation_report JSONB;
BEGIN
    -- Idempotency check: see if a replacement was already committed with this operation_id
    SELECT id INTO v_existing_id
    FROM public.version_questions
    WHERE regeneration_id = p_operation_id
      AND status != 'rejected'
      AND status != 'regenerating'
    LIMIT 1;

    IF FOUND THEN
        SELECT v.session_id INTO v_session_id
        FROM public.version_questions q
        JOIN public.exam_versions v ON v.id = q.version_id
        WHERE q.id = v_existing_id;

        RETURN jsonb_build_object(
            'success', false,
            'replayed', true,
            'session_id', v_session_id,
            'question_id', v_existing_id,
            'operation_id', p_operation_id,
            'status', 'pending_review'
        );
    END IF;

    -- Find active regenerating question bound to this operation
    SELECT q.id, q.version_id, q.source_question_id, q.question_no,
           COALESCE(q.canonical_question_no, q.question_no), v.session_id
    INTO v_old_id, v_version_id, v_source_id, v_question_no,
         v_canonical_no, v_session_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.status = 'regenerating'
      AND q.is_current = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'rejection_reason', 'OPERATION_NOT_FOUND'
        );
    END IF;

    -- 1. Deactivate old candidate
    UPDATE public.version_questions
    SET is_current = FALSE,
        status = 'rejected',
        regeneration_id = NULL,
        updated_at = NOW()
    WHERE id = v_old_id;

    -- 2. Extract candidate payload fields
    v_content := COALESCE(p_candidate->>'content', p_candidate->>'stem_latex');
    v_options := p_candidate->'options';
    v_correct_key := UPPER(TRIM(COALESCE(p_candidate->>'correct_key', 'A')));
    v_solution_md := p_candidate->>'solution_md';
    v_validation_report := COALESCE(p_candidate->'validation_report', '{}'::jsonb);

    -- 3. Insert new candidate with fresh canonical snapshot
    v_new_id := gen_random_uuid();
    INSERT INTO public.version_questions (
        id, version_id, source_question_id, question_no,
        content, options, correct_key, solution_md,
        canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
        status, is_current, is_reverted, regenerated_from_id, regeneration_id,
        validation_report, created_at, updated_at
    ) VALUES (
        v_new_id,
        v_version_id,
        v_source_id,
        v_question_no,
        v_content,
        v_options,
        v_correct_key,
        v_solution_md,
        v_canonical_no,
        v_options,
        v_correct_key,
        v_solution_md,
        'pending_review',
        TRUE,
        FALSE,
        v_old_id,
        p_operation_id,
        v_validation_report,
        NOW(),
        NOW()
    );

    -- 4. Session-wide reshuffle invalidation
    DELETE FROM public.answer_keys
    WHERE version_id IN (
        SELECT id FROM public.exam_versions WHERE session_id = v_session_id
    );

    UPDATE public.exam_versions
    SET is_finalized = FALSE,
        shuffle_seed = NULL,
        permutations = NULL,
        updated_at = NOW()
    WHERE session_id = v_session_id;

    UPDATE public.exam_sessions
    SET status = 'generated',
        updated_at = NOW()
    WHERE id = v_session_id AND status = 'reviewed';

    -- 5. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, api_calls_used, regenerated_from_id, created_at
    ) VALUES (
        v_session_id,
        v_new_id,
        p_user_id,
        'REJECT',
        'USER_REJECTED',
        p_actual_calls,
        v_old_id,
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', v_session_id,
        'question_id', v_new_id,
        'previous_question_id', v_old_id,
        'operation_id', p_operation_id,
        'status', 'pending_review',
        'api_calls_used', p_actual_calls
    );
END;
$$;


-- ============================================================================
-- 5. Stored Procedure: review_fail_regeneration (Worker / service_role)
-- Emergency Rollback: restores old question to pending_review without quota refund
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_fail_regeneration(
    p_operation_id UUID,
    p_error_code TEXT,
    p_user_id UUID,
    p_actual_calls INT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_old_id UUID;
    v_session_id UUID;
BEGIN
    SELECT q.id, v.session_id
    INTO v_old_id, v_session_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.status = 'regenerating'
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'operation_id', p_operation_id
        );
    END IF;

    -- Restore question back to pending_review and clear lease
    UPDATE public.version_questions
    SET status = 'pending_review',
        regeneration_id = NULL,
        updated_at = NOW()
    WHERE id = v_old_id;

    -- Record failed attempt in audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, api_calls_used, created_at
    ) VALUES (
        v_session_id,
        v_old_id,
        p_user_id,
        'REJECT_FAILED',
        p_error_code,
        p_actual_calls,
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'operation_id', p_operation_id,
        'question_id', v_old_id,
        'status', 'pending_review',
        'api_calls_used', p_actual_calls
    );
END;
$$;


-- ============================================================================
-- 6. Stored Procedure: review_revert_question (Owner JWT / Service Role)
-- Atomic Revert: Copies original source question, invalidates finalization, and audits
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_revert_question(
    p_session_id UUID,
    p_question_id UUID,
    p_action_id UUID,
    p_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_session_owner UUID;
    v_old_id UUID;
    v_version_id UUID;
    v_source_id UUID;
    v_is_current BOOLEAN;
    v_qstatus TEXT;
    v_is_reverted BOOLEAN;
    v_regen_from_id UUID;
    v_raw_content TEXT;
    v_src_opts JSONB;
    v_src_key TEXT;
    v_src_sol TEXT;
    v_qno INT;
    v_new_id UUID;
BEGIN
    -- 1. Lock session row
    SELECT status, user_id INTO v_session_status, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 2. Lock candidate row
    SELECT q.id, q.version_id, q.source_question_id, q.is_current, q.status,
           q.is_reverted, q.regenerated_from_id
    INTO v_old_id, v_version_id, v_source_id, v_is_current, v_qstatus,
         v_is_reverted, v_regen_from_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    -- Cannot revert a question that was never regenerated
    IF v_regen_from_id IS NULL AND v_is_reverted IS FALSE THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_REGENERATED');
    END IF;

    -- Idempotent check
    IF v_is_reverted IS TRUE AND v_qstatus = 'approved' THEN
        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'session_id', p_session_id,
            'question_id', p_question_id,
            'status', 'approved'
        );
    END IF;

    -- 3. Fetch source question
    SELECT raw_content, options, correct_key, solution_md, question_no
    INTO v_raw_content, v_src_opts, v_src_key, v_src_sol, v_qno
    FROM public.source_questions
    WHERE id = v_source_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SOURCE_NOT_FOUND');
    END IF;

    -- 4. Deactivate old candidate
    UPDATE public.version_questions
    SET is_current = FALSE,
        updated_at = NOW()
    WHERE id = p_question_id;

    -- 5. Insert new candidate copied from source
    v_new_id := gen_random_uuid();
    INSERT INTO public.version_questions (
        id, version_id, source_question_id, question_no,
        content, options, correct_key, solution_md,
        canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
        status, is_current, is_reverted, regenerated_from_id, created_at, updated_at
    ) VALUES (
        v_new_id,
        v_version_id,
        v_source_id,
        v_qno,
        v_raw_content,
        v_src_opts,
        v_src_key,
        v_src_sol,
        v_qno,
        v_src_opts,
        v_src_key,
        v_src_sol,
        'approved',
        TRUE,
        TRUE,
        p_question_id,
        NOW(),
        NOW()
    );

    -- 6. Session-wide reshuffle invalidation
    DELETE FROM public.answer_keys
    WHERE version_id IN (
        SELECT id FROM public.exam_versions WHERE session_id = p_session_id
    );

    UPDATE public.exam_versions
    SET is_finalized = FALSE,
        shuffle_seed = NULL,
        permutations = NULL,
        updated_at = NOW()
    WHERE session_id = p_session_id;

    UPDATE public.exam_sessions
    SET status = 'generated',
        updated_at = NOW()
    WHERE id = p_session_id AND status = 'reviewed';

    -- 7. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, created_at
    ) VALUES (
        p_session_id,
        v_new_id,
        p_user_id,
        'REVERT',
        'USER_REVERTED',
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', p_session_id,
        'question_id', v_new_id,
        'previous_question_id', p_question_id,
        'status', 'approved'
    );
END;
$$;


-- ============================================================================
-- 7. Stored Procedure: review_accept_question (Owner JWT / Service Role)
-- Atomic Accept: Marks candidate approved and writes audit log
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_accept_question(
    p_session_id UUID,
    p_question_id UUID,
    p_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_session_owner UUID;
    v_qid UUID;
    v_qstatus TEXT;
    v_is_current BOOLEAN;
BEGIN
    -- 1. Lock session row
    SELECT status, user_id INTO v_session_status, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 2. Lock candidate row
    SELECT q.id, q.status, q.is_current
    INTO v_qid, v_qstatus, v_is_current
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    IF v_qstatus = 'approved' THEN
        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'session_id', p_session_id,
            'question_id', p_question_id,
            'status', 'approved'
        );
    END IF;

    -- 3. Mark approved
    UPDATE public.version_questions
    SET status = 'approved',
        updated_at = NOW()
    WHERE id = p_question_id;

    -- 4. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, created_at
    ) VALUES (
        p_session_id,
        p_question_id,
        p_user_id,
        'ACCEPT',
        'USER_ACCEPTED',
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', p_session_id,
        'question_id', p_question_id,
        'status', 'approved'
    );
END;
$$;


-- ============================================================================
-- 8. Stored Procedure: review_recover_stale (Owner JWT / Service Role)
-- Recovers stale regenerating questions (> 180s) and writes REJECT_FAILED audit logs
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_recover_stale(
    p_session_id UUID,
    p_caller_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_recovered_count INT := 0;
    r RECORD;
BEGIN
    FOR r IN (
        SELECT q.id
        FROM public.version_questions q
        JOIN public.exam_versions v ON v.id = q.version_id
        WHERE v.session_id = p_session_id
          AND q.status = 'regenerating'
          AND q.is_current = TRUE
          AND q.updated_at < (NOW() - INTERVAL '180 seconds')
        FOR UPDATE OF q
    ) LOOP
        UPDATE public.version_questions
        SET status = 'pending_review',
            regeneration_id = NULL,
            updated_at = NOW()
        WHERE id = r.id;

        INSERT INTO public.review_logs (
            session_id, version_question_id, user_id, action_type,
            reason, created_at
        ) VALUES (
            p_session_id,
            r.id,
            p_caller_user_id,
            'REJECT_FAILED',
            'STALE_TIMEOUT',
            NOW()
        );

        v_recovered_count := v_recovered_count + 1;
    END LOOP;

    RETURN jsonb_build_object(
        'success', true,
        'session_id', p_session_id,
        'recovered_count', v_recovered_count
    );
END;
$$;


-- ============================================================================
-- 9. Permissions & Access Control (TASK-302 Contract)
-- ============================================================================
-- Revoke all from PUBLIC and anon
REVOKE ALL ON FUNCTION public.review_reserve_regeneration(UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_acquire_attempt(UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_complete_regeneration(UUID, JSONB, UUID, INT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_fail_regeneration(UUID, TEXT, UUID, INT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_revert_question(UUID, UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_accept_question(UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_recover_stale(UUID, UUID) FROM PUBLIC, anon;

-- Grant Owner RPCs to authenticated and service_role
GRANT EXECUTE ON FUNCTION public.review_reserve_regeneration(UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_revert_question(UUID, UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_accept_question(UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_recover_stale(UUID, UUID) TO authenticated, service_role;

-- Grant Worker RPCs to service_role (and authenticated for direct API lifecycle)
GRANT EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.review_complete_regeneration(UUID, JSONB, UUID, INT) TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.review_fail_regeneration(UUID, TEXT, UUID, INT) TO service_role, authenticated;

