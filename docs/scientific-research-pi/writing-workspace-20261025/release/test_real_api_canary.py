"""Synthetic local HTTP control-flow tests, never real Pi/model acceptance."""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/'panghu_agent'
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tests/scientific_pi/api'))
spec=importlib.util.spec_from_file_location('dedicated_real_api_canary',HERE/'real_api_canary.py')
canary=importlib.util.module_from_spec(spec);spec.loader.exec_module(canary)

from fastapi.testclient import TestClient
from app.api.scientific_agent import create_app
from scientific_agent.pi_projection import PiProjection
from scientific_agent.pi_sections import index_sections
from test_api import MemoryDB
from test_citation_api import records_for
import test_revision_execution as revision_fixture


class RealApiCanaryTests(unittest.TestCase):
    def test_non_canary_owner_or_other_report_is_rejected_before_any_io(self):
        for owner,report in (('27714443',canary.REPORT_ID),(canary.OWNER,'27714443')):
            with self.subTest(owner=owner,report=report),patch.object(canary,'api') as api:
                with self.assertRaises(canary.CanaryError):
                    canary.run(argparse.Namespace(owner=owner,report_id=report,source_commit='a'*40,output_dir=Path('never-created')))
                api.assert_not_called()

    def test_leaf_selection_skips_parents_reference_and_uncited_sections(self):
        report=('# Review\n\n## Parent\n\n### Evidence\n\n'
                'A cited synthetic abstract finding [1] with carefully bounded limitations.\n\n'
                '## References\n\nA synthetic reference [1] with substantial filler text for selection.\n\n')
        index=index_sections(report)
        chosen=canary.select_leaf(index,report.encode())
        self.assertEqual(chosen['title'],'Evidence')
        chosen['sha256']='0'*64
        with self.assertRaises(canary.CanaryError): canary.select_leaf(index,report.encode())

    def test_real_api_contract_flow_with_synthetic_worker_is_resumable_and_never_emails(self):
        database,worker=MemoryDB(),revision_fixture.RevisionWorker()
        self.addCleanup(database.connection.close)
        sent=[]
        projection=PiProjection(database,worker,'skills-pinned','runtime-pinned',lambda *args:sent.append(args))
        client=TestClient(create_app(database,worker,projection,start_reconciler=False))
        client.__enter__();self.addCleanup(client.__exit__,None,None,None)
        owner=canary.OWNER
        report=revision_fixture.RevisionExecutionTests.REPORT
        parent_task=client.post('/scientific-research',json={'topic':'Synthetic D2 fixture'},headers={'X-Forwarded-User':owner}).json()['id']
        worker.complete(parent_task,report);projection.reconcile()
        base_items,base_artifacts=records_for(report)
        actions=[]
        lost_start=[False]
        lost_adopt=[False]
        def request(path,user=owner,*,body=None,key=None):
            actions.append((path,user,body))
            headers={}
            if user is not None: headers['X-Forwarded-User']=user
            if key is not None: headers['Idempotency-Key']=key
            response=client.request('GET' if body is None else 'POST',path,headers=headers,
                **({} if body is None else {'json':body}))
            if path.endswith('/start') and response.status_code==200:
                task_id=response.json()['id']
                if task_id not in worker.files:
                    worker.candidate(task_id)
                    # Fill the real QueueStore snapshot fields missing from
                    # this explicitly synthetic in-memory worker fixture.
                    worker.tasks[task_id].update(report_sha256=worker.results[task_id]['report_sha256'],
                        result_digest=worker.results[task_id]['result_digest'])
                    projection.reconcile()
                if not lost_start[0]:
                    lost_start[0]=True
                    return 503,json.dumps({'detail':{'code':'storage_unavailable','task_id':task_id}}).encode(),{}
            if path.endswith('/adopt') and response.status_code==200 and not lost_adopt[0]:
                lost_adopt[0]=True
                return 503,b'{"detail":{"code":"storage_unavailable"}}',{}
            return response.status_code,response.content,{key.casefold():value for key,value in response.headers.items()}
        def artifact(task_id,name,max_bytes=None):
            return (base_artifacts if task_id==parent_task else worker.files[task_id])[name],{}
        def artifacts(task_id):
            return {'items':base_items if task_id==parent_task else worker.results[task_id]['artifacts']}
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory, \
             patch.object(canary,'REPORT_ID',parent_task),patch.object(canary,'request',side_effect=request), \
             patch.object(canary.time,'sleep',return_value=None), \
             patch.object(worker,'artifact',side_effect=artifact),patch.object(worker,'artifacts',side_effect=artifacts):
            args=argparse.Namespace(owner=owner,report_id=parent_task,source_commit='a'*40,output_dir=Path(directory))
            output=io.StringIO()
            with redirect_stdout(output):
                first=canary.run(args)
                replay=canary.run(args)
            self.assertEqual(first['status'],'passed',first)
            self.assertEqual(replay['status'],'passed',replay)
            self.assertEqual(first['task_id'],replay['task_id'])
            self.assertEqual(first['adoption_id'],replay['adoption_id'])
            self.assertEqual(replay['selection_revision'],1)
            self.assertTrue(lost_start[0])
            self.assertTrue(lost_adopt[0])
            self.assertTrue((Path(directory)/'review-materials/candidate-section.md').is_file())
            self.assertTrue((Path(directory)/'review-materials/candidate-evidence.jsonl').is_file())
            self.assertNotIn('<!-- claim:',output.getvalue())
            self.assertEqual(database.get_report(parent_task)['content'],report)
        self.assertEqual(sent,[])
        self.assertEqual(len(worker.revision_jobs),1)
        self.assertFalse(any(path.endswith('/cancel') for path,_,body in actions if body is not None))
        self.assertTrue(all(user==owner for _,user,body in actions if body is not None))


if __name__=='__main__': unittest.main()
