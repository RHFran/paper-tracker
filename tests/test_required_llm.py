"""Fail-closed live model contracts; every provider and mail transport is synthetic."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from literature_digest.analysis import FIELDS
from literature_digest.cli import main
from literature_digest.config import DEFAULTS
from literature_digest.http import RetrievalError
from literature_digest.models import Paper
from literature_digest.pipeline import run, config_fingerprint, digest_id, verify_payload_config
from literature_digest.mail import send_smtp
from literature_digest.state import State, state_scope
from model_fixture import perspective_fixture, outlook_fixture
ENV = {'LITERATURE_LLM_BASE_URL': 'https://model.example.org/v1', 'LITERATURE_LLM_API_KEY': 'synthetic-review-token', 'LITERATURE_LLM_MODEL': 'synthetic-model'}
EVIDENCE = 'The synthetic battery experiment measured reversible capacity at room temperature.'
ANCHOR = 'measured reversible capacity at room temperature'

class ReviewModel:

    def __init__(self, mode='success'):
        self.mode = mode
        self.calls = []

    def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        content = json.loads(kwargs['payload']['messages'][1]['content'])
        overview = 'untrusted_grounded_papers' in content
        outlook = 'untrusted_outlook_papers' in content
        if self.mode == 'failure' or (self.mode == 'overview_failure' and overview) or (self.mode == 'outlook_failure' and outlook):
            raise RetrievalError('synthetic model failure: do not emit this secret-review-marker')
        if self.mode == 'malformed':
            return {'choices': []}
        if self.mode == 'bad_json':
            return {'choices': [{'message': {'content': 'not json'}}]}
        if outlook:
            data = outlook_fixture([{'ref': source['ref'], 'evidence': ANCHOR}
                                    for source in content['untrusted_outlook_papers']])
        elif overview:
            source = content['untrusted_grounded_papers'][0]
            data = {'paragraphs': [{'sentences': [{'text': 'The synthetic study reports a controlled battery experiment.', 'citations': [{'ref': source['ref'], 'evidence': ANCHOR}]}]}]}
        else:
            data = {k: [] for k in FIELDS}
            if self.mode != 'empty':
                data['findings'] = [{'text': 'The synthetic study measured room-temperature reversible capacity.', 'evidence': ANCHOR if self.mode != 'fabricated' else 'This fabricated phrase is absent from source evidence.'}]
                data['question'] = [{'text': 'The fixture examines room-temperature battery capacity.', 'evidence': ANCHOR}]
                data['methods'] = [{'text': 'The fixture measures capacity at room temperature.', 'evidence': ANCHOR}]
            data = {'fields': data, 'perspective': perspective_fixture(ANCHOR)}
        return {'choices': [{'message': {'content': json.dumps(data)}}]}

class RequiredLLMReview(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update(timezone='UTC', language='en', state_path=str(Path(self.tmp.name) / 'state.db'), output_dir=str(Path(self.tmp.name) / 'out'), sources=['crossref'], topics=[{'id': 'battery', 'name': 'Battery', 'queries': ['battery'], 'include_any': ['battery']}])
        self.c['llm']['enabled'] = True
        self.now = datetime(2026, 10, 5, 9, tzinfo=timezone.utc)
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch('literature_digest.http.HttpClient.request', side_effect=AssertionError('Real network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def paper(self):
        day = self.now.date()
        return Paper(title='Synthetic battery study', source='crossref', source_id='review', doi='10.9999/review-required', url='https://example.org/review', abstract=EVIDENCE, provenance=[{'date_fields': {'published-online': {'date-parts': [[day.year, day.month, day.day]]}}}])

    def fetch(self):
        return {'crossref': lambda *args: ([self.paper()], {'complete': True})}

    def assert_never_prepared(self):
        if Path(self.c['state_path']).exists():
            state = State(self.c['state_path'], scope=state_scope(self.c))
            try:
                self.assertEqual(state.recent(), [])
            finally:
                state.close()

    def test_disabled_llm_fails_before_retrieval_and_state(self):
        self.c['llm']['enabled'] = False
        with self.assertRaisesRegex((ValueError, RuntimeError), '(?i)llm|model'):
            run(self.c, now=self.now, fetchers={'crossref': lambda *a: self.fail('retrieval before setup')})
        self.assertFalse(Path(self.c['state_path']).exists())

    def test_each_missing_model_env_fails_early(self):
        for key in ENV:
            with self.subTest(key=key), patch.dict(os.environ, {key: ''}):
                with self.assertRaisesRegex((ValueError, RuntimeError), '(?i)llm|model|environment'):
                    run(self.c, now=self.now, fetchers={'crossref': lambda *a: self.fail('retrieval before setup')})
        self.assertFalse(Path(self.c['state_path']).exists())

    def test_invalid_endpoint_fails_early(self):
        for url in ['http://model.example.org/v1', 'https://u:p@model.example.org/v1', 'https://model.example.org/v1?token=secret']:
            with self.subTest(url=url), patch.dict(os.environ, {'LITERATURE_LLM_BASE_URL': url}):
                with self.assertRaisesRegex((ValueError, RuntimeError), '(?i)https|endpoint|credential'):
                    run(self.c, now=self.now, fetchers={'crossref': lambda *a: self.fail('retrieval before setup')})

    def test_model_failures_never_prepare_or_send(self):
        for mode in ['failure', 'malformed', 'bad_json', 'empty', 'fabricated', 'overview_failure', 'outlook_failure']:
            with self.subTest(mode=mode):
                with self.assertRaises((ValueError, RuntimeError)) as raised:
                    run(self.c, send=True, now=self.now, http=ReviewModel(mode), fetchers=self.fetch(), mail_adapter=lambda *a: self.fail('Invalid analysis sent'))
                self.assertNotIn('secret-review-marker', str(raised.exception))
                self.assert_never_prepared()
                self.assertFalse(Path(self.c['output_dir']).exists(), 'Failure must not look like successful output')

    def test_success_runs_paper_model_overview_and_outlook(self):
        http = ReviewModel()
        sent = []

        def mail(payload, c, state, id_):
            sent.append(payload)
            state.mark_sent(id_)
        result = run(self.c, send=True, now=self.now, http=http, fetchers=self.fetch(), mail_adapter=mail)
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['analysis_policy'], 'required-v1')
        audit = json.loads(Path(result['paths']['json']).read_text(encoding="utf-8"))
        self.assertEqual(audit['papers'][0]['analysis']['mode'], 'llm_grounded')
        self.assertEqual(audit['overview']['mode'], 'llm_grounded')
        self.assertEqual(audit['outlook']['mode'], 'llm_grounded')
        self.assertIn('perspective', audit['papers'][0]['analysis'])
        self.assertIn('measured room-temperature reversible capacity', sent[0]['text'])

    def test_empty_real_result_is_factual_not_model_failure(self):
        http = ReviewModel()
        result = run(self.c, now=self.now, http=http, fetchers={'crossref': lambda *a: ([], {'complete': True})})
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['paper_count'], 0)
        self.assertEqual(http.calls, [])

    def test_legacy_prepared_snapshot_cannot_bypass_quality_policy(self):
        payload = {'recipient': self.c['recipient'], 'profile_id': 'default', 'config_fingerprint': config_fingerprint(self.c), 'subject': 'legacy discovery', 'text': 'discovery', 'html': '<p>discovery</p>', 'aliases': [], 'harvest_until': self.now.date().isoformat(), 'paths': {}}
        id_ = digest_id(self.c, self.now.date())
        state = State(self.c['state_path'], scope=state_scope(self.c))
        state.prepare(id_, payload)
        state.close()
        with self.assertRaises((ValueError, RuntimeError)):
            run(self.c, send=True, now=self.now, http=ReviewModel(), fetchers=self.fetch(), mail_adapter=lambda *a: self.fail('Legacy discovery replayed'))
        with self.assertRaises((ValueError, RuntimeError)):
            verify_payload_config(payload, self.c)

    def test_direct_mail_boundary_rejects_legacy_payload(self):
        payload = {'recipient': self.c['recipient'], 'subject': 'legacy discovery', 'text': 'discovery', 'html': '<p>discovery</p>', 'aliases': [], 'harvest_until': self.now.date().isoformat()}
        self.c['mail']['enabled'] = True
        with patch.dict(os.environ, {'LITERATURE_SMTP_HOST': 'smtp.example.org', 'LITERATURE_SMTP_USER': 'user', 'LITERATURE_SMTP_PASSWORD': 'synthetic-password', 'LITERATURE_MAIL_FROM': 'sender@example.org'}):
            state = State(self.c['state_path'], scope=state_scope(self.c))
            self.addCleanup(state.close)
            state.prepare('legacy', payload)
            with self.assertRaisesRegex((ValueError, RuntimeError), '(?i)analysis|llm|model|editorial|policy|legacy'):
                send_smtp(payload, self.c, state, 'legacy', smtp_ssl=lambda *a, **kw: self.fail('SMTP attempted for legacy discovery'), now=self.now)

    def test_cli_real_run_disabled_is_clear_error_not_network(self):
        self.c['llm']['enabled'] = False
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps(self.c))
        out, err = (io.StringIO(), io.StringIO())
        with redirect_stdout(out), redirect_stderr(err):
            result = main(['--config', str(path), 'run'])
        self.assertNotEqual(result, 0)
        self.assertRegex(out.getvalue() + err.getvalue(), '(?i)llm|model')
        self.assertFalse(Path(self.c['state_path']).exists())

    def test_cli_preview_needs_no_model_credentials(self):
        self.c['llm']['enabled'] = False
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps(self.c))
        out = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            self.assertEqual(main(['--config', str(path), 'preview', '--language', 'en']), 0)
        self.assertFalse(Path(self.c['state_path']).exists())
        result = json.loads(out.getvalue())[0]
        audit = json.loads(Path(result['paths']['json']).read_text(encoding="utf-8"))
        self.assertTrue(audit['meta']['synthetic'])

    def test_missing_source_evidence_is_excluded_and_audited(self):
        paper = self.paper()
        paper.abstract = ''
        http = ReviewModel()
        result = run(self.c, now=self.now, http=http, fetchers={'crossref': lambda *args: ([paper], {'complete': True})})
        self.assertEqual(result['paper_count'], 0)
        self.assertEqual(http.calls, [])
        audit = json.loads(Path(result['paths']['json']).read_text(encoding="utf-8"))
        self.assertEqual(audit['meta']['insufficient_evidence'], 1)
        self.assertEqual(audit['papers'], [])
        self.assertIn('Insufficient source evidence', audit['excluded'][0]['reason'])

    def test_missing_evidence_does_not_consume_topic_capacity(self):
        no_evidence = self.paper()
        no_evidence.abstract = ''
        no_evidence.doi = '10.9999/newest-without-evidence'
        no_evidence.source_id = 'newest-without-evidence'
        qualified = self.paper()
        earlier = self.now.date() - timedelta(days=1)
        qualified.provenance = [{'date_fields': {'published-online': {'date-parts': [[earlier.year, earlier.month, earlier.day]]}}}]
        self.c['max_papers_per_track'] = 1
        result = run(self.c, now=self.now, http=ReviewModel(), fetchers={'crossref': lambda *args: ([no_evidence, qualified], {'complete': True})})
        self.assertEqual(result['paper_count'], 1)
        audit = json.loads(Path(result['paths']['json']).read_text(encoding="utf-8"))
        self.assertEqual(audit['papers'][0]['doi'], qualified.doi)
        self.assertEqual(audit['meta']['insufficient_evidence'], 1)

    def test_cli_send_rejects_legacy_discovery_snapshot(self):
        payload = {'recipient': self.c['recipient'], 'config_fingerprint': config_fingerprint(self.c), 'aliases': [], 'harvest_until': self.now.date().isoformat()}
        state = State(self.c['state_path'], scope=state_scope(self.c))
        state.prepare('legacy-review', payload)
        state.close()
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps(self.c))
        output, error = (io.StringIO(), io.StringIO())
        with patch('literature_digest.cli.send_smtp', side_effect=AssertionError('Legacy SMTP must not execute')), redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(main(['--config', str(path), 'send', 'legacy-review']), 1)
        self.assertIn('required model-analysis verification', error.getvalue())

    def test_cli_schedule_rejects_unready_model_before_sleep(self):
        self.c['llm']['enabled'] = False
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps(self.c))
        output, error = (io.StringIO(), io.StringIO())
        with patch('literature_digest.cli.time.sleep', side_effect=AssertionError('Unready scheduler must not loop')), redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(main(['--config', str(path), 'schedule']), 1)
        self.assertRegex(error.getvalue(), '(?i)llm|model')
        self.assertFalse(Path(self.c['state_path']).exists())

    def test_validate_reports_missing_model_readiness_without_network(self):
        self.c['llm']['enabled'] = False
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps(self.c))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['--config', str(path), 'validate']), 0)
        result = json.loads(output.getvalue())[0]
        self.assertTrue(result['llm_required'])
        self.assertFalse(result['live_ready'])
        self.assertRegex(result['live_blocker'], '(?i)llm|model')
if __name__ == '__main__':
    unittest.main(verbosity=2)
