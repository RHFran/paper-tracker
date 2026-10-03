"""Offline agent lifecycle tests. Agent/source doubles are not live CLI runs."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from unittest.mock import patch

from literature_digest.agent_jobs import (create_job, tool, recover_job, _load, _save)
from literature_digest.agent_runner import command, run_agent, AgentInterrupted
from literature_digest.cli import main, _run_one
from literature_digest.config import DEFAULTS, load_configs, validate_config
from literature_digest.connector_delivery import begin_send, confirm_sent
from literature_digest.models import Paper
from literature_digest.pipeline import config_fingerprint
from literature_digest.state import State, state_scope


class AgentJobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agent job test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = copy.deepcopy(DEFAULTS)
        self.config.update(workflow={'mode':'agent'}, language='en', timezone='UTC',
                           state_path=str(self.root/'state'/'ledger.db'), output_dir=str(self.root/'out'),
                           sources=['crossref'], topics=[{'id':'earth','name':'Earth agents','queries':['earth agents']}])
        self.config['agent']['backend']='host'
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        self.evidence='This synthetic earth research evidence describes a tested agent method for climate forecasts.'
        self.paper = Paper(title='Synthetic earth agents', source='crossref', source_id='10.9999/offline',
                           doi='10.9999/offline', url='https://doi.org/10.9999/offline', abstract=self.evidence,
                           provenance=[{'date_fields':{'published-online':{'date-parts':[[2026,10,2]]}}}])

    def source(self, job):
        report={'source':'crossref','complete':True,'queries':[{'query':'earth agents'}]}
        with patch('literature_digest.agent_sources.search', return_value=([copy.deepcopy(self.paper)],report)):
            result=tool(self.config,job['job_id'],'search',source='crossref',topic_id='earth',query='earth agents')
        tool(self.config,job['job_id'],'ingest',input_path=result['snapshot_path'])
        return result

    def data(self):
        claim={'text':'The synthetic source describes a tested agent method.','evidence':self.evidence[:80]}
        return {'decisions':[{'key':self.paper.key,'include':True,'topic_ids':['earth'],'reason':'Direct relevance to Earth agents.','evidence':self.evidence[:80]}],
                'analyses':[{'key':self.paper.key,'fields':{'highlights':[],'question':[],'methods':[],'findings':[claim]}}],
                'overview':{'paragraphs':[{'sentences':[{'text':claim['text'],'citations':[{'ref':1,'evidence':claim['evidence']}]}]}]},
                'coverage_notes':'One synthetic offline source query; not an exhaustive bibliography.'}

    def submission(self, data=None):
        path=self.root/'result.json';path.write_text(json.dumps(data if data is not None else self.data()),encoding='utf-8');return str(path)

    def finish(self, delivery='dry_run'):
        job=create_job(self.config,self.now,delivery);self.source(job)
        result=tool(self.config,job['job_id'],'finalize',input_path=self.submission())
        return job,result

    def test_host_export_no_research_model_or_mail_and_launcher_from_other_cwd(self):
        with patch('literature_digest.pipeline.run') as fixed, patch('literature_digest.agent_sources.search') as search:
            result=run_agent(self.config,now=self.now)
        self.assertEqual(result['status'],'awaiting_agent');fixed.assert_not_called();search.assert_not_called()
        task=Path(result['task_path']).read_text();self.assertIn('no research pipeline has run',task)
        output=subprocess.run(result['tool_argv']+['status'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(output.returncode,0,output.stderr)
        self.assertEqual(json.loads(output.stdout)['status'],'awaiting_agent')
        self.assertIn("str(Path(__file__).with_name('config.json'))",Path(result['workspace'],'tool.py').read_text())

    def test_source_ingest_validate_finalize_library_and_idempotence(self):
        job=create_job(self.config,self.now);fetched=self.source(job)
        self.assertTrue(tool(self.config,job['job_id'],'ingest',input_path=fetched['snapshot_path'])['already_ingested'])
        self.assertEqual(tool(self.config,job['job_id'],'validate',input_path=self.submission())['status'],'validated')
        result=tool(self.config,job['job_id'],'finalize',input_path=self.submission())
        self.assertEqual(result['workflow'],'agent_led');self.assertEqual(result['paper_count'],1)
        self.assertEqual(len(tool(self.config,job['job_id'],'library')['papers']),1)
        self.assertTrue(tool(self.config,job['job_id'],'finalize',input_path=self.submission())['reused_completed_job'])
        self.assertIsNone(self.state().checkpoint())

    def state(self):
        state=State(self.config['state_path'],scope=state_scope(self.config));self.addCleanup(state.close);return state

    def test_fake_or_changed_evidence_rejected(self):
        job=create_job(self.config,self.now)
        bogus=self.root/'fake.json';bogus.write_text(json.dumps({'papers':[self.paper.export(True)]}))
        with self.assertRaisesRegex(ValueError,'unmodified'):tool(self.config,job['job_id'],'ingest',input_path=str(bogus))
        fetched=self.source(job);Path(fetched['snapshot_path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'unmodified'):tool(self.config,job['job_id'],'ingest',input_path=fetched['snapshot_path'])

    def test_anchor_topic_window_and_missing_decisions_fail_closed(self):
        job=create_job(self.config,self.now);self.source(job)
        for mutation in ('anchor','topic','decisions','overview'):
            data=self.data()
            if mutation=='anchor':data['analyses'][0]['fields']['findings'][0]['evidence']='Fabricated source quotation nowhere present.'
            if mutation=='topic':data['decisions'][0]['topic_ids']=['unknown']
            if mutation=='decisions':data['decisions']=[]
            if mutation=='overview':data['overview']['paragraphs'][0]['sentences'][0]['citations'][0]['ref']=9
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):tool(self.config,job['job_id'],'finalize',input_path=self.submission(data))
        self.assertEqual(self.state().recent(),[])

    def test_source_operation_required_and_coverage_is_bounded(self):
        job=create_job(self.config,self.now)
        data={'decisions':[],'analyses':[],'overview':{'paragraphs':[]},'coverage_notes':'No retrieval performed; this must be rejected.'}
        with self.assertRaisesRegex(ValueError,'ingested'):tool(self.config,job['job_id'],'finalize',input_path=self.submission(data))
        self.source(job);result=tool(self.config,job['job_id'],'finalize',input_path=self.submission())
        audit=json.loads(Path(result['paths']['json']).read_text())
        self.assertTrue(audit['meta']['partial_coverage']);self.assertEqual(audit['meta']['workflow'],'agent_led')

    def test_dry_run_promotes_without_research_and_prepared_never_replaced(self):
        job,dry=self.finish()
        with patch('literature_digest.agent_sources.search') as search:
            result=run_agent(self.config,now=self.now,prepare_connector=True)
        search.assert_not_called();self.assertEqual(result['status'],'prepared');self.assertEqual(result['digest_id'],dry['digest_id'])
        with self.assertRaisesRegex(ValueError,'different delivery'):run_agent(self.config,now=self.now)
        self.assertEqual(len(self.state().recent()),1)

    def test_receipt_status_not_stale_and_no_resend(self):
        job,result=self.finish('connector')
        begin_send(self.config,job['job_id'],now=self.now)
        receipt={'digest_id':job['job_id'],'envelope_sha256':result['envelope_sha256'],'provider':'offline-test',
                 'status':'pending','sender':'sender@example.org','recipient':self.config['recipient']}
        confirm_sent(self.config,job['job_id'],receipt)
        again=run_agent(self.config,now=self.now,prepare_connector=True)
        self.assertEqual(again['status'],'uncertain')
        with self.assertRaises(ValueError):begin_send(self.config,job['job_id'],now=self.now)
        self.assertIsNone(self.state().checkpoint())

    def test_partial_finalize_recovers_exact_outbox(self):
        job=create_job(self.config,self.now,'connector');self.source(job)
        with patch('literature_digest.agent_jobs._save_library',side_effect=RuntimeError('simulated interruption')):
            with self.assertRaises(RuntimeError):tool(self.config,job['job_id'],'finalize',input_path=self.submission())
        existing=self.state().get(job['job_id']);self.assertEqual(existing['status'],'prepared')
        result=tool(self.config,job['job_id'],'finalize',input_path=self.submission())
        self.assertEqual(result['status'],'prepared');self.assertEqual(result['envelope_sha256'],existing['payload']['envelope_sha256'])

    def test_running_job_needs_explicit_operator_recovery(self):
        job=create_job(self.config,self.now);state=self.state()
        with state.lock():
            record=_load(state,self.config,job['job_id']);record['status']='running';_save(state,record)
        with self.assertRaises(ValueError):recover_job(self.config,job['job_id'])
        self.assertEqual(recover_job(self.config,job['job_id'],True)['status'],'awaiting_agent')

    def test_contract_mutation_and_config_drift_rejected(self):
        job=create_job(self.config,self.now)
        changed=copy.deepcopy(self.config);changed['language']='de'
        with self.assertRaisesRegex(ValueError,'configuration changed'):tool(changed,job['job_id'],'status')
        Path(job['contract_path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrity'):tool(self.config,job['job_id'],'status')

    def test_full_agent_command_keeps_tools_and_explicit_model_effort(self):
        job=create_job(self.config,self.now)
        for backend,effort in [('codex','xhigh'),('claude','high')]:
            self.config['agent'].update(backend=backend,model='account-available-model',reasoning_effort=effort)
            with patch('literature_digest.agent_jobs.shutil.which',return_value=sys.executable):argv=command(self.config,job)
            self.assertIn('--model',argv);self.assertIn('account-available-model',argv)
            for disabled in ('--tools','--ignore-user-config','--disable','--dangerously-skip-permissions','--dangerously-bypass-approvals-and-sandbox','--fallback-model'):
                self.assertNotIn(disabled,argv)
            if backend=='codex':self.assertIn('model_reasoning_effort="xhigh"',argv);self.assertIn('workspace-write',argv)
            else:self.assertIn('--effort',argv);self.assertIn('high',argv)

    def test_cli_success_without_tool_commit_is_blocked_and_tick_never_retries(self):
        self.config['agent']['backend']='codex'
        with patch('literature_digest.agent_jobs.shutil.which',return_value=sys.executable):
            first=run_agent(self.config,now=self.now,executor=lambda *args:None)
        self.assertEqual(first['status'],'blocked')
        with patch('literature_digest.agent_runner.execute') as execute:
            self.assertEqual(_run_one(self.config,'tick',now=self.now)['status'],'blocked')
        execute.assert_not_called()

    def test_agent_stub_drives_tools_and_never_fixed_pipeline(self):
        self.config['agent']['backend']='codex'
        calls=[]
        def agent(argv,prompt,config,job):
            calls.append(argv);self.source(job);tool(config,job['job_id'],'finalize',input_path=self.submission())
        with patch('literature_digest.agent_jobs.shutil.which',return_value=sys.executable),patch('literature_digest.pipeline.run') as fixed:
            result=run_agent(self.config,now=self.now,executor=agent)
        self.assertEqual(result['status'],'dry_run');self.assertEqual(len(calls),1);fixed.assert_not_called()

    def test_init_new_agent_existing_configs_keep_standalone(self):
        path=self.root/'config.json'
        args=['--config',str(path),'init','--yes','--recipient','r@example.org','--topic','earth agents','--agent-backend','host']
        with redirect_stdout(io.StringIO()):self.assertEqual(main(args),0)
        self.assertEqual(load_configs(path)[0]['workflow']['mode'],'agent')
        path.write_text('{}');self.assertEqual(load_configs(path)[0]['workflow']['mode'],'standalone')
        legacy=copy.deepcopy(DEFAULTS);old=copy.deepcopy(legacy);old.pop('workflow');old.pop('agent')
        self.assertEqual(config_fingerprint(legacy),config_fingerprint(old))

    def test_timeout_never_automatically_retries_uncertain_child_processes(self):
        self.config['agent']['backend']='codex'
        def fail(*args):raise AgentInterrupted('simulated descendant uncertainty')
        with patch('literature_digest.agent_jobs.shutil.which',return_value=sys.executable):
            result=run_agent(self.config,now=self.now,executor=fail)
        self.assertEqual(result['status'],'interrupted')
        with patch('literature_digest.agent_runner.execute') as execute:
            self.assertEqual(run_agent(self.config,now=self.now,retry=True)['status'],'interrupted')
        execute.assert_not_called()
        self.assertEqual(recover_job(self.config,result['job_id'],True)['status'],'awaiting_agent')

    def test_backend_specific_effort_validation(self):
        self.config['agent'].update(backend='claude',reasoning_effort='ultra')
        with self.assertRaisesRegex(ValueError,'reasoning_effort'):validate_config(self.config)


if __name__=='__main__':unittest.main()
