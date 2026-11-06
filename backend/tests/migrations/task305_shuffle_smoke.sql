\set ON_ERROR_STOP on
INSERT INTO auth.users(id,email) VALUES ('00000000-0000-0000-0000-000000000001','fixture@example.invalid');
INSERT INTO public.exam_sessions(id,user_id,title,status) VALUES
 ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Fixture','reviewed');
INSERT INTO public.generation_configs(id,session_id,n_versions,ordering_preferences) VALUES
 ('90000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',1,
  '{"shuffle_questions":false,"shuffle_options":false}');
INSERT INTO public.source_questions(id,session_id,question_no,raw_content,options,correct_key) VALUES
 ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',1,'source','{}','A');
INSERT INTO public.question_blueprints(source_question_id,confirmed_at) VALUES
 ('20000000-0000-0000-0000-000000000001',now());
INSERT INTO public.exam_versions(id,session_id,version_code) VALUES
 ('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','101');
INSERT INTO public.version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
 canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,solution_md,status,is_current)
 VALUES ('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',
 '20000000-0000-0000-0000-000000000001',1,'stem','["a","b","c","d"]','A',1,
 '["a","b","c","d"]','A','Chọn A','Chọn A','approved',true);

CREATE FUNCTION public.test_shuffle_payload() RETURNS jsonb LANGUAGE sql AS $$
 SELECT jsonb_build_object('snapshot',jsonb_build_object(
 'config',(SELECT jsonb_build_object('id',id,'session_id',session_id,'n_versions',n_versions,'ordering_preferences',ordering_preferences) FROM public.generation_configs LIMIT 1),
 'versions',(SELECT jsonb_agg(jsonb_build_object('id',id,'session_id',session_id,'version_code',version_code)) FROM public.exam_versions),
 'sources',(SELECT jsonb_agg(jsonb_build_object('id',id,'session_id',session_id,'question_no',question_no)) FROM public.source_questions),
 'questions',(SELECT jsonb_agg(jsonb_build_object('id',id,'version_id',version_id,'source_question_id',source_question_id,'content',content,'canonical_question_no',canonical_question_no,'canonical_options',canonical_options,'canonical_correct_key',canonical_correct_key,'canonical_solution_md',canonical_solution_md,'status',status,'is_current',is_current)) FROM public.version_questions)),
 'versions',jsonb_build_array(jsonb_build_object('version_id','30000000-0000-0000-0000-000000000001','version_code','101',
 'shuffle_seed',encode(sha256(convert_to('10000000-0000-0000-0000-000000000001_101','UTF8')),'hex'),'total_questions',1,
 'questions',jsonb_build_array(jsonb_build_object('id','40000000-0000-0000-0000-000000000001','source_question_id','20000000-0000-0000-0000-000000000001',
 'display_no',1,'content','stem','is_current',true,'options','["a","b","c","d"]'::jsonb,'display_correct_key','A','solution_md','Chọn A',
 'canonical_question_no',1,'canonical_options','["a","b","c","d"]'::jsonb,'canonical_correct_key','A','canonical_solution_md','Chọn A',
 'permutation_map','{"A":"A","B":"B","C":"C","D":"D"}'::jsonb)),
 'answer_keys',jsonb_build_array(jsonb_build_object('version_id','30000000-0000-0000-0000-000000000001','display_no',1,'display_correct_key','A','canonical_question_no',1)),
 'permutations','{"question_order":[1],"display_to_canonical":{"1":1},"canonical_to_display":{"1":1},"option_permutations":{"1":{"A":"A","B":"B","C":"C","D":"D"}}}'::jsonb)));
$$;
UPDATE public.exam_sessions SET status='reviewed' WHERE id='10000000-0000-0000-0000-000000000001';
DO $$ BEGIN
 IF public._finalize_sync_solution('Chọn A','A','B') <> 'Chọn B' THEN
   RAISE EXCEPTION 'solution synchronization mismatch';
 END IF;
END $$;
SELECT set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
SELECT public.finalize_persist_shuffle('10000000-0000-0000-0000-000000000001',public.test_shuffle_payload());
DO $$ BEGIN
 IF (SELECT count(*) FROM public.answer_keys) <> 1 OR NOT (SELECT is_finalized FROM public.exam_versions LIMIT 1) THEN
   RAISE EXCEPTION 'persist postcondition failed';
 END IF;
END $$;
