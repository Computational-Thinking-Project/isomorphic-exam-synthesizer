-- ============================================================================
-- Migration 017: Generation Lifecycle Recovery & Durable Interruption Error
-- TASK-207 / PR #32 DB Support for PR #30 (Author: Duy)
-- Apply after 016_stage2_original_clone.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Schema Additions: Generation Activity Timestamp & Durable Error Code
-- ----------------------------------------------------------------------------

ALTER TABLE public.exam_sessions
  ADD COLUMN IF NOT EXISTS generation_last_activity_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS generation_error_code TEXT NULL;

-- Format constraint on generation_error_code: uppercase alphanumeric and underscores only
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.exam_sessions'::regclass
      AND conname = 'chk_generation_error_code_format'
  ) THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_generation_error_code_format
      CHECK (
        generation_error_code IS NULL
        OR (generation_error_code ~ '^[A-Z0-9_]{3,64}$')
      );
  END IF;
END $$;

-- Backfill generation_last_activity_at for active generating sessions using current updated_at
UPDATE public.exam_sessions
SET generation_last_activity_at = updated_at
WHERE status = 'generating' AND generation_last_activity_at IS NULL;

-- ----------------------------------------------------------------------------
-- 2. Partial Index for Efficient Stale Job Enumeration
-- ----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_exam_sessions_generation_stale
  ON public.exam_sessions (generation_last_activity_at, id)
  WHERE status = 'generating' AND active_job_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Triggers: Generation Activity Tracking & Retry Error Clearance
-- ----------------------------------------------------------------------------

-- Trigger on exam_sessions:
-- - Sets generation_last_activity_at and clears generation_error_code on claim / retry
-- - Updates generation_last_activity_at when quota is reserved (gemini_call_count changes)
-- - Does NOT touch generation_last_activity_at when user merely edits title/subject/grade
CREATE OR REPLACE FUNCTION public.tg_exam_sessions_generation_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
  -- When claiming new job or retrying from failed/partial: status is 'generating' with new token
  IF NEW.status = 'generating' AND (OLD.active_job_id IS DISTINCT FROM NEW.active_job_id OR OLD.status IS DISTINCT FROM 'generating') THEN
    NEW.generation_error_code := NULL;
    NEW.generation_last_activity_at := clock_timestamp();
  END IF;

  -- When quota is reserved by worker: gemini_call_count increases
  IF OLD.gemini_call_count IS DISTINCT FROM NEW.gemini_call_count THEN
    NEW.generation_last_activity_at := clock_timestamp();
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_exam_sessions_generation_lifecycle ON public.exam_sessions;
CREATE TRIGGER trg_exam_sessions_generation_lifecycle
  BEFORE UPDATE ON public.exam_sessions
  FOR EACH ROW EXECUTE FUNCTION public.tg_exam_sessions_generation_lifecycle();

-- Trigger on generation_target_results:
-- - Touches generation_last_activity_at on session when a question result (AI or clone) is persisted
CREATE OR REPLACE FUNCTION public.tg_generation_target_results_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
  UPDATE public.exam_sessions
  SET generation_last_activity_at = clock_timestamp()
  WHERE id = NEW.session_id AND status = 'generating';
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_generation_target_results_activity ON public.generation_target_results;
CREATE TRIGGER trg_generation_target_results_activity
  AFTER INSERT OR UPDATE ON public.generation_target_results
  FOR EACH ROW EXECUTE FUNCTION public.tg_generation_target_results_activity();

-- ----------------------------------------------------------------------------
-- 4. Heartbeat RPC Update
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.heartbeat_generation_job(
  p_session_id UUID,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_current_status public.session_status;
  v_active_job_id UUID;
  v_activity_at TIMESTAMPTZ := clock_timestamp();
BEGIN
  IF p_job_token IS NULL THEN
    RAISE EXCEPTION 'p_job_token cannot be NULL' USING ERRCODE = '22023';
  END IF;

  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'heartbeat_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  SELECT status, active_job_id
    INTO v_current_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_current_status != 'generating' THEN
    RAISE EXCEPTION 'Session % is not generating (current: %)', p_session_id, v_current_status
      USING ERRCODE = '55006';
  END IF;

  IF v_active_job_id IS DISTINCT FROM p_job_token THEN
    RAISE EXCEPTION 'Fencing token mismatch for session %', p_session_id
      USING ERRCODE = '55006';
  END IF;

  UPDATE public.exam_sessions
  SET updated_at = now(),
      generation_last_activity_at = v_activity_at
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'heartbeat_at', v_activity_at,
    'status', 'generating'
  );
END;
$$;

REVOKE ALL ON FUNCTION public.heartbeat_generation_job(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.heartbeat_generation_job(UUID, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- 5. RPC: list_stale_generation_jobs (Keyset Pagination & Service Role Only)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.list_stale_generation_jobs(
  p_cutoff_seconds integer DEFAULT 720,
  p_limit integer DEFAULT 50,
  p_after_activity_at timestamptz DEFAULT NULL,
  p_after_session_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_scan_as_of timestamptz := clock_timestamp();
  v_cutoff_bound timestamptz;
  v_items jsonb := '[]'::jsonb;
  v_next_cursor jsonb := NULL;
  v_has_more boolean := FALSE;
  v_count int := 0;
  r record;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'list_stale_generation_jobs is restricted to service_role' USING ERRCODE = '42501';
  END IF;

  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds USING ERRCODE = '22023';
  END IF;

  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
    RAISE EXCEPTION 'p_limit must be between 1 and 100 (got %)', p_limit USING ERRCODE = '22023';
  END IF;

  IF (p_after_activity_at IS NULL AND p_after_session_id IS NOT NULL)
     OR (p_after_activity_at IS NOT NULL AND p_after_session_id IS NULL) THEN
    RAISE EXCEPTION 'Cursor components must be both provided or both NULL' USING ERRCODE = '22023';
  END IF;

  v_cutoff_bound := v_scan_as_of - make_interval(secs => p_cutoff_seconds);

  FOR r IN
    SELECT id AS session_id, active_job_id, generation_last_activity_at
    FROM public.exam_sessions
    WHERE status = 'generating'
      AND active_job_id IS NOT NULL
      AND generation_last_activity_at IS NOT NULL
      AND generation_last_activity_at < v_cutoff_bound
      AND (
        p_after_activity_at IS NULL
        OR (generation_last_activity_at > p_after_activity_at)
        OR (generation_last_activity_at = p_after_activity_at AND id > p_after_session_id)
      )
    ORDER BY generation_last_activity_at ASC, id ASC
    LIMIT (p_limit + 1)
  LOOP
    v_count := v_count + 1;
    IF v_count <= p_limit THEN
      v_items := v_items || jsonb_build_array(jsonb_build_object(
        'session_id', r.session_id,
        'job_token', r.active_job_id,
        'last_activity_at', r.generation_last_activity_at
      ));
    ELSE
      v_has_more := TRUE;
    END IF;
  END LOOP;

  IF v_has_more THEN
    v_next_cursor := jsonb_build_object(
      'last_activity_at', (v_items->(p_limit - 1))->>'last_activity_at',
      'session_id', (v_items->(p_limit - 1))->>'session_id'
    );
  END IF;

  RETURN jsonb_build_object(
    'scan_as_of', v_scan_as_of,
    'cutoff_seconds', p_cutoff_seconds,
    'items', v_items,
    'next_cursor', v_next_cursor,
    'has_more', v_has_more
  );
END;
$$;

REVOKE ALL ON FUNCTION public.list_stale_generation_jobs(integer, integer, timestamptz, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_stale_generation_jobs(integer, integer, timestamptz, uuid) TO service_role;

-- ----------------------------------------------------------------------------
-- 6. RPC: fail_stale_generation_job_if_current (Fencing & Atomic Error Code)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.fail_stale_generation_job_if_current(
  p_session_id uuid,
  p_expected_job_token uuid,
  p_cutoff_seconds integer DEFAULT 720
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_status public.session_status;
  v_active_job_id uuid;
  v_activity_at timestamptz;
  v_cutoff_bound timestamptz;
  v_now timestamptz := clock_timestamp();
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'fail_stale_generation_job_if_current is restricted to service_role' USING ERRCODE = '42501';
  END IF;

  IF p_session_id IS NULL THEN
    RAISE EXCEPTION 'p_session_id cannot be NULL' USING ERRCODE = '22023';
  END IF;

  IF p_expected_job_token IS NULL THEN
    RAISE EXCEPTION 'p_expected_job_token cannot be NULL' USING ERRCODE = '22023';
  END IF;

  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds USING ERRCODE = '22023';
  END IF;

  v_cutoff_bound := v_now - make_interval(secs => p_cutoff_seconds);

  SELECT status, active_job_id, coalesce(generation_last_activity_at, updated_at)
    INTO v_status, v_active_job_id, v_activity_at
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- Fencing token, status, and timeout verification
  IF v_status = 'generating'
     AND v_active_job_id IS NOT DISTINCT FROM p_expected_job_token
     AND v_activity_at < v_cutoff_bound THEN

    UPDATE public.exam_sessions
    SET status = 'failed',
        active_job_id = NULL,
        generation_error_code = 'ERR_GENERATION_INTERRUPTED',
        updated_at = v_now
    WHERE id = p_session_id;

    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'recovered', true,
      'previous_job_id', v_active_job_id,
      'status', 'failed',
      'error_code', 'ERR_GENERATION_INTERRUPTED'
    );
  END IF;

  -- Condition not met: job finished, retried with new token, or has recent activity
  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'recovered', false,
    'current_status', v_status::text,
    'current_job_id', v_active_job_id,
    'reason', CASE
      WHEN v_status != 'generating' THEN 'status_not_generating'
      WHEN v_active_job_id IS DISTINCT FROM p_expected_job_token THEN 'token_mismatch'
      ELSE 'activity_not_stale'
    END
  );
END;
$$;

REVOKE ALL ON FUNCTION public.fail_stale_generation_job_if_current(uuid, uuid, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fail_stale_generation_job_if_current(uuid, uuid, integer) TO service_role;

-- ----------------------------------------------------------------------------
-- 7. Upgraded fail_stale_generation_job (Backwards Compatible Signature)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.fail_stale_generation_job(
  p_session_id UUID,
  p_cutoff_seconds INT DEFAULT 720
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_current_status public.session_status;
  v_activity_at TIMESTAMPTZ;
  v_old_job_id UUID;
  v_recovered BOOLEAN := FALSE;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds
      USING ERRCODE = '22023';
  END IF;

  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'fail_stale_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  SELECT status, coalesce(generation_last_activity_at, updated_at), active_job_id
    INTO v_current_status, v_activity_at, v_old_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_current_status = 'generating'
     AND v_activity_at < (v_now - make_interval(secs => p_cutoff_seconds)) THEN
    UPDATE public.exam_sessions
    SET status = 'failed',
        active_job_id = NULL,
        generation_error_code = 'ERR_GENERATION_INTERRUPTED',
        updated_at = v_now
    WHERE id = p_session_id;
    v_recovered := TRUE;
  END IF;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'stale_job_recovered', v_recovered,
    'old_active_job_id', v_old_job_id,
    'current_status', CASE WHEN v_recovered THEN 'failed' ELSE v_current_status::text END
  );
END;
$$;

REVOKE ALL ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;

-- ----------------------------------------------------------------------------
-- 8. RPC: finish_generation_job_with_error (Persist Failure Code Atomically)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.finish_generation_job_with_error(
  p_session_id uuid,
  p_outcome text,
  p_job_token uuid,
  p_error_code text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_receipt jsonb;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Worker only' USING ERRCODE = '42501';
  END IF;

  IF p_outcome IS NULL OR p_outcome NOT IN ('generated', 'failed', 'partial_generated') THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid generation outcome: %', p_outcome USING ERRCODE = '22023';
  END IF;

  IF p_outcome = 'generated' AND p_error_code IS NOT NULL THEN
    RAISE EXCEPTION 'Cannot specify error_code for generated outcome' USING ERRCODE = '22023';
  END IF;

  IF p_error_code IS NOT NULL AND p_error_code !~ '^[A-Z0-9_]{3,64}$' THEN
    RAISE EXCEPTION 'Invalid error code format: %', p_error_code USING ERRCODE = '22023';
  END IF;

  -- Delegate to canonical finish_generation_job to retain completeness validations
  v_receipt := public.finish_generation_job(p_session_id, p_outcome, p_job_token);

  -- Record generation_error_code atomically
  IF p_outcome IN ('failed', 'partial_generated') THEN
    UPDATE public.exam_sessions
    SET generation_error_code = p_error_code
    WHERE id = p_session_id;
  ELSE
    UPDATE public.exam_sessions
    SET generation_error_code = NULL
    WHERE id = p_session_id;
  END IF;

  RETURN v_receipt || jsonb_build_object('generation_error_code', p_error_code);
END;
$$;

REVOKE ALL ON FUNCTION public.finish_generation_job_with_error(uuid, text, uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_generation_job_with_error(uuid, text, uuid, text) TO service_role;

-- ----------------------------------------------------------------------------
-- 9. Upgraded load_generation_completed_results (Returns generation_error_code)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.load_generation_completed_results(p_session_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions;
  job public.generation_job_snapshots;
  completed jsonb;
  failures jsonb;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;

  IF public.current_role() != 'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing resume snapshot' USING ERRCODE = '55006';
  END IF;

  PERFORM public._generation_assert_result_kind(s.id, job.id);

  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'snapshot_id', r.snapshot_id,
    'version_index', r.version_index,
    'source_question_id', r.source_question_id,
    'question_no', r.question_no,
    'is_success', true,
    'seed', r.seed,
    'request_fingerprint', r.request_fingerprint,
    'raw_result', r.raw_result,
    'result_kind', r.result_kind,
    'clone_fingerprint', r.clone_fingerprint
  ) ORDER BY r.version_index, r.question_no), '[]')
  INTO completed
  FROM public._generation_committed(s.id, job.id) r;

  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'snapshot_id', r.snapshot_id,
    'version_index', r.version_index,
    'source_question_id', r.source_question_id,
    'question_no', r.question_no,
    'is_success', false,
    'seed', r.seed,
    'request_fingerprint', r.request_fingerprint,
    'raw_result', r.raw_result,
    'result_kind', r.result_kind,
    'clone_fingerprint', r.clone_fingerprint
  ) ORDER BY r.version_index, r.question_no), '[]')
  INTO failures
  FROM public.generation_target_results r
  WHERE r.session_id = s.id AND r.snapshot_id = job.id AND NOT r.is_success;

  RETURN jsonb_build_object(
    'session_id', s.id,
    'snapshot_id', job.id,
    'context', job.snapshot_payload,
    'completed', completed,
    'failures', failures,
    'generation_error_code', s.generation_error_code
  );
END;
$$;

REVOKE ALL ON FUNCTION public.load_generation_completed_results(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.load_generation_completed_results(uuid) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 10. Least Privilege: Deny Direct Writes to New Columns
-- ----------------------------------------------------------------------------

REVOKE UPDATE (generation_last_activity_at, generation_error_code) ON TABLE public.exam_sessions FROM PUBLIC, anon, authenticated;

COMMIT;

