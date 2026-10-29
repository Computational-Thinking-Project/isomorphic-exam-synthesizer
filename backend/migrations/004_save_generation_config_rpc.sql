-- Migration 004: Atomic Save Generation Config RPC & Session Configured Transition [TASK-207a]
-- Purpose: Atomically lock exam session, verify ownership and state ('blueprinted' or 'configured'),
-- ensure 1-to-1 unique generation_config per session, validate source questions and confirmed blueprints,
-- upsert generation configuration preferences, and transition session status to 'configured' in one transaction.

-- 1. Ensure unique constraint on session_id and updated_at column on generation_configs
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_generation_configs_session_id'
  ) AND NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'uq_generation_configs_session_id'
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

-- 2. Drop existing signature if exists
DROP FUNCTION IF EXISTS public.save_generation_config(UUID, INT, JSONB, JSONB);

-- 3. Create hardened atomic save_generation_config RPC
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
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
  v_source_count INT := 0;
  v_now TIMESTAMPTZ := now();
  v_config_id UUID;
BEGIN
  -- 1. Atomic row lock on session to prevent concurrent status/source changes
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  -- 2. Validate session existence
  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 3. Enforce ownership (authenticated user must match owner; service_role is exempt)
  IF v_role != 'service_role' AND (v_session_user_id != auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 4. Enforce state machine: only 'blueprinted' or 'configured' sessions can save configuration
  IF v_session_status NOT IN ('blueprinted', 'configured') THEN
    RAISE EXCEPTION 'Cannot save config: session status must be blueprinted or configured, current status is %', 
      v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Validate parameters
  IF p_n_versions < 1 OR p_n_versions > 4 THEN
    RAISE EXCEPTION 'Invalid n_versions: % (must be between 1 and 4)', p_n_versions USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(p_active_variation_modes) != 'array' THEN
    RAISE EXCEPTION 'active_variation_modes must be a JSON array' USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(p_ordering_preferences) != 'object' THEN
    RAISE EXCEPTION 'ordering_preferences must be a JSON object' USING ERRCODE = '22023';
  END IF;

  -- 6. Verify source question count (1 to 20 questions)
  SELECT COUNT(*) INTO v_source_count
  FROM public.source_questions
  WHERE session_id = p_session_id;

  IF v_source_count < 1 OR v_source_count > 20 THEN
    RAISE EXCEPTION 'Cannot save config: session must contain between 1 and 20 source questions (found %)', 
      v_source_count USING ERRCODE = '22023';
  END IF;

  -- Verify that EVERY source question has a confirmed blueprint (NOT EXISTS check ensures robustness)
  IF EXISTS (
    SELECT 1 
    FROM public.source_questions sq
    WHERE sq.session_id = p_session_id
      AND NOT EXISTS (
        SELECT 1 
        FROM public.question_blueprints qb
        WHERE qb.source_question_id = sq.id 
          AND qb.confirmed_at IS NOT NULL
      )
  ) THEN
    RAISE EXCEPTION 'Cannot save config: not all source questions have confirmed blueprints' 
      USING ERRCODE = '22023';
  END IF;

  -- 7. Upsert configuration preferences
  INSERT INTO public.generation_configs (
    session_id,
    n_versions,
    active_variation_modes,
    ordering_preferences,
    created_at,
    updated_at
  ) VALUES (
    p_session_id,
    p_n_versions,
    p_active_variation_modes,
    p_ordering_preferences,
    v_now,
    v_now
  )
  ON CONFLICT (session_id) DO UPDATE SET
    n_versions = EXCLUDED.n_versions,
    active_variation_modes = EXCLUDED.active_variation_modes,
    ordering_preferences = EXCLUDED.ordering_preferences,
    updated_at = v_now
  RETURNING id INTO v_config_id;

  -- 8. Transition session status to 'configured' atomically
  UPDATE public.exam_sessions
  SET status = 'configured', updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'config_id', v_config_id,
    'status', 'configured',
    'config', jsonb_build_object(
      'n_versions', p_n_versions,
      'active_variation_modes', p_active_variation_modes,
      'ordering_preferences', p_ordering_preferences
    )
  );
END;
$$;

-- 4. Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) FROM anon;
GRANT EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) TO service_role;
