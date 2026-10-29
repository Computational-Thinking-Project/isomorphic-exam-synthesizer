-- ============================================================================
-- Migration 004 (v5): Atomic Save Generation Config RPC & Shared Helpers
-- Part A: Shared Helpers, Triggers & Partial Index
-- Part B: Hardened save_generation_config RPC
--
-- Security, Concurrency & Data Normalization Hardening (Review v4 Resolution):
--   - current_role(): Guaranteed non-NULL ('anon' fallback).
--   - is_valid_variation_modes(): Declared STABLE (collation-aware lower()),
--     CASE-expression guards against SQL evaluation order bugs,
--     strictly internal (REVOKED from PUBLIC, anon, authenticated).
--   - Data Normalization: Normalizes modes to lower(trim()) with deterministic ORDER BY.
--   - Unique Index Detection: Uses indnkeyatts = 1, indexprs IS NULL, indpred IS NULL.
--   - TOCTOU Elimination: Locks both source_questions and question_blueprints FOR SHARE.
--   - Schema Invariants: Verifies non-partial, valid unique index and guarantees updated_at NOT NULL.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Part A. Shared Helpers & Triggers
-- ----------------------------------------------------------------------------

-- 1. Helper: Current JWT Role (guaranteed non-NULL; fallback to 'anon')
CREATE OR REPLACE FUNCTION public.current_role()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, auth, pg_temp
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END,
    'anon'   -- Fallback: never returns NULL to prevent PL/pgSQL condition bypass
  );
$$;

-- 2. Helper: Set updated_at trigger
CREATE OR REPLACE FUNCTION public.tg_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- 3. Trigger updated_at on exam_sessions
DROP TRIGGER IF EXISTS trg_exam_sessions_updated_at ON public.exam_sessions;
CREATE TRIGGER trg_exam_sessions_updated_at
BEFORE UPDATE ON public.exam_sessions
FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- 4. Trigger updated_at on generation_configs
DROP TRIGGER IF EXISTS trg_generation_configs_updated_at ON public.generation_configs;
CREATE TRIGGER trg_generation_configs_updated_at
BEFORE UPDATE ON public.generation_configs
FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- 5. Ensure active_job_id and last_progress_at columns exist on exam_sessions before index creation
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions 
      ADD COLUMN active_job_id UUID NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'last_progress_at'
  ) THEN
    ALTER TABLE public.exam_sessions 
      ADD COLUMN last_progress_at TIMESTAMPTZ NULL;
  END IF;
END $$;

-- 6. Partial index for recovery job (scans only active generating sessions)
CREATE INDEX IF NOT EXISTS idx_exam_sessions_active_job
  ON public.exam_sessions (updated_at)
  WHERE active_job_id IS NOT NULL AND status = 'generating';

-- 7. Helper: Validate variation modes (STABLE due to collation-dependent lower(); CASE guards execution order)
CREATE OR REPLACE FUNCTION public.is_valid_variation_modes(p_modes JSONB)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE 
    WHEN jsonb_typeof(p_modes) = 'array' THEN
      NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(p_modes) AS m(value)
        WHERE m.value IS NULL
           OR trim(m.value) = ''
           OR lower(trim(m.value)) NOT IN (
             'numerical', 'structural', 'contextual', 'none',
             'parameter_variation', 'context_swap', 'difficulty_shift',
             'shuffle_answers', 'paraphrase', 'reorder_options',
             'tone_formal', 'tone_conversational'
           )
      )
    ELSE FALSE
  END;
$$;

-- Restricted strictly: internal helper for save_generation_config
REVOKE EXECUTE ON FUNCTION public.is_valid_variation_modes(JSONB) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.is_valid_variation_modes(JSONB) TO service_role;

-- ----------------------------------------------------------------------------
-- Part B. Generation Config Schema Hardening & RPC
-- ----------------------------------------------------------------------------

-- 8. Ensure non-partial, valid unique constraint & updated_at on generation_configs
DO $$
BEGIN
  -- Unique constraint on session_id (checks pg_index using indnkeyatts = 1 to correctly handle INCLUDE columns)
  IF NOT EXISTS (
    SELECT 1
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
    WHERE i.indrelid = 'public.generation_configs'::regclass
      AND i.indisunique
      AND i.indisvalid
      AND i.indpred IS NULL
      AND i.indexprs IS NULL
      AND i.indnkeyatts = 1
      AND a.attname = 'session_id'
      AND NOT a.attisdropped
  ) THEN
    ALTER TABLE public.generation_configs
      ADD CONSTRAINT uq_generation_configs_session_id UNIQUE (session_id);
  END IF;

  -- Ensure updated_at column exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'generation_configs' 
      AND column_name = 'updated_at'
  ) THEN
    ALTER TABLE public.generation_configs ADD COLUMN updated_at TIMESTAMPTZ NULL;
  END IF;

  -- Backfill any existing rows with NULL updated_at
  UPDATE public.generation_configs 
  SET updated_at = COALESCE(created_at, now()) 
  WHERE updated_at IS NULL;

  -- Enforce NOT NULL and DEFAULT
  ALTER TABLE public.generation_configs 
    ALTER COLUMN updated_at SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now();
END $$;

-- 9. Drop old RPC signature
DROP FUNCTION IF EXISTS public.save_generation_config(UUID, INT, JSONB, JSONB);

-- 10. Create hardened atomic save_generation_config RPC
CREATE OR REPLACE FUNCTION public.save_generation_config(
  p_session_id UUID,
  p_n_versions INT,
  p_active_variation_modes JSONB DEFAULT '[]'::jsonb,
  p_ordering_preferences JSONB DEFAULT '{"shuffle_questions": true, "shuffle_options": true}'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_source_count INT := 0;
  v_config_id UUID;
  v_revision TIMESTAMPTZ;
  v_normalized_modes JSONB;
BEGIN
  -- 1. Lock session row
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Ownership check (NULL-safe: current_role() is guaranteed non-NULL)
  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id
      USING ERRCODE = '42501';
  END IF;

  -- 3. State machine validation
  IF v_session_status NOT IN ('blueprinted', 'configured') THEN
    RAISE EXCEPTION 'Cannot save config: session status must be blueprinted or configured (current: %)',
      v_session_status USING ERRCODE = '22023';
  END IF;

  -- 4. Validate p_n_versions (not null, 1-4)
  IF p_n_versions IS NULL OR p_n_versions < 1 OR p_n_versions > 4 THEN
    RAISE EXCEPTION 'Invalid n_versions: % (must be between 1 and 4)', p_n_versions
      USING ERRCODE = '22023';
  END IF;

  -- 5. Validate variation modes (explicit NULL check + domain validator)
  IF p_active_variation_modes IS NULL THEN
    RAISE EXCEPTION 'active_variation_modes cannot be NULL' USING ERRCODE = '22023';
  END IF;
  IF NOT public.is_valid_variation_modes(p_active_variation_modes) THEN
    RAISE EXCEPTION 'Invalid active_variation_modes: must be a JSON array of known mode strings'
      USING ERRCODE = '22023';
  END IF;

  -- Normalize modes (lower, trim, deduplicated with deterministic alphabetical ordering)
  SELECT COALESCE(
    jsonb_agg(DISTINCT lower(trim(m.value)) ORDER BY lower(trim(m.value))),
    '[]'::jsonb
  ) INTO v_normalized_modes
  FROM jsonb_array_elements_text(p_active_variation_modes) AS m(value);

  -- 6. Validate ordering preferences (explicit NULL check + object + required schema keys)
  IF p_ordering_preferences IS NULL THEN
    RAISE EXCEPTION 'ordering_preferences cannot be NULL' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(p_ordering_preferences) != 'object' THEN
    RAISE EXCEPTION 'ordering_preferences must be a JSON object' USING ERRCODE = '22023';
  END IF;
  IF NOT (p_ordering_preferences ? 'shuffle_questions')
     OR NOT (p_ordering_preferences ? 'shuffle_options') THEN
    RAISE EXCEPTION 'ordering_preferences missing required keys: shuffle_questions, shuffle_options'
      USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(p_ordering_preferences->'shuffle_questions') != 'boolean'
     OR jsonb_typeof(p_ordering_preferences->'shuffle_options') != 'boolean' THEN
    RAISE EXCEPTION 'ordering_preferences values must be boolean' USING ERRCODE = '22023';
  END IF;

  -- 7. Defense-in-depth: Shared lock on source_questions and blueprints to eliminate TOCTOU races
  PERFORM 1 
  FROM public.source_questions sq
  LEFT JOIN public.question_blueprints qb ON qb.source_question_id = sq.id
  WHERE sq.session_id = p_session_id 
  FOR SHARE;

  -- 8. Validate source question count (1-20)
  SELECT COUNT(*) INTO v_source_count
  FROM public.source_questions WHERE session_id = p_session_id;

  IF v_source_count < 1 OR v_source_count > 20 THEN
    RAISE EXCEPTION 'Session must contain 1-20 source questions (found %)', v_source_count
      USING ERRCODE = '22023';
  END IF;

  -- 9. Validate all source questions have confirmed blueprints (NOT EXISTS)
  IF EXISTS (
    SELECT 1
    FROM public.source_questions sq
    WHERE sq.session_id = p_session_id
      AND NOT EXISTS (
        SELECT 1 FROM public.question_blueprints qb
        WHERE qb.source_question_id = sq.id AND qb.confirmed_at IS NOT NULL
      )
  ) THEN
    RAISE EXCEPTION 'Not all source questions have confirmed blueprints' USING ERRCODE = '22023';
  END IF;

  -- 10. Upsert normalized configuration (trigger trg_generation_configs_updated_at handles updated_at)
  INSERT INTO public.generation_configs (
    session_id, n_versions, active_variation_modes, ordering_preferences
  ) VALUES (
    p_session_id, p_n_versions, v_normalized_modes, p_ordering_preferences
  )
  ON CONFLICT (session_id) DO UPDATE SET
    n_versions = EXCLUDED.n_versions,
    active_variation_modes = EXCLUDED.active_variation_modes,
    ordering_preferences = EXCLUDED.ordering_preferences
  RETURNING id, updated_at INTO v_config_id, v_revision;

  -- 11. Transition session status to 'configured' (trigger trg_exam_sessions_updated_at handles updated_at)
  UPDATE public.exam_sessions SET status = 'configured' WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'config_id', v_config_id,
    'config_revision', v_revision,
    'status', 'configured',
    'config', jsonb_build_object(
      'n_versions', p_n_versions,
      'active_variation_modes', v_normalized_modes,
      'ordering_preferences', p_ordering_preferences
    )
  );
END;
$$;

-- 12. Least privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) TO authenticated, service_role;
