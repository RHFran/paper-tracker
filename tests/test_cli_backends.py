"""All model subprocesses are simulated; tests never use an account or network."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from literature_digest.analysis import require_llm, analyze, compose_overview, screen_candidates, validate_analysis, FIELDS
from literature_digest.config import DEFAULTS, validate_config
from literature_digest.http import RetrievalError
from literature_digest.model_backends import cli_request, _execute, ANALYSIS_SCHEMA
from literature_digest.models import Paper
from model_fixture import perspective_fixture

EVIDENCE = 'The model measured weather forecasts using controlled experiments.'
ANCHOR = 'measured weather forecasts using controlled experiments'
FIELDS_RESULT = {key: ([{'text': 'The model measured weather forecasts.', 'evidence': ANCHOR}] if key == 'findings' else []) for key in FIELDS}
FIELDS_RESULT['question'] = [{'text': 'The fixture examines weather forecasts.', 'evidence': ANCHOR}]
FIELDS_RESULT['methods'] = [{'text': 'The fixture uses controlled experiments.', 'evidence': ANCHOR}]
ANALYSIS_RESULT = {'fields': FIELDS_RESULT, 'perspective': perspective_fixture(ANCHOR)}

class CLIBackends(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(DEFAULTS)
        self.config.update(language='en', topics=[{'id':'weather','name':'Weather agents','queries':['weather'],'include_any':['weather']}])
        self.config['llm'].update(enabled=True,backend='codex')
        self.which=patch('literature_digest.model_backends.shutil.which',return_value='/official/codex')
        self.which.start(); self.addCleanup(self.which.stop)

    def test_cli_needs_no_external_api_credentials(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(require_llm(self.config),('codex','/official/codex',''))

    def test_missing_executable_fails_before_model(self):
        with patch('literature_digest.model_backends.shutil.which',return_value=None):
            with self.assertRaisesRegex(ValueError,'not found'): require_llm(self.config)

    def test_codex_safe_argv_and_schema_stdin(self):
        def execute(command,prompt,cwd,timeout):
            self.assertNotIn(EVIDENCE,command)
            self.assertIn(EVIDENCE,prompt)
            self.assertIn('read-only',command)
            self.assertIn('--ephemeral',command)
            self.assertIn('--ignore-user-config',command)
            self.assertNotIn('--ignore-rules',command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',command)
            self.assertIn('shell_tool',command);self.assertIn('apps',command)
            self.assertEqual(command[-1],'-')
            schema=json.loads(Path(command[command.index('--output-schema')+1]).read_text(encoding='utf-8'))
            self.assertEqual(schema,ANALYSIS_SCHEMA)
            Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(ANALYSIS_RESULT),encoding='utf-8')
            return 'raw provider logs ignored'
        with patch('literature_digest.model_backends._execute',side_effect=execute):
            data,model=cli_request(self.config,'Transform source only',{'evidence':EVIDENCE},ANALYSIS_SCHEMA)
        self.assertEqual(data,ANALYSIS_RESULT);self.assertEqual(model,'codex:cli-default')

    def test_claude_subscription_login_not_disabled_and_tools_disabled(self):
        self.config['llm'].update(backend='claude',cli_model='chosen-model')
        def execute(command,*args):
            self.assertNotIn('--bare',command)
            self.assertEqual(command[command.index('--tools')+1],'')
            self.assertIn('mcp__*',command);self.assertIn('--strict-mcp-config',command)
            self.assertIn('--no-session-persistence',command)
            return json.dumps({'subtype':'success','structured_output':ANALYSIS_RESULT})
        with patch('literature_digest.model_backends._execute',side_effect=execute):
            result,model=cli_request(self.config,'s',{},ANALYSIS_SCHEMA)
        self.assertEqual(model,'claude:chosen-model');self.assertEqual(result,ANALYSIS_RESULT)

    def test_claude_malformed_error_and_missing_structured_json_fail(self):
        self.config['llm']['backend']='claude'
        for data in ('bad json',json.dumps({'is_error':True,'result':'secret'}),json.dumps({'result':'not json'})):
            with self.subTest(data=data),patch('literature_digest.model_backends._execute',return_value=data):
                with self.assertRaises(RetrievalError):cli_request(self.config,'s',{},ANALYSIS_SCHEMA)

    def test_invalid_evidence_is_not_successful_cli_analysis(self):
        p=Paper('Weather model','s','s','https://example.org',abstract=EVIDENCE)
        bad=copy.deepcopy(ANALYSIS_RESULT);bad['fields']['findings'][0]['evidence']='invented text that is not in evidence'
        with patch('literature_digest.model_backends.cli_request',return_value=(bad,'codex:test')):
            self.assertEqual(analyze(p,self.config,None)['mode'],'discovery_only')

    def test_timeout_kills_and_reaps_process(self):
        process=unittest.mock.Mock(pid=1234)
        process.communicate.side_effect=[subprocess.TimeoutExpired('codex',1),('','')]
        with patch('literature_digest.model_backends.subprocess.Popen',return_value=process) as popen,patch('literature_digest.model_backends.os.name','posix'),patch('literature_digest.model_backends.os.killpg',create=True) as kill,patch('literature_digest.model_backends.signal.SIGKILL',9,create=True):
            with self.assertRaisesRegex(RetrievalError,'timed out'):_execute(['codex'],'source','/tmp',1)
            self.assertFalse(popen.call_args.kwargs['shell']);self.assertTrue(kill.called)
            self.assertEqual(process.communicate.call_count,2)

    def test_windows_timeout_kills_process_without_posix_calls(self):
        process=unittest.mock.Mock(pid=1234)
        process.communicate.side_effect=[subprocess.TimeoutExpired('codex',1),('','')]
        with patch('literature_digest.model_backends.subprocess.Popen',return_value=process),patch('literature_digest.model_backends.os.name','nt'):
            with self.assertRaisesRegex(RetrievalError,'timed out'):_execute(['codex'],'source','C:/tmp',1)
        process.kill.assert_called_once()

    def test_error_logs_redacted_but_category_useful(self):
        for log,expected in [('Error: read-only file system secret_token','runtime storage'),('unexpected argument secret_token','required safe'),('HTTP 401 secret_token','authentication'),('provider down secret_token','logs withheld')]:
            process=unittest.mock.Mock(returncode=1)
            process.communicate.return_value=('secret stdout',log)
            with patch('literature_digest.model_backends.subprocess.Popen',return_value=process):
                with self.assertRaisesRegex(RetrievalError,expected) as error:_execute(['codex'],'source','/tmp',1)
                self.assertNotIn('secret',str(error.exception))

    def test_backend_config_validation(self):
        for field,value in [('backend','shell'),('cli_timeout_seconds',0),('max_screen_candidates',201),('cli_model','bad\nmodel'),('screen_candidates','yes'),('plan_queries',1)]:
            c=copy.deepcopy(self.config);c['llm'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_config(c)

    def paper(self,key='one'):
        return Paper('Weather agent',key,'arxiv','https://arxiv.org',abstract=EVIDENCE,tracks=['weather'])

    def decisions(self,papers):
        return {'decisions':[{'key':p.key,'include':True,'topic_ids':p.tracks,'reason':'Direct weather model research.','evidence':ANCHOR} for p in papers]}

    def test_screen_requires_every_identity_once_and_matching_anchors(self):
        papers=[self.paper(),self.paper('two')]
        variants=[{'decisions':[]},self.decisions([papers[0],papers[0]]),self.decisions(papers)]
        variants[2]['decisions'][0]['evidence']='invented evidence not in the source'
        for data in variants:
            with patch('literature_digest.analysis._model_request',return_value=(data,'fake')):
                with self.assertRaises(ValueError):screen_candidates(papers,self.config,None)

    def test_screen_preserves_order_and_audits_cap(self):
        papers=[self.paper(),self.paper('two')];self.config['llm']['max_screen_candidates']=1
        with patch('literature_digest.analysis._model_request',return_value=(self.decisions(papers[:1]),'fake')):
            selected,audit=screen_candidates(papers,self.config,None)
        self.assertEqual(selected,papers[:1]);self.assertEqual(len(audit),2)
        self.assertIn('Deferred',audit[1]['reason'])

if __name__=='__main__': unittest.main()
