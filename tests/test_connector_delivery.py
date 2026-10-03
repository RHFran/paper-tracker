"""Connector transport uses a real pipeline path with synthetic source/model adapters."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch

from literature_digest.config import DEFAULTS
from literature_digest.connector_delivery import begin_send, confirm_sent
from literature_digest.models import Paper
from literature_digest.pipeline import run
from literature_digest.state import State,state_scope
from test_required_llm import ReviewModel,ENV,EVIDENCE

class ConnectorDelivery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=copy.deepcopy(DEFAULTS)
        self.c.update(language='en',timezone='UTC',state_path=str(Path(self.tmp.name)/'state.db'),output_dir=str(Path(self.tmp.name)/'out'),sources=['crossref'],topics=[{'id':'battery','name':'Battery','queries':['battery'],'include_any':['battery']}])
        self.c['llm']['enabled']=True
        self.now=datetime.now(timezone.utc)
        self.env=patch.dict(os.environ,ENV,clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.network=patch('literature_digest.http.HttpClient.request',side_effect=AssertionError('real network forbidden'));self.network.start();self.addCleanup(self.network.stop)

    def fetch(self):
        d=self.now.date()
        paper=Paper('Synthetic battery study','one','crossref','https://example.org/p',doi='10.9999/synthetic',abstract=EVIDENCE,provenance=[{'date_fields':{'published-online':{'date-parts':[[d.year,d.month,d.day]]}}}])
        return {'crossref':lambda *a:([paper],{'complete':True})}

    def prepare(self):
        return run(self.c,prepare_connector=True,now=self.now,http=ReviewModel(),fetchers=self.fetch())

    def receipt(self,r,status='accepted'):
        return {'digest_id':r['digest_id'],'envelope_sha256':r['envelope_sha256'],'provider':'synthetic-mail','status':status,'sender':'sender@example.org','recipient':self.c['recipient'],'message_id':'provider-123','accepted_at':self.now.isoformat(),'provider_receipt':{'message_id':'provider-123','status':'accepted'}}

    def state(self):
        state=State(self.c['state_path'],scope=state_scope(self.c));self.addCleanup(state.close);return state

    def test_full_pipeline_prepares_immutable_bundle_without_mail(self):
        result=self.prepare();self.assertEqual(result['status'],'prepared')
        audit=json.loads(Path(result['paths']['audit']).read_text())
        self.assertEqual(audit['papers'][0]['analysis']['mode'],'llm_grounded')
        self.assertEqual(audit['overview']['mode'],'llm_grounded')
        envelope=json.loads(Path(result['paths']['envelope']).read_text())
        self.assertEqual(len(envelope['attachments']),2)
        self.assertIsNone(self.state().checkpoint())
        self.assertEqual(self.state().receipt(result['digest_id']),None)

    def test_repeat_prepare_reuses_without_source_or_model_calls(self):
        a=self.prepare();before=Path(a['paths']['envelope']).read_bytes()
        b=run(self.c,prepare_connector=True,now=self.now,fetchers={'crossref':lambda *a:self.fail('re-fetch')})
        self.assertTrue(b['reused_prepared_outbox']);self.assertEqual(before,Path(b['paths']['envelope']).read_bytes())

    def test_one_shot_claim_then_acceptance_is_atomic_idempotent(self):
        r=self.prepare();identifier=r['digest_id'];begin_send(self.c,identifier,now=self.now)
        with self.assertRaises(ValueError):begin_send(self.c,identifier,now=self.now)
        receipt=self.receipt(r);result=confirm_sent(self.c,identifier,receipt)
        self.assertEqual(result['status'],'sent');self.assertFalse(result['delivery_guaranteed'])
        self.assertEqual(self.state().receipt(identifier),receipt)
        self.assertEqual(self.state().checkpoint(),self.now.date().isoformat())
        self.assertTrue(confirm_sent(self.c,identifier,receipt)['already_confirmed'])
        receipt['message_id']='other'
        with self.assertRaises(ValueError):confirm_sent(self.c,identifier,receipt)

    def test_uncertain_receipt_never_enables_resend(self):
        r=self.prepare();identifier=r['digest_id'];begin_send(self.c,identifier,now=self.now)
        result=confirm_sent(self.c,identifier,self.receipt(r,'pending'))
        self.assertEqual(result['status'],'uncertain');self.assertIsNone(self.state().checkpoint())
        with self.assertRaises(ValueError):begin_send(self.c,identifier,now=self.now)
        with self.assertRaises(ValueError):self.state().resolve(identifier,'retry')
        self.assertEqual(confirm_sent(self.c,identifier,self.receipt(r))['status'],'sent')

    def test_accepted_without_message_id_stays_uncertain(self):
        r=self.prepare();begin_send(self.c,r['digest_id'],now=self.now)
        receipt=self.receipt(r);del receipt['message_id']
        self.assertEqual(confirm_sent(self.c,r['digest_id'],receipt)['status'],'uncertain')

    def test_wrong_receipt_scope_or_hash_rejected(self):
        r=self.prepare();begin_send(self.c,r['digest_id'],now=self.now)
        for key,value in [('recipient','other@example.org'),('envelope_sha256','bad'),('digest_id','bad')]:
            receipt=self.receipt(r);receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):confirm_sent(self.c,r['digest_id'],receipt)
        self.assertEqual(self.state().get(r['digest_id'])['status'],'sending')

    def test_cannot_confirm_unclaimed_outbox(self):
        r=self.prepare()
        with self.assertRaises(ValueError):confirm_sent(self.c,r['digest_id'],self.receipt(r))

    def test_tampered_artifact_blocks_claim(self):
        r=self.prepare();Path(r['paths']['html']).write_text('tampered')
        with self.assertRaisesRegex(ValueError,'integrity'):begin_send(self.c,r['digest_id'],now=self.now)
        self.assertEqual(self.state().get(r['digest_id'])['status'],'prepared')

    def test_no_smtp_replay_of_connector_payload(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'Connector'):run(self.c,send=True,now=self.now,mail_adapter=lambda *a:self.fail('SMTP called'))

    def test_changed_config_cannot_reuse_or_claim_stale_envelope(self):
        r=self.prepare();changed=copy.deepcopy(self.c);changed['language']='de'
        with self.assertRaisesRegex(ValueError,'settings changed'):begin_send(changed,r['digest_id'],now=self.now)
        with self.assertRaisesRegex(ValueError,'settings changed'):run(changed,prepare_connector=True,now=self.now)

    def test_message_id_must_match_actual_response(self):
        r=self.prepare();begin_send(self.c,r['digest_id'],now=self.now)
        receipt=self.receipt(r);receipt['provider_receipt']={'message_id':'another-id'}
        with self.assertRaisesRegex(ValueError,'message identifier'):confirm_sent(self.c,r['digest_id'],receipt)
        self.assertEqual(self.state().get(r['digest_id'])['status'],'sending')

    def test_failed_model_never_creates_envelope(self):
        with self.assertRaises(RuntimeError):run(self.c,prepare_connector=True,now=self.now,http=ReviewModel('failure'),fetchers=self.fetch())
        self.assertEqual(self.state().recent(),[]);self.assertFalse(Path(self.c['output_dir']).exists())

if __name__=='__main__':unittest.main()
