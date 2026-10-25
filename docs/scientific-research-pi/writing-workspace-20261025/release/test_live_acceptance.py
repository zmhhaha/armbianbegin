"""Local synthetic operator-probe coverage; never certifies a real model run."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/'panghu_agent'
sys.path.insert(0,str(SOURCE))
sys.path.insert(0,str(SOURCE/'tests/scientific_pi/api'))
spec=importlib.util.spec_from_file_location('deployed_writing_acceptance',HERE/'live_acceptance.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

from fastapi.testclient import TestClient
from app.api.scientific_agent import create_app
from scientific_agent.pi_projection import PiProjection
from test_api import MemoryDB, FakeWorker
from test_citation_api import records_for
import tools
from tools import sqlite_client


class LiveAcceptanceTests(unittest.TestCase):
    REPORT='# Synthetic abstract review\r\n\r\n## Evidence\r\n\r\n<!-- claim:c1 -->\r\nSynthetic finding [1].\r\n'

    def setUp(self):
        self.database,self.worker=MemoryDB(),FakeWorker()
        self.projection=PiProjection(self.database,self.worker,'skills-pinned','runtime-pinned',
            lambda *args: self.fail('Operator acceptance must not send mail'))
        self.client=TestClient(create_app(self.database,self.worker,self.projection,start_reconciler=False))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)
        self.addCleanup(self.database.connection.close)
        self.items,self.artifacts=records_for(self.REPORT)
        self.addCleanup(patch.stopall)
        patch.object(self.worker,'artifacts',return_value={'items':self.items}).start()
        patch.object(self.worker,'artifact',side_effect=lambda task_id,artifact_id,max_bytes:(self.artifacts[artifact_id],{})).start()
        patch.object(self.worker,'health',return_value=dict(alive=True,queue_writable=True,runtime_ready=True,worker_ready=True,
            capabilities=dict(revision_job_versions=['1'],revision_input_scope='recorded_evidence_only',max_revision_input_bytes=16*1024*1024))).start()
        patch.object(tools,'sqlite_client',self.database).start()
        self.actions=[]
        def request(path,owner=None,*,body=None,key=None):
            self.actions.append((path,owner,body))
            headers={}
            if owner is not None: headers['X-Forwarded-User']=owner
            if key is not None: headers['Idempotency-Key']=key
            response=self.client.request('GET' if body is None else 'POST',path,headers=headers,
                **({} if body is None else {'json':body}))
            return response.status_code,response.content,{key.casefold():value for key,value in response.headers.items()}
        patch.object(probe,'request',side_effect=request).start()

    def seed(self,owner):
        # Synthetic setup is deliberately separate from the operator probe.
        task=self.client.post('/scientific-research',json={'topic':'Synthetic operator fixture'},
            headers={'X-Forwarded-User':owner}).json()['id']
        self.worker.complete(task,self.REPORT)
        self.projection.reconcile()
        return task

    def run_probe(self,read_only=False):
        output=io.StringIO()
        command=['live_acceptance.py','--source-commit','a'*40]+(['--read-only'] if read_only else [])
        with patch.object(sys,'argv',command),redirect_stdout(output): probe.main()
        return json.loads(output.getvalue())

    def assert_no_execution(self,result):
        self.assertFalse(result['real_model_requested'])
        self.assertFalse(result['revision_started'])
        self.assertFalse(result['candidate_adopted'])
        self.assertEqual((self.worker.put_count,self.worker.ack_count),(1,1))
        self.assertFalse(any(path.endswith(('/start','/adopt','/cancel')) for path,_,body in self.actions if body is not None))

    def test_canary_prepares_exact_private_input_and_replays_without_any_execution(self):
        report_id=self.seed('synthetic-writing-canary')
        first=self.run_probe()
        second=self.run_probe()
        self.assertEqual((first['status'],second['status']),('passed','passed'))
        self.assertEqual(first['intent_id'],second['intent_id'])
        self.assertEqual(first['root_report_id'],report_id)
        self.assertIn('prepared_intent_has_explicit_start_route_without_starting',first['checks'])
        self.assertIn('writing_state_comparison_adopt_and_start_routes_registered',first['checks'])
        self.assertEqual(second['counts_after'],second['counts_before'])
        self.assertEqual(first['counts_after']['adoptions'],0)
        self.assertEqual(first['counts_after']['revision_jobs'],0)
        self.assert_no_execution(second)

    def test_read_only_disables_even_canary_preparation_and_preserves_all_tables(self):
        self.seed('synthetic-writing-canary')
        result=self.run_probe(read_only=True)
        self.assertEqual(result['status'],'passed')
        self.assertIn('canary_preparation_disabled_by_read_only',result['skipped'])
        self.assertEqual(result['counts_before'],result['counts_after'])
        self.assertFalse(any(body is not None for _,_,body in self.actions))
        self.assert_no_execution(result)

    def test_ordinary_user_is_only_read_and_never_borrowed_for_canary_writes(self):
        self.seed('ordinary-user')
        result=self.run_probe()
        self.assertEqual(result['status'],'partial')
        self.assertIn('no_available_canary_report_preparation_not_attempted_on_real_user',result['skipped'])
        self.assertFalse(any(body is not None for _,_,body in self.actions))
        self.assertEqual(result['counts_before'],result['counts_after'])
        self.assert_no_execution(result)

    def test_missing_adoption_schema_route_or_revision_capability_blocks_acceptance(self):
        schema=self.client.get('/openapi.json').json()
        probe.check_writing_routes(schema)
        missing=copy.deepcopy(schema)
        missing['paths']['/scientific-report-versions/{candidate_id}/adopt'].pop('post')
        with self.assertRaises(probe.ProbeError): probe.check_writing_routes(missing)
        valid=self.worker.health()
        probe.check_revision_capabilities(valid)
        for changed in ({'revision_job_versions':[]},{'revision_input_scope':'retrieval_allowed'},
                        {'max_revision_input_bytes':True},{'max_revision_input_bytes':0}):
            with self.subTest(changed=changed):
                invalid=copy.deepcopy(valid);invalid['capabilities'].update(changed)
                with self.assertRaises(probe.ProbeError): probe.check_revision_capabilities(invalid)


if __name__=='__main__':unittest.main()
