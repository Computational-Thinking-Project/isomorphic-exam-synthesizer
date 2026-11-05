"""Canonical profile 1.0 on real SQL heads, never legacy Blueprint rows."""
import json
import unittest
from copy import deepcopy
from uuid import uuid4

import test_source_confirmation_revision as revision_fixtures
from test_review_rpcs import SID
from test_stage3_schema import ROOT


class SupportedModeTests(revision_fixtures.SourceRevisionTests):
    def setUp(self):
        super().setUp()
        self.sql((ROOT / 'backend/migrations/012_source_artifact_supported_modes.sql').read_text(encoding='utf-8'))

    def state(self):
        return self.call('get_source_artifacts', SID, worker=False)

    def test_single_rpc_modes_pending_running_failed_ready(self):
        self.confirm()
        self.assertIsNone(self.state()['supported_modes'])
        job = str(uuid4())
        self.call('claim_source_production', SID, self.sources[0]['source_revision_id'], job)
        self.assertEqual(self.state()['production'][0]['status'], 'running')
        self.assertIsNone(self.state()['supported_modes'])
        self.call('fail_source_production', SID, self.sources[0]['source_revision_id'], job, 'FIXTURE_FAILURE')
        self.assertEqual(self.state()['production'][0]['status'], 'failed')
        self.assertIsNone(self.state()['supported_modes'])
        self.publish()
        state = self.state()
        self.assertTrue(state['ready'])
        self.assertEqual([m['id'] for m in state['supported_modes']], ['NUMERICAL','context_swap','parameter_variation'])
        self.assertTrue(all(m['question_count']==1 and m['is_available'] is True for m in state['supported_modes']))

    def test_none_only_is_valid_ready_empty_array(self):
        from app.services.blueprint.artifacts import prepare_blueprint_artifact
        document = deepcopy(self.blueprint)
        policy = document['requirement']['variation_policy']
        policy['allowed_transformations'] = [t for t in policy['allowed_transformations'] if t['dimension']=='wording']
        publication = prepare_blueprint_artifact(self.sources[0], document)
        publication['producer_job_id'] = str(uuid4())
        self.confirm()
        self.publish(publication)
        state = self.state()
        self.assertTrue(state['ready'])
        self.assertEqual(state['supported_modes'], [])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(SupportedModeTests(name) for name in
        sorted(SupportedModeTests.__dict__) if name.startswith('test_'))
