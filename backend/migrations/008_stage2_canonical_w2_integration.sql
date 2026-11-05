-- ============================================================================
-- Migration 008: Stage 2 Canonical Blueprint Integration & W2 Storage
--
-- Enhancements for TASK-207a/b & W2 Handoff:
-- 1. Canonical Source Snapshot RPC (public.get_generation_source_snapshot)
--    - Validates against all live source_questions, confirmation, source heads,
--      revisions, and canonical blueprint 0.4.0 documents.
-- 2. Canonical Readiness Integration in public.save_generation_config
--    - Enforces canonical readiness check atomically before config commit.
-- 3. Immutable Generation Job Snapshots table (public.generation_job_snapshots)
--    - Binds immutable execution context (sources, blueprints, hash, seed, modes).
-- 4. Safe Full Result Storage Table (public.generation_target_results)
--    - Strict idempotency, slot verification, no unsafe overwrites.
-- 5. Atomic Full Result & Display Projection Persistence RPC (public.persist_generation_result)
-- 6. Durable Resume Read RPC (public.load_generation_completed_results)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Immutable Generation Job Snapshots Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.generation_job_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  job_token UUID NOT NULL,
  confirmation_id UUID NULL,
  source_order JSONB NOT NULL,
  confirmed_source_hash TEXT NOT NULL,
  base_seed INT NOT NULL,
  n_versions INT NOT NULL,
  public_modes JSONB NOT NULL,
  canonical_dimensions JSONB NOT NULL,
  mapping_version TEXT NOT NULL DEFAULT '1.0',
  snapshot_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_job_snapshots_token UNIQUE (job_token)
);

ALTER TABLE public.generation_job_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.generation_job_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.generation_job_snapshots TO service_role;

-- ----------------------------------------------------------------------------
-- 2. Extended Full Result Storage Table (for incremental resume)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.generation_target_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  job_token UUID NOT NULL,
  version_index INT NOT NULL CHECK (version_index BETWEEN 1 AND 4),
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  is_success BOOLEAN NOT NULL,
  error_code TEXT NULL,
  attempts INT NOT NULL DEFAULT 1,
  seed INT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  raw_result JSONB NOT NULL,
  version_question_id UUID NULL REFERENCES public.version_questions(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_target_slot UNIQUE (session_id, version_index, source_question_id)
);

ALTER TABLE public.generation_target_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.generation_target_results FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.generation_target_results TO service_role;

-- ----------------------------------------------------------------------------
-- 3. Canonical Source Snapshot RPC (public.get_generation_source_snapshot)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_generation_source_snapshot(p_session_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session public.exam_sessions;
  v_confirmation public.source_artifact_confirmations;
  v_source_count INT;
  v_ready BOOLEAN := TRUE;
  v_reason TEXT := NULL;
  v_sources JSONB := '[]'::jsonb;
  v_source_order JSONB := '[]'::jsonb;
  v_missing_head BOOLEAN := FALSE;
  v_stale_source BOOLEAN := FALSE;
  v_missing_bp BOOLEAN := FALSE;
  v_invalid_schema BOOLEAN := FALSE;
BEGIN
  -- 1. Lock session for share
  SELECT * INTO v_session FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Authorization (owner or service_role)
  IF public.current_role() != 'service_role'
     AND (v_session.user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 3. Read latest confirmation
  SELECT * INTO v_confirmation
  FROM public.source_artifact_confirmations
  WHERE session_id = p_session_id
  ORDER BY confirmed_at DESC, confirmation_id DESC
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'NO_CONFIRMATION',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  -- 4. Count live sources
  SELECT COUNT(*) INTO v_source_count
  FROM public.source_questions
  WHERE session_id = p_session_id;

  IF v_source_count < 1 OR v_source_count > 20 THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'INVALID_SOURCE_COUNT',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  IF jsonb_array_length(v_confirmation.result->'sources') <> v_source_count THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'SOURCE_COUNT_MISMATCH',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  -- 5. Stale check: check if any confirmed input differs from current live input
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements(v_confirmation.result->'sources') item
    LEFT JOIN public.source_artifact_heads h ON h.source_question_id = (item->>'source_question_id')::uuid
    LEFT JOIN public.source_questions q ON q.id = h.source_question_id
    WHERE h.source_revision_id IS DISTINCT FROM (item->>'source_revision_id')::uuid
       OR public._artifact_source_input(q) IS DISTINCT FROM item->'confirmed_input'
  ) THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'ARTIFACT_STALE',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  -- 6. Build confirmed sources with canonical blueprints via LEFT JOIN to detect all missing items
  SELECT 
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'source_question_id', sq.id,
          'question_no', sq.question_no,
          'source_revision_id', h.source_revision_id,
          'blueprint_revision_id', h.blueprint_revision_id,
          'source_fingerprint', sar.source_fingerprint,
          'confirmed_input', sar.confirmed_input,
          'canonical_blueprint', cbr.canonical_blueprint,
          'schema_version', cbr.schema_version
        ) ORDER BY sq.question_no ASC
      ),
      '[]'::jsonb
    ),
    COALESCE(
      jsonb_agg(sq.id ORDER BY sq.question_no ASC),
      '[]'::jsonb
    ),
    BOOL_OR(h.source_question_id IS NULL OR sar.source_revision_id IS NULL),
    BOOL_OR(h.blueprint_revision_id IS NULL),
    BOOL_OR(cbr.schema_version IS DISTINCT FROM '0.4.0')
  INTO v_sources, v_source_order, v_missing_head, v_missing_bp, v_invalid_schema
  FROM public.source_questions sq
  LEFT JOIN public.source_artifact_heads h ON h.source_question_id = sq.id
  LEFT JOIN public.source_artifact_revisions sar ON sar.source_revision_id = h.source_revision_id AND sar.source_question_id = sq.id
  LEFT JOIN public.canonical_blueprint_revisions cbr ON cbr.blueprint_revision_id = h.blueprint_revision_id
  WHERE sq.session_id = p_session_id;

  IF v_missing_head THEN
    v_ready := FALSE;
    v_reason := 'SOURCE_HEAD_MISSING';
  ELSIF v_missing_bp THEN
    v_ready := FALSE;
    v_reason := 'CANONICAL_BLUEPRINTS_INCOMPLETE';
  ELSIF v_invalid_schema THEN
    v_ready := FALSE;
    v_reason := 'INVALID_BLUEPRINT_SCHEMA_VERSION';
  END IF;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'confirmation_id', v_confirmation.confirmation_id,
    'ready', v_ready,
    'reason', v_reason,
    'confirmed_sources', v_sources,
    'source_order', v_source_order
  );
END;
$$;

REVOKE ALL ON FUNCTION public.get_generation_source_snapshot(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_generation_source_snapshot(UUID) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. Atomic Save Generation Config RPC with Canonical Readiness Validation
-- ----------------------------------------------------------------------------
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
  v_canonical_snap JSONB;
  v_is_canonical_session BOOLEAN := FALSE;
  v_canonical_dimensions JSONB := '[]'::jsonb;
BEGIN
  -- 1. Lock session row
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Ownership check
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

  -- 5. Validate variation modes structure
  IF p_active_variation_modes IS NULL OR NOT public.is_valid_variation_modes(p_active_variation_modes) THEN
    RAISE EXCEPTION 'Invalid active_variation_modes: contains unapproved mode or invalid schema'
      USING ERRCODE = '22023';
  END IF;

  -- 5a. Handle ["NONE"] normalization:
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(p_active_variation_modes) AS elem
    WHERE upper(trim(elem)) = 'NONE'
  ) THEN
    IF jsonb_array_length(p_active_variation_modes) > 1 THEN
      RAISE EXCEPTION 'Invalid active_variation_modes: NONE cannot be combined with other variation modes'
        USING ERRCODE = '22023';
    END IF;
    v_normalized_modes := '[]'::jsonb;
  ELSE
    SELECT COALESCE(
      (
        SELECT jsonb_agg(m.val)
        FROM (
          SELECT DISTINCT ON (trim(elem #>> '{}')) trim(elem #>> '{}') AS val, ord
          FROM jsonb_array_elements(p_active_variation_modes) WITH ORDINALITY AS arr(elem, ord)
          ORDER BY trim(elem #>> '{}'), ord
        ) m
      ),
      '[]'::jsonb
    ) INTO v_normalized_modes;
  END IF;

  IF v_normalized_modes IS NULL THEN
    v_normalized_modes := '[]'::jsonb;
  END IF;

  -- Reject unapproved or unsafe modes (STRUCTURAL, variable_inversion, lowercase numerical)
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(v_normalized_modes) AS m(val)
    WHERE val IN ('STRUCTURAL', 'structural', 'variable_inversion', 'scenario', 'reverse', 'visual', 'numerical')
  ) THEN
    RAISE EXCEPTION 'Invalid active_variation_modes: mode not supported or unapproved' USING ERRCODE = '22023';
  END IF;

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

  -- 8. Check Canonical Readiness First
  v_is_canonical_session := EXISTS (
    SELECT 1 FROM public.source_artifact_confirmations WHERE session_id = p_session_id
  );

  IF v_is_canonical_session THEN
    v_canonical_snap := public.get_generation_source_snapshot(p_session_id);
    IF NOT (v_canonical_snap->>'ready')::BOOLEAN THEN
      RAISE EXCEPTION 'Cannot save config: canonical blueprints not ready (%)',
        v_canonical_snap->>'reason' USING ERRCODE = '22023';
    END IF;

    -- Validate requested mode intersection against all canonical blueprints
    -- Map public alias NUMERICAL / parameter_variation -> values, context_swap -> context
    IF jsonb_array_length(v_normalized_modes) > 0 THEN
      IF EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(v_normalized_modes) AS req(m)
        WHERE (
          CASE 
            WHEN req.m IN ('NUMERICAL', 'parameter_variation') THEN 'values'
            WHEN req.m = 'context_swap' THEN 'context'
            ELSE req.m
          END
        ) NOT IN (
          -- Intersection: dimension present in EVERY source blueprint
          SELECT dim FROM (
            SELECT 
              t->>'dimension' AS dim, 
              COUNT(DISTINCT (src->>'source_question_id')::uuid) AS cnt
            FROM jsonb_array_elements(v_canonical_snap->'confirmed_sources') src,
                 jsonb_array_elements(src->'canonical_blueprint'->'requirement'->'variation_policy'->'allowed_transformations') t
            GROUP BY t->>'dimension'
          ) d WHERE d.cnt = v_source_count
        )
      ) THEN
        RAISE EXCEPTION 'Requested active_variation_modes contains a mode not supported by all source blueprints'
          USING ERRCODE = '22023';
      END IF;
    END IF;
  ELSE
    -- Legacy blueprint validation
    IF EXISTS (
      SELECT 1 FROM public.source_questions sq
      WHERE sq.session_id = p_session_id
        AND NOT EXISTS (
          SELECT 1 FROM public.question_blueprints qb
          WHERE qb.source_question_id = sq.id AND qb.confirmed_at IS NOT NULL
        )
    ) THEN
      RAISE EXCEPTION 'Not all source questions have confirmed blueprints' USING ERRCODE = '22023';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM public.source_questions sq
      JOIN public.question_blueprints qb ON qb.source_question_id = sq.id
      WHERE sq.session_id = p_session_id
        AND (
          qb.variation_modes IS NULL
          OR jsonb_typeof(qb.variation_modes) != 'array'
          OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(qb.variation_modes) AS elem
            WHERE jsonb_typeof(elem) != 'string' OR length(trim(elem #>> '{}')) = 0
          )
        )
    ) THEN
      RAISE EXCEPTION 'Invalid variation_modes in source blueprints: must be array of non-empty strings'
        USING ERRCODE = '22023';
    END IF;

    IF jsonb_array_length(v_normalized_modes) > 0 THEN
      IF EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(v_normalized_modes) AS req(mode_id)
        WHERE EXISTS (
          SELECT 1 FROM public.source_questions sq
          JOIN public.question_blueprints qb ON qb.source_question_id = sq.id
          WHERE sq.session_id = p_session_id
            AND qb.confirmed_at IS NOT NULL
            AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(qb.variation_modes) AS bp_elem(val)
              WHERE bp_elem.val = req.mode_id
            )
        )
      ) THEN
        RAISE EXCEPTION 'Requested active_variation_modes contains a mode not supported by all source blueprints'
          USING ERRCODE = '22023';
      END IF;
    END IF;
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

REVOKE EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.save_generation_config(UUID, INT, JSONB, JSONB) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5. Safe Atomic Full Result & Display Projection Persistence RPC
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.persist_generation_result(
  p_session_id UUID,
  p_job_token UUID,
  p_version_index INT,
  p_source_question_id UUID,
  p_question_no INT,
  p_is_success BOOLEAN,
  p_error_code TEXT,
  p_attempts INT,
  p_seed INT,
  p_request_fingerprint TEXT,
  p_raw_result JSONB,
  p_content TEXT DEFAULT NULL,
  p_options JSONB DEFAULT NULL,
  p_correct_key TEXT DEFAULT NULL,
  p_solution_md TEXT DEFAULT NULL,
  p_has_warning BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_version_code TEXT;
  v_version_id UUID;
  v_existing_target public.generation_target_results;
  v_existing_vq public.version_questions;
  v_vq_id UUID := NULL;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: persist_generation_result is restricted to service_role' USING ERRCODE = '42501';
  END IF;

  -- 1. Lock session row
  SELECT status, active_job_id INTO v_session_status, v_active_job_id
  FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot persist: session is not generating (current: %)', v_session_status USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing check
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session %', p_job_token, p_session_id USING ERRCODE = '55006';
  END IF;

  -- 3. Strict idempotency check on target slot
  SELECT * INTO v_existing_target
  FROM public.generation_target_results
  WHERE session_id = p_session_id
    AND version_index = p_version_index
    AND source_question_id = p_source_question_id
  FOR UPDATE;

  IF FOUND THEN
    IF v_existing_target.is_success AND p_is_success THEN
      -- Slot already committed successfully: verify payload equivalence
      IF v_existing_target.request_fingerprint = p_request_fingerprint
         AND v_existing_target.seed = p_seed THEN
        -- Replay succeeds idempotently without modifying database
        RETURN jsonb_build_object(
          'success', TRUE,
          'replayed', TRUE,
          'session_id', p_session_id,
          'version_index', p_version_index,
          'source_question_id', p_source_question_id,
          'version_question_id', v_existing_target.version_question_id
        );
      ELSE
        -- Overwriting already committed successful slot with different payload is forbidden (F03)
        RAISE EXCEPTION 'Target slot already committed with different payload for version % and source %',
          p_version_index, p_source_question_id USING ERRCODE = '23505';
      END IF;
    END IF;
  END IF;

  -- 4. If success, atomically persist version_questions display projection
  IF p_is_success THEN
    v_version_code := (100 + p_version_index)::TEXT;

    INSERT INTO public.exam_versions (session_id, version_code)
    VALUES (p_session_id, v_version_code)
    ON CONFLICT (session_id, version_code) DO NOTHING;

    SELECT id INTO v_version_id FROM public.exam_versions
    WHERE session_id = p_session_id AND version_code = v_version_code;

    -- Check if version_questions already committed
    SELECT * INTO v_existing_vq
    FROM public.version_questions
    WHERE version_id = v_version_id
      AND source_question_id = p_source_question_id
      AND is_current = TRUE
    FOR UPDATE;

    IF FOUND THEN
      IF v_existing_vq.content = p_content
         AND v_existing_vq.options = p_options
         AND v_existing_vq.correct_key = p_correct_key
         AND (v_existing_vq.solution_md IS NOT DISTINCT FROM p_solution_md) THEN
        v_vq_id := v_existing_vq.id;
      ELSE
        RAISE EXCEPTION 'Display projection already committed with different content for version % and source %',
          v_version_code, p_source_question_id USING ERRCODE = '23505';
      END IF;
    ELSE
      INSERT INTO public.version_questions (
        version_id, source_question_id, question_no,
        content, options, correct_key, solution_md,
        canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
        has_warning, status, is_current
      ) VALUES (
        v_version_id, p_source_question_id, p_question_no,
        p_content, p_options, p_correct_key, p_solution_md,
        p_question_no, p_options, p_correct_key, p_solution_md,
        COALESCE(p_has_warning, FALSE), 'pending_review', TRUE
      )
      RETURNING id INTO v_vq_id;
    END IF;
  END IF;

  -- 5. Insert or update target result
  INSERT INTO public.generation_target_results (
    session_id, job_token, version_index, source_question_id, question_no,
    is_success, error_code, attempts, seed, request_fingerprint,
    raw_result, version_question_id
  ) VALUES (
    p_session_id, p_job_token, p_version_index, p_source_question_id, p_question_no,
    p_is_success, p_error_code, p_attempts, p_seed, p_request_fingerprint,
    p_raw_result, v_vq_id
  )
  ON CONFLICT (session_id, version_index, source_question_id)
  DO UPDATE SET
    job_token = EXCLUDED.job_token,
    is_success = EXCLUDED.is_success,
    error_code = EXCLUDED.error_code,
    attempts = EXCLUDED.attempts,
    raw_result = EXCLUDED.raw_result,
    version_question_id = EXCLUDED.version_question_id,
    created_at = now();

  -- 6. Atomically update session updated_at
  UPDATE public.exam_sessions SET updated_at = now() WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'replayed', FALSE,
    'session_id', p_session_id,
    'version_index', p_version_index,
    'source_question_id', p_source_question_id,
    'version_question_id', v_vq_id
  );
END;
$$;

REVOKE ALL ON FUNCTION public.persist_generation_result(UUID, UUID, INT, UUID, INT, BOOLEAN, TEXT, INT, INT, TEXT, JSONB, TEXT, JSONB, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_result(UUID, UUID, INT, UUID, INT, BOOLEAN, TEXT, INT, INT, TEXT, JSONB, TEXT, JSONB, TEXT, TEXT, BOOLEAN) TO service_role;

-- ----------------------------------------------------------------------------
-- 6. Durable Resume Read RPC (load_generation_completed_results)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.load_generation_completed_results(
  p_session_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_results JSONB;
BEGIN
  -- 1. Read session owner
  SELECT user_id INTO v_session_user_id
  FROM public.exam_sessions WHERE id = p_session_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 2. Aggregate only successful valid QuestionResults
  SELECT COALESCE(
    jsonb_agg(
      gtr.raw_result
      ORDER BY gtr.version_index ASC, gtr.question_no ASC
    ),
    '[]'::jsonb
  ) INTO v_results
  FROM public.generation_target_results gtr
  WHERE gtr.session_id = p_session_id
    AND gtr.is_success = TRUE
    AND gtr.raw_result ? 'candidate'
    AND gtr.raw_result->>'candidate' IS NOT NULL;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'completed', v_results
  );
END;
$$;

REVOKE ALL ON FUNCTION public.load_generation_completed_results(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.load_generation_completed_results(UUID) TO authenticated, service_role;
