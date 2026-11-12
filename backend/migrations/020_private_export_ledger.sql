-- W4-MVP-08. Forward-only; 019 belongs to PR #61. No dependency on 019 DDL.
-- Apply via the approved manifest, never infer shared-DB application from Git.
BEGIN;

CREATE TABLE public.private_export_ledger (
  session_id uuid NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  packaging_key text NOT NULL CHECK (packaging_key ~ '^[0-9a-f]{64}$'),
  revision text NOT NULL CHECK (revision ~ '^sha256:[0-9a-f]{64}$'),
  packager_version text NOT NULL,
  approved_at timestamptz NOT NULL,
  snapshot_title text NOT NULL,
  state text NOT NULL CHECK (state IN ('preparing','ready','failed')),
  phase text NOT NULL CHECK (phase IN ('build','recover')),
  token uuid NOT NULL,
  lease_until timestamptz NOT NULL,
  expected jsonb,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(session_id,packaging_key),
  CHECK (state <> 'ready' OR expected IS NOT NULL),
  CHECK ((state='failed') = (error_code IS NOT NULL))
);
ALTER TABLE public.private_export_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.private_export_ledger FROM PUBLIC,anon,authenticated,service_role;

-- One privileged RPC with explicit operations; read performs no DML or row lock.
-- The server must first load snapshot07 through its verified user's RLS client.
CREATE FUNCTION public.private_export_ledger_command(
  p_session_id uuid, p_actor_id uuid, p_identity jsonb, p_action text,
  p_token uuid DEFAULT NULL, p_receipt jsonb DEFAULT NULL, p_reason text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  s public.exam_sessions%ROWTYPE;
  r public.private_export_ledger%ROWTYPE;
  k text; rev text; ver text; result_state text;
  receipt_keys integer;
BEGIN
  -- Check actual invoker role, not auth.role()/untrusted JWT role claims.
  IF coalesce(nullif(current_setting('role',true),'none'),session_user)<>'service_role' THEN
    RAISE EXCEPTION 'ERR_UNAUTHORIZED' USING ERRCODE='42501';
  END IF;
  IF p_action IS NULL OR p_action NOT IN ('read','claim','checkpoint','complete','fail','restart') THEN
    RAISE EXCEPTION 'ERR_EXPORT_INVALID_COMMAND';
  END IF;
  IF p_action='read' THEN
    SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id;
  ELSE
    -- Root-first locks serialize all claims and lifecycle completion for a session.
    SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
  END IF;
  IF NOT FOUND OR p_actor_id IS NULL OR s.user_id IS DISTINCT FROM p_actor_id THEN
    RAISE EXCEPTION 'ERR_UNAUTHORIZED' USING ERRCODE='42501';
  END IF;
  IF s.status NOT IN ('approved','exported') OR s.approved_at IS NULL THEN
    RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE';
  END IF;
  rev:=p_identity->>'revision'; ver:=p_identity->>'packager_version';
  k:=p_identity->>'packaging_key';
  IF jsonb_typeof(p_identity) IS DISTINCT FROM 'object'
     OR rev IS NULL OR rev !~ '^sha256:[0-9a-f]{64}$'
     OR ver IS NULL OR ver !~ '^[a-zA-Z0-9_.-]{1,64}$'
     OR k IS DISTINCT FROM encode(sha256(convert_to(ver||E'\n'||rev,'UTF8')),'hex') THEN
    RAISE EXCEPTION 'ERR_EXPORT_IDENTITY_INVALID';
  END IF;
  IF p_action='read' THEN
    SELECT * INTO r FROM public.private_export_ledger WHERE session_id=p_session_id AND packaging_key=k;
  ELSE
    SELECT * INTO r FROM public.private_export_ledger WHERE session_id=p_session_id AND packaging_key=k FOR UPDATE;
  END IF;
  IF r.session_id IS NOT NULL AND (r.revision<>rev OR r.packager_version<>ver
     OR r.approved_at IS DISTINCT FROM s.approved_at OR r.snapshot_title IS DISTINCT FROM s.title) THEN
    RAISE EXCEPTION 'ERR_EXPORT_IDENTITY_INVALID';
  END IF;

  IF p_action='read' THEN
    IF r.session_id IS NULL THEN RETURN jsonb_build_object('state','idle'); END IF;
  ELSIF p_action='claim' THEN
    IF r.session_id IS NULL THEN
      INSERT INTO public.private_export_ledger(session_id,packaging_key,revision,packager_version,
        approved_at,snapshot_title,state,phase,token,lease_until)
      VALUES(p_session_id,k,rev,ver,s.approved_at,s.title,'preparing','build',gen_random_uuid(),
        clock_timestamp()+interval '900 seconds') RETURNING * INTO r;
      result_state:='claimed';
    ELSIF r.state='ready' THEN result_state:='ready';
    ELSIF r.state='preparing' AND r.lease_until>clock_timestamp() THEN result_state:='pending';
    ELSE
      -- Keep the OLD object receipt but grant NEW fencing authority for recovery.
      UPDATE public.private_export_ledger SET token=gen_random_uuid(),state='preparing',error_code=NULL,
        phase=CASE WHEN expected IS NULL THEN 'build' ELSE 'recover' END,
        lease_until=clock_timestamp()+interval '900 seconds',updated_at=clock_timestamp()
      WHERE session_id=p_session_id AND packaging_key=k RETURNING * INTO r;
      result_state:=CASE WHEN r.expected IS NULL THEN 'claimed' ELSE 'recovering' END;
    END IF;
  ELSE
    IF r.session_id IS NULL OR p_token IS NULL OR r.token IS DISTINCT FROM p_token THEN
      RAISE EXCEPTION 'ERR_EXPORT_STALE_ATTEMPT';
    END IF;
    -- Replays of committed completion/checkpoint/failure are idempotent only
    -- for exactly matching input. No replay can revert an existing ready row.
    IF r.state='ready' AND p_action IN ('complete','checkpoint') AND r.expected=p_receipt THEN
      RETURN jsonb_build_object('state','ready','token',r.token,'receipt',r.expected);
    END IF;
    IF r.state='failed' AND p_action='fail' AND r.error_code=p_reason THEN
      RETURN jsonb_build_object('state','failed','error_code',r.error_code);
    END IF;
    IF r.state<>'preparing' OR r.lease_until<=clock_timestamp() THEN
      RAISE EXCEPTION 'ERR_EXPORT_STALE_ATTEMPT';
    END IF;
    IF p_action='checkpoint' THEN
      IF r.phase<>'build' OR jsonb_typeof(p_receipt) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      SELECT count(*) INTO receipt_keys FROM jsonb_object_keys(p_receipt);
      IF receipt_keys<>4 OR p_receipt->>'object_path' IS DISTINCT FROM
          p_session_id::text||'/'||k||'/'||p_token::text||'.zip'
        OR p_receipt->>'filename' IS DISTINCT FROM 'exam_bundle_'||p_session_id::text||'.zip'
        OR coalesce(p_receipt->>'sha256','') !~ '^[0-9a-f]{64}$'
        OR jsonb_typeof(p_receipt->'sha256') IS DISTINCT FROM 'string'
        OR jsonb_typeof(p_receipt->'size_bytes') IS DISTINCT FROM 'number'
        OR (p_receipt->>'size_bytes') !~ '^[0-9]{1,9}$' THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      IF (p_receipt->>'size_bytes')::bigint NOT BETWEEN 1 AND 104857600
        OR (r.expected IS NOT NULL AND r.expected IS DISTINCT FROM p_receipt) THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      UPDATE public.private_export_ledger SET expected=p_receipt,updated_at=clock_timestamp()
        WHERE session_id=p_session_id AND packaging_key=k RETURNING * INTO r;
    ELSIF p_action='complete' THEN
      IF r.expected IS NULL OR r.expected IS DISTINCT FROM p_receipt THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      UPDATE public.private_export_ledger SET state='ready',updated_at=clock_timestamp()
        WHERE session_id=p_session_id AND packaging_key=k RETURNING * INTO r;
      UPDATE public.exam_sessions SET status='exported' WHERE id=p_session_id AND status='approved';
    ELSIF p_action='fail' THEN
      IF r.expected IS NOT NULL OR p_reason IS NULL OR p_reason NOT IN
        ('ERR_EXPORT_BUILD_FAILED','ERR_EXPORT_COMPILER_UNAVAILABLE') THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      UPDATE public.private_export_ledger SET state='failed',error_code=p_reason,updated_at=clock_timestamp()
        WHERE session_id=p_session_id AND packaging_key=k RETURNING * INTO r;
    ELSIF p_action='restart' THEN
      IF r.phase<>'recover' OR r.expected IS NULL OR r.expected IS DISTINCT FROM p_receipt
        OR p_reason IS NULL OR p_reason NOT IN ('missing','checksum_mismatch') THEN
        RAISE EXCEPTION 'ERR_EXPORT_RECEIPT_INVALID';
      END IF;
      -- Backend attests conclusive verification failure. A timeout is not missing.
      UPDATE public.private_export_ledger SET expected=NULL,phase='build',token=gen_random_uuid(),
        lease_until=clock_timestamp()+interval '900 seconds',updated_at=clock_timestamp()
        WHERE session_id=p_session_id AND packaging_key=k RETURNING * INTO r;
      result_state:='claimed';
    END IF;
  END IF;
  result_state:=coalesce(result_state,CASE WHEN r.state='preparing' THEN 'pending' ELSE r.state END);
  RETURN jsonb_build_object('state',result_state,'token',r.token,'receipt',
    CASE WHEN result_state IN ('ready','recovering') THEN r.expected ELSE NULL END,
    'error_code',r.error_code);
END $$;
REVOKE ALL ON FUNCTION public.private_export_ledger_command(uuid,uuid,jsonb,text,uuid,jsonb,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.private_export_ledger_command(uuid,uuid,jsonb,text,uuid,jsonb,text)
  TO service_role;

-- Narrow the known historical policy, preserving raw/source bucket behavior.
DROP POLICY "User storage isolated access" ON storage.objects;
CREATE POLICY "User storage isolated access" ON storage.objects FOR ALL USING (
  bucket_id IN ('exam-raw-files','exam-sources') AND (storage.foldername(name))[1] IN
    (SELECT id::text FROM public.exam_sessions WHERE user_id=auth.uid())
) WITH CHECK (
  bucket_id IN ('exam-raw-files','exam-sources') AND (storage.foldername(name))[1] IN
    (SELECT id::text FROM public.exam_sessions WHERE user_id=auth.uid())
);
-- Preserve historical owner reads; Q09 removes mutation rights, not SELECT.
CREATE POLICY "User export read access" ON storage.objects FOR SELECT TO authenticated USING (
  bucket_id='exam-export-bundles' AND (storage.foldername(name))[1] IN
    (SELECT id::text FROM public.exam_sessions WHERE user_id=auth.uid())
);
-- Restrictive guards also protect against other permissive policies on a project.
CREATE POLICY "Export backend insert only" ON storage.objects AS RESTRICTIVE FOR INSERT TO anon,authenticated
  WITH CHECK (bucket_id IS DISTINCT FROM 'exam-export-bundles');
CREATE POLICY "Export backend update only" ON storage.objects AS RESTRICTIVE FOR UPDATE TO anon,authenticated
  USING (bucket_id IS DISTINCT FROM 'exam-export-bundles') WITH CHECK (bucket_id IS DISTINCT FROM 'exam-export-bundles');
CREATE POLICY "Export backend delete only" ON storage.objects AS RESTRICTIVE FOR DELETE TO anon,authenticated
  USING (bucket_id IS DISTINCT FROM 'exam-export-bundles');
COMMIT;
