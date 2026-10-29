-- ============================================================================
-- Migration 004 (v6-lite): Atomic Save Generation Config RPC & Shared Helpers
-- Part A: Shared Helpers & Triggers
-- Part B: Atomic save_generation_config RPC
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
    'anon'
  );
$$;

-- 2. Helper: Set updated_at on UPDATE
CREATE OR REPLACE FUNCTION public.tg_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- 3. Trigger updated_at for exam_sessions
DROP TRIGGER IF EXISTS trg_exam_sessions_updated_at ON public.exam_sessions;
CREATE TRIGGER trg_exam_sessions_updated_at
BEFORE UPDATE ON public.exam_sessions
FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- 4. Trigger updated_at for generation_configs
DROP TRIGGER IF EXISTS trg_generation_configs_updated_at ON public.generation_configs;
CREATE TRIGGER trg_generation_configs_updated_at
BEFORE UPDATE ON public.generation_configs
FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- 5. Helper: Validate variation modes
CREATE OR REPLACE FUNCTION public.is_valid_variation_modes(p_modes JSONB)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE 
    WHEN p_modes IS NULL OR jsonb_typeof(p_modes) != 'array' THEN FALSE
    WHEN jsonb_array_length(p_modes) = 0 THEN TRUE
    WHEN EXISTS (
      SELECT 1 
      FROM jsonb_array_elements(p_modes) AS elem
      WHERE jsonb_typeof(elem) != 'string'
    ) THEN FALSE
    ELSE NOT EXISTS (
      SELECT 1 
      FROM jsonb_array_elements_text(p_modes) AS m(val)
      WHERE lower(trim(m.val)) NOT IN (
        'numerical', 'scenario', 'parameter', 'visual', 'structural', 'reverse'
      )
    )
  END;
$$;

REVOKE EXECUTE ON FUNCTION public.is_valid_variation_modes(JSONB) FROM PUBLIC, anon, authenticated;

-- ----------------------------------------------------------------------------
-- Part B. Generation Config Schema Hardening & RPC
-- ----------------------------------------------------------------------------

-- 6. Ensure unique constraint & updated_at on generation_configs
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_generation_configs_session_id'
  ) THEN
    ALTER TABLE public.generation_configs
      ADD CONSTRAINT uq_generation_configs_session_id UNIQUE (session_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'generation_configs' 
      AND column_name = 'updated_at'
  ) THEN
    ALTER TABLE public.generation_configs 
      ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
  END IF;
END $$;

-- 7. Drop function if exists for clean signature definition
DROP FUNCTION IF EXISTS public.save_generation_config(UUID, INT, JSONB, JSONB);

-- 8. Atomic save_generation_config RPC
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

  -- 2. Ownership check (NULL-safe)
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

  -- 4. Validate p_n_versions (1-4)
  IF p_n_versions IS NULL OR p_n_versions < 1 OR p_n_versions > 4 THEN
    RAISE EXCEPTION 'Invalid n_versions: % (must be between 1 and 4)', p_n_versions
      USING ERRCODE = '22023';
  END IF;

  -- 5. Validate variation modes
  IF p_active_variation_modes IS NULL OR NOT public.is_valid_variation_modes(p_active_variation_modes) THEN
    RAISE EXCEPTION 'Invalid active_variation_modes: contains unapproved mode or invalid schema'
      USING ERRCODE = '22023';
  END IF;

  SELECT COALESCE(
    jsonb_agg(lower(trim(m.value))),
    '[]'::jsonb
  ) INTO v_normalized_modes
  FROM jsonb_array_elements_text(p_active_variation_modes) AS m(value);

  -- 6. Validate ordering preferences
  IF p_ordering_preferences IS NULL 
     OR jsonb_typeof(p_ordering_preferences) != 'object'
     OR NOT (p_ordering_preferences ? 'shuffle_questions')
     OR NOT (p_ordering_preferences ? 'shuffle_options') THEN
    RAISE EXCEPTION 'ordering_preferences must be a JSON object with shuffle_questions and shuffle_options'
      USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(p_ordering_preferences->'shuffle_questions') != 'boolean'
     OR jsonb_typeof(p_ordering_preferences->'shuffle_options') != 'boolean' THEN
    RAISE EXCEPTION 'ordering_preferences values must be boolean' USING ERRCODE = '22023';
  END IF;

  -- 7. Validate source question count (1-20)
  SELECT COUNT(*) INTO v_source_count
  FROM public.source_questions WHERE session_id = p_session_id;

  IF v_source_count < 1 OR v_source_count > 20 THEN
    RAISE EXCEPTION 'Session must contain 1-20 source questions (found %)', v_source_count
      USING ERRCODE = '22023';
  END IF;

  -- 8. Validate all source questions have confirmed blueprints
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

  -- 9. Upsert configuration
  INSERT INTO public.generation_configs (
    session_id, n_versions, active_variation_modes, ordering_preferences
  ) VALUES (
    p_session_id, p_n_versions, v_normalized_modes, p_ordering_preferences
  )
  ON CONFLICT (session_id) DO UPDATE SET
    n_versions = EXCLUDED.n_versions,
    active_variation_modes = EXCLUDED.active_variation_modes,
    ordering_preferences = EXCLUDED.ordering_preferences
  RETURNING id INTO v_config_id;

  -- 10. Transition session status to 'configured'
  UPDATE public.exam_sessions SET status = 'configured' WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'config_id', v_config_id,
    'status', 'configured',
    'config', jsonb_build_object(
      'n_versions', p_n_versions,
      'active_variation_modes', v_normalized_modes,
      'ordering_preferences', p_ordering_preferences
    )
  );
END;
$$;

-- 9. Least privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) TO authenticated, service_role;
