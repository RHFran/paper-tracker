"""Offline lifecycle, evidence integrity and transaction tests for supersession."""
import copy
from contextlib import redirect_stdout, redirect_stderr
from datetime import timedelta
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_agent_jobs as fixtures
from literature_digest.agent_jobs import create_job, _load, _save, tool
from literature_digest.agent_supersede import supersede_job, _commit_successor
from literature_digest.cli import main
from literature_digest.config import load_configs
from literature_digest.connector_delivery import begin_send
from literature_digest.outlook import empty_outlook


class AgentSupersede(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.AgentJobs()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.config = self.h.config
        self.reason = 'Correct a contradictory coverage disclosure before delivery'

    def prepare(self):
        return self.h.finish('connector')

    def snapshot(self):
        return {str(path): path.read_bytes() for path in self.h.root.rglob('*')
                if path.is_file() and (path.parent.name != 'state') and not path.name.endswith(('.db', '-wal', '-shm', '.lock'))}

    def assert_original_bytes(self, original):
        for path, contents in original.items():
            self.assertEqual(Path(path).read_bytes(), contents, path)

    def rows(self, state, table):
        return state.db.execute('SELECT * FROM ' + table + ' ORDER BY 1,2').fetchall()

    def test_replacement_preserves_bundle_payload_receipts_dedup_and_window(self):
        job, prepared = self.prepare()
        state = self.h.state()
        # Unrelated historical data must be entirely unaffected.
        state.prepare('f' * 32, {'aliases':['doi:10.9999/history'], 'harvest_until':'2026-10-01'})
        state.mark_sent('f' * 32, {'provider':'offline-test', 'id':'history-receipt'})
        old_payload = state.db.execute('SELECT payload FROM deliveries_v2 WHERE id=?', (job['job_id'],)).fetchone()[0]
        before = self.snapshot()
        receipts = self.rows(state, 'delivery_receipts_v1')
        sent = self.rows(state, 'sent_papers_v2')
        metadata = self.rows(state, 'metadata_v2')
        original_job = _load(state, self.config, job['job_id'])
        replacement = supersede_job(self.config, job['job_id'], self.reason)
        self.assertNotEqual(replacement['job_id'], job['job_id'])
        self.assertEqual(replacement['status'], 'awaiting_agent')
        self.assertEqual(replacement['supersedes'], job['job_id'])
        current = _load(state, self.config, replacement['job_id'])
        for key in ('publication_start','publication_end','local_date','recipient','profile_id','delivery'):
            self.assertEqual(current[key], original_job[key])
        self.assertNotIn('revision_of', current)
        self.assertNotIn('submission_sha256', current)
        self.assertEqual(state.get(job['job_id'])['status'], 'superseded')
        self.assertEqual(state.db.execute('SELECT payload FROM deliveries_v2 WHERE id=?', (job['job_id'],)).fetchone()[0], old_payload)
        self.assertEqual(self.rows(state, 'delivery_receipts_v1'), receipts)
        self.assertEqual(self.rows(state, 'sent_papers_v2'), sent)
        self.assertEqual(self.rows(state, 'metadata_v2'), metadata)
        self.assertIsNone(state.get(replacement['job_id']))
        self.assert_original_bytes(before)
        self.assertEqual(tool(self.config, replacement['job_id'], 'status')['papers'], tool(self.config, job['job_id'], 'status')['papers'])
        self.assertEqual(tool(self.config, replacement['job_id'], 'status')['figures'], [])
        result = tool(self.config, replacement['job_id'], 'finalize', input_path=self.h.submission())
        self.assertEqual(result['status'], 'prepared')
        original_audit = json.loads(Path(prepared['paths']['audit']).read_text(encoding='utf-8'))
        replacement_audit = json.loads(Path(result['paths']['audit']).read_text(encoding='utf-8'))
        self.assertEqual(replacement_audit['meta']['window_end'], original_audit['meta']['window_end'])
        self.assertNotEqual(result['envelope_sha256'], prepared['envelope_sha256'])
        self.assertNotIn('Revised edition', state.get(replacement['job_id'])['payload']['subject'])
        self.assertEqual(state.get(replacement['job_id'])['payload']['supersedes'], job['job_id'])
        self.assert_original_bytes(before)
        with self.assertRaises(ValueError):
            begin_send(self.config, job['job_id'], now=self.h.now)
        self.assertEqual(begin_send(self.config, replacement['job_id'], now=self.h.now)['status'], 'sending')
        self.assertIsNotNone(state.send_claim(replacement['job_id']))

    def test_repeat_is_idempotent_before_and_after_finalization_and_export_follows(self):
        job, _ = self.prepare()
        successor = supersede_job(self.config, job['job_id'], self.reason)
        state = self.h.state()
        rows = self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')
        again = supersede_job(self.config, job['job_id'], self.reason)
        self.assertTrue(again['reused_supersession'])
        self.assertEqual(again['job_id'], successor['job_id'])
        self.assertEqual(rows, (self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')))
        exported = create_job(self.config, self.h.now, 'connector')
        self.assertEqual(exported['job_id'], successor['job_id'])
        self.assertEqual(exported['status'], 'awaiting_agent')
        with self.assertRaisesRegex(ValueError, 'different reason'):
            supersede_job(self.config, job['job_id'], 'A different correction request')
        tool(self.config, successor['job_id'], 'finalize', input_path=self.h.submission())
        self.assertEqual(supersede_job(self.config, job['job_id'], self.reason)['job_id'], successor['job_id'])
        self.assertEqual(create_job(self.config, self.h.now, 'connector')['job_id'], successor['job_id'])
        with self.assertRaises(ValueError):
            tool(self.config, job['job_id'], 'finalize', input_path=self.h.submission())

    def test_claimed_uncertain_sent_and_nonprepared_are_rejected(self):
        job, _ = self.prepare()
        state = self.h.state()
        for status in ('sending', 'uncertain', 'sent', 'failed'):
            state.status(job['job_id'], status)
            before = self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')
            with self.subTest(status=status), self.assertRaises(ValueError):
                supersede_job(self.config, job['job_id'], self.reason)
            self.assertEqual(before, (self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')))

    def test_durable_claim_blocks_prepared_status_reuse_and_claim_is_atomic(self):
        job, _ = self.prepare()
        state = self.h.state()
        begin_send(self.config, job['job_id'], now=self.h.now)
        claim = state.send_claim(job['job_id'])
        state.status(job['job_id'], 'prepared')  # Simulate an erroneous external reset.
        with self.assertRaisesRegex(ValueError, 'claim'):
            supersede_job(self.config, job['job_id'], self.reason)
        with self.assertRaisesRegex(ValueError, 'claim'):
            begin_send(self.config, job['job_id'], now=self.h.now)
        self.assertEqual(state.send_claim(job['job_id']), claim)
        self.assertEqual(state.get(job['job_id'])['status'], 'prepared')

    def test_claim_write_failure_rolls_back_sending_status(self):
        job, _ = self.prepare()
        state = self.h.state()
        state.db.execute("CREATE TRIGGER fail_claim BEFORE INSERT ON delivery_claims_v1 BEGIN SELECT RAISE(ABORT,'test claim failure'); END")
        state.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            begin_send(self.config, job['job_id'], now=self.h.now)
        self.assertEqual(state.get(job['job_id'])['status'], 'prepared')
        self.assertIsNone(state.send_claim(job['job_id']))

    def test_receipt_even_empty_blocks_prepared_source(self):
        job, _ = self.prepare()
        state = self.h.state()
        state.record_receipt(job['job_id'], {})
        before = self.rows(state, 'delivery_receipts_v1')
        with self.assertRaisesRegex(ValueError, 'receipt'):
            supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(self.rows(state, 'delivery_receipts_v1'), before)

    def test_wrong_audience_profile_config_or_storage_rejected(self):
        job, _ = self.prepare()
        for key, value in (('recipient','other@example.org'), ('profile_id','other'), ('language','de'),
                           ('output_dir',str(self.h.root/'different')), ('http_retries',8),
                           ('schedule', {'time':'01:00'})):
            changed = copy.deepcopy(self.config)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                supersede_job(changed, job['job_id'], self.reason)
        changed = copy.deepcopy(self.config)
        changed['state_path'] = str(self.h.root/'other-ledger.db')
        with self.assertRaises(ValueError):
            supersede_job(changed, job['job_id'], self.reason)

    def test_incomplete_or_dry_run_or_smtp_source_rejected(self):
        for delivery in ('dry_run','smtp','connector'):
            with self.subTest(delivery=delivery):
                h = fixtures.AgentJobs(); h.setUp()
                try:
                    if delivery == 'connector':
                        job = create_job(h.config, h.now, delivery)
                    else:
                        job, _ = h.finish(delivery)
                    with self.assertRaises(ValueError):
                        supersede_job(h.config, job['job_id'], self.reason)
                finally:
                    h.doCleanups()

    def test_other_open_delivery_rejected(self):
        job, _ = self.prepare()
        state = self.h.state()
        state.prepare('e' * 32, {'aliases':[], 'harvest_until':'2026-10-03'})
        with self.assertRaisesRegex(ValueError, 'Other open'):
            supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(state.get(job['job_id'])['status'], 'prepared')

    def test_artifact_contract_submission_source_and_candidate_tampering_rejected(self):
        for target in ('artifact', 'contract', 'submission', 'source', 'candidate', 'event'):
            with self.subTest(target=target):
                h = fixtures.AgentJobs(); h.setUp()
                try:
                    job, result = h.finish('connector')
                    state = h.state()
                    if target == 'artifact':
                        Path(result['paths']['html']).write_text('tampered')
                    elif target == 'contract':
                        Path(job['contract_path']).write_text('{}')
                    elif target == 'submission':
                        Path(job['workspace'], 'submission.json').write_text('{}')
                    elif target == 'source':
                        source = state.db.execute('SELECT path FROM agent_sources_v1').fetchone()[0]
                        Path(source).write_text('{}')
                    elif target == 'candidate':
                        state.db.execute("UPDATE agent_candidates_v1 SET data='{}'"); state.db.commit()
                    else:
                        record = _load(state, h.config, job['job_id'])
                        record['events'][0]['report']['complete'] = False
                        _save(state, record)
                    with self.assertRaisesRegex(ValueError, 'integrity'):
                        supersede_job(h.config, job['job_id'], self.reason)
                    self.assertEqual(state.get(job['job_id'])['status'], 'prepared')
                finally:
                    h.doCleanups()

    def test_transaction_failure_after_original_transition_rolls_everything_back(self):
        job, _ = self.prepare()
        state = self.h.state()
        tables = ('agent_jobs_v1','agent_sources_v1','agent_candidates_v1','deliveries_v2',
                  'delivery_receipts_v1','delivery_claims_v1','sent_papers_v2','metadata_v2')
        before = {table:self.rows(state, table) for table in tables}
        files = self.snapshot()
        parent = Path(job['workspace']).parent
        directories = set(parent.iterdir())
        def fail(*args):
            _commit_successor(*args)
            raise RuntimeError('simulated failure after predecessor transition')
        with patch('literature_digest.agent_supersede._commit_successor', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'predecessor'):
                supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual({table:self.rows(state, table) for table in tables}, before)
        self.assertEqual(set(parent.iterdir()), directories)
        self.assert_original_bytes(files)
        self.assertEqual(supersede_job(self.config, job['job_id'], self.reason)['status'], 'awaiting_agent')

    def test_publish_failure_rolls_back_ledger_and_no_partial_workspace(self):
        job, _ = self.prepare()
        state = self.h.state()
        directories = set(Path(job['workspace']).parent.iterdir())
        with patch('literature_digest.agent_supersede.Path.rename', side_effect=OSError('simulated publish failure')):
            with self.assertRaises(OSError):
                supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(state.get(job['job_id'])['status'], 'prepared')
        self.assertEqual(len(self.rows(state, 'agent_jobs_v1')), 1)
        self.assertEqual(set(Path(job['workspace']).parent.iterdir()), directories)

    def test_commit_failure_after_workspace_publish_rolls_back_and_cleans_up(self):
        job, _ = self.prepare()
        state = self.h.state()
        before = self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')
        directories = set(Path(job['workspace']).parent.iterdir())
        class FailingCommit:
            def __init__(self, db):
                self.db = db
            def __getattr__(self, name):
                return getattr(self.db, name)
            def commit(self):
                raise sqlite3.OperationalError('simulated commit failure')
        def fail_commit(active, *args):
            _commit_successor(active, *args)
            active.db = FailingCommit(active.db)
        with patch('literature_digest.agent_supersede._commit_successor', side_effect=fail_commit):
            with self.assertRaises(sqlite3.OperationalError):
                supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(before, (self.rows(state, 'agent_jobs_v1'), self.rows(state, 'deliveries_v2')))
        self.assertEqual(set(Path(job['workspace']).parent.iterdir()), directories)

    def test_successor_can_be_superseded_once_and_regular_export_follows_chain(self):
        job, _ = self.prepare()
        first = supersede_job(self.config, job['job_id'], self.reason)
        tool(self.config, first['job_id'], 'finalize', input_path=self.h.submission())
        second = supersede_job(self.config, first['job_id'], 'Another reviewed correction before any claim')
        self.assertNotIn(second['job_id'], (job['job_id'], first['job_id']))
        self.assertEqual(create_job(self.config, self.h.now, 'connector')['job_id'], second['job_id'])
        self.assertEqual(supersede_job(self.config, job['job_id'], self.reason)['job_id'], first['job_id'])
        state = self.h.state()
        original = _load(state, self.config, job['job_id'])
        self.assertEqual(_load(state, self.config, second['job_id'])['research_window_end'], original['created_at'])

    def test_registered_figures_are_preserved_but_not_copied(self):
        import test_original_figures as figure_fixtures
        self.config['images'] = {'mode':'embed', 'max_per_paper':2}
        self.h.paper.arxiv_id = '2608.10277'
        self.h.paper.doi = ''
        self.h.paper.source = 'arxiv'
        self.h.paper.source_id = '2608.10277'
        job = create_job(self.config, self.h.now, 'connector')
        self.h.source(job)
        manifest = Path(job['workspace'])/'figure.json'
        manifest.write_text(json.dumps(figure_fixtures.manifest()), encoding='utf-8')
        with patch('literature_digest.figures.fetch_public', side_effect=figure_fixtures.fetcher):
            tool(self.config, job['job_id'], 'figure', input_path=manifest)
        tool(self.config, job['job_id'], 'finalize', input_path=self.h.submission())
        before = self.snapshot()
        state = self.h.state()
        figures = self.rows(state, 'agent_figures_v1')
        successor = supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(self.rows(state, 'agent_figures_v1'), figures)
        self.assertEqual(tool(self.config, successor['job_id'], 'status')['figures'], [])
        self.assertFalse((Path(successor['workspace'])/'figure-evidence').exists())
        self.assert_original_bytes(before)
        next((Path(job['workspace'])/'figure-evidence').iterdir()).write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            supersede_job(self.config, job['job_id'], self.reason)

    def test_stale_replacement_keeps_original_day_and_cannot_be_claimed(self):
        job, _ = self.prepare()
        successor = supersede_job(self.config, job['job_id'], self.reason)
        tool(self.config, successor['job_id'], 'finalize', input_path=self.h.submission())
        with self.assertRaisesRegex(ValueError, 'stale'):
            begin_send(self.config, successor['job_id'], now=self.h.now + timedelta(days=1))
        self.assertIsNone(self.h.state().send_claim(successor['job_id']))

    def test_cli_supersede_works_without_model_or_send_and_requires_reason(self):
        path = self.h.root/'config.json'
        path.write_text(json.dumps(self.config), encoding='utf-8')
        # CLI-created jobs use resolved paths. Windows temporary paths may use
        # short aliases, so prepare with the same canonical config as the CLI.
        self.config = self.h.config = load_configs(str(path))[0]
        job, _ = self.prepare()
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors), patch('literature_digest.agent_sources.search') as search, patch('literature_digest.mail.send_smtp') as send:
            code = main(['--config',str(path),'agent-supersede',job['job_id'],'--reason',self.reason])
        self.assertEqual(code, 0, output.getvalue() + errors.getvalue())
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed['status'], 'awaiting_agent')
        self.assertNotEqual(parsed['job_id'], job['job_id'])
        search.assert_not_called(); send.assert_not_called()

    def test_empty_candidate_source_can_be_reused(self):
        job = create_job(self.config, self.h.now, 'connector')
        with patch('literature_digest.agent_sources.search', return_value=([], {'source':'crossref','complete':True})):
            source = tool(self.config, job['job_id'], 'search', source='crossref', topic_id='earth', query='earth agents')
        tool(self.config, job['job_id'], 'ingest', input_path=source['snapshot_path'])
        data = {'decisions':[], 'analyses':[], 'overview':{'paragraphs':[]}, 'outlook':empty_outlook(),
                'coverage_notes':'Synthetic empty source result; this is non-exhaustive coverage.'}
        tool(self.config, job['job_id'], 'finalize', input_path=self.h.submission(data))
        successor = supersede_job(self.config, job['job_id'], self.reason)
        self.assertEqual(tool(self.config, successor['job_id'], 'validate', input_path=self.h.submission(data))['paper_count'], 0)


if __name__ == '__main__':
    unittest.main()
