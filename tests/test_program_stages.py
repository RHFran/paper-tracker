import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from literature_digest.config import DEFAULTS
from literature_digest.models import Paper
from literature_digest.pipeline import run
from literature_digest.http import RetrievalError
from literature_digest.relevance import screening_tracks
from literature_digest.state import State,state_scope
from literature_digest.library import list_papers
from test_required_llm import ENV,EVIDENCE,ANCHOR,ReviewModel

class StageModel(ReviewModel):
    def json(self,url,**kwargs):
        content=json.loads(kwargs['payload']['messages'][1]['content'])
        if 'untrusted_research_topics' in content:
            data={'topics':[{'id':t['id'],'queries':['electrochemical storage']} for t in content['untrusted_research_topics']]}
        elif 'untrusted_candidates' in content:
            data={'decisions':[{'key':p['key'],'include':True,'topic_ids':p['topic_ids'],'reason':'Battery storage research.','evidence':ANCHOR} for p in content['untrusted_candidates']]}
        else:return super().json(url,**kwargs)
        return {'choices':[{'message':{'content':json.dumps(data)}}]}

class ProgramStages(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=copy.deepcopy(DEFAULTS)
        self.c.update(language='en',timezone='UTC',sources=['crossref'],state_path=str(Path(self.tmp.name)/'state.db'),output_dir=str(Path(self.tmp.name)/'out'),topics=[{'id':'battery','name':'Battery energy storage','queries':['battery energy storage'],'include_any':[],'include_all':[],'exclude_any':[]}])
        self.c['llm'].update(enabled=True,plan_queries=True,screen_candidates=True)
        self.now=datetime(2026,10,5,tzinfo=timezone.utc)
        self.env=patch.dict('os.environ',ENV,clear=True);self.env.start();self.addCleanup(self.env.stop)
    def fetch(self):
        def fetch(http,c,*args):
            self.assertEqual(c['topics'][0]['queries'],['electrochemical storage'])
            p=Paper('Electrochemical storage','one','crossref','https://example.org',abstract=EVIDENCE,provenance=[{'date_fields':{'published-online':{'date-parts':[[2026,10,5]]}}}])
            return [p],{'complete':True}
        return {'crossref':fetch}
    def state(self):
        s=State(self.c['state_path'],scope=state_scope(self.c));self.addCleanup(s.close);return s
    def test_program_plans_retrieves_screens_analyzes_and_saves_library(self):
        original=copy.deepcopy(self.c)
        result=run(self.c,now=self.now,http=StageModel(),fetchers=self.fetch())
        self.assertEqual(result['paper_count'],1);self.assertEqual(self.c,original)
        audit=json.loads(Path(result['paths']['json']).read_text())
        self.assertEqual(audit['meta']['query_plan'][0]['queries'],['electrochemical storage'])
        self.assertTrue(audit['meta']['model_screening'][0]['include'])
        s=self.state();self.assertEqual(len(list_papers(s)),1);self.assertEqual(s.recent(),[])
    def test_library_audit_survives_same_day_preview_overwrite(self):
        first=run(self.c,now=self.now,http=StageModel(),fetchers=self.fetch())
        saved=Path(first['paths']['library_audit']);original=saved.read_bytes()
        self.c['language']='en-US'
        second=run(self.c,now=self.now,http=StageModel(),fetchers=self.fetch())
        self.assertNotEqual(first['paths']['library_audit'],second['paths']['library_audit'])
        self.assertEqual(saved.read_bytes(),original)
        self.assertEqual(list_papers(self.state())[0]['audit_path'],second['paths']['library_audit'])

    def test_bounded_coverage_is_visible_in_report(self):
        original=self.fetch()['crossref']
        def partial(*args):
            papers,report=original(*args);return papers,{'complete':False,'truncated':True}
        self.c['retrieval_policy']='bounded'
        result=run(self.c,now=self.now,http=StageModel(),fetchers={'crossref':partial})
        self.assertIn('not an exhaustive',Path(result['paths']['txt']).read_text())

    def test_explicit_exclusions_remain_binding_before_screen(self):
        p=Paper('Battery excluded system','id','s','https://example.org',abstract=EVIDENCE)
        self.c['topics'][0]['exclude_any']=['excluded']
        self.assertEqual(screening_tracks(p,self.c['topics']),[])
    def test_malformed_provider_envelopes_pause_each_paid_stage(self):
        for plan in (True,False):
            self.c['llm']['plan_queries']=plan
            with patch('literature_digest.analysis._model_request',side_effect=IndexError('bad provider')):
                with self.assertRaises(RuntimeError):
                    run(self.c,now=self.now,http=StageModel(),fetchers={'crossref':lambda *a:([Paper('Battery','id','s','https://example.org',abstract=EVIDENCE,provenance=[{'date_fields':{'published-online':{'date-parts':[[2026,10,5]]}}}])],{'complete':True})})
            self.assertIsNotNone(self.state().model_failure_pause())
            self.assertEqual(self.state().recent(),[])
    def test_retrieval_failure_after_planning_pauses_automatic_paid_retry(self):
        def fail(*a):raise RetrievalError('source unavailable')
        result=run(self.c,now=self.now,http=StageModel(),fetchers={'crossref':fail})
        self.assertEqual(result['status'],'retrieval_failed');self.assertIsNotNone(self.state().model_failure_pause())
