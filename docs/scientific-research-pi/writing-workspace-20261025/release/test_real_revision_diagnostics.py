"""Private probe diagnostics: no model, subprocess, queue or network access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'panghu_agent'))
spec=importlib.util.spec_from_file_location('real_revision_probe_diagnostics',Path(__file__).with_name('real_revision_probe.py'))
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class DiagnosticTests(unittest.TestCase):
    def classification(self,code='model_error',retryable=False):
        return SimpleNamespace(code=code,retryable=retryable)

    def test_private_text_redacts_all_env_values_and_common_credentials_before_limit(self):
        secret='provider-token-fixture'
        message=('401 Authorization: Bearer bearer-fixture-abcdef api_key=unknown-fixture '
                 '"password":"private-password" https://user:pass@example.org '
                 'sk-abcDEF1234567 eyJabcdef.eyJghijkl.signature '+secret+' tail ')*100
        text=probe.redacted_model_error(message,{'KEY':secret,'EMPTY':''})
        self.assertLessEqual(len(text),2000)
        for value in (secret,'bearer-fixture-abcdef','unknown-fixture','private-password',
                      'user:pass','sk-abcDEF1234567','eyJabcdef.eyJghijkl.signature'):
            self.assertNotIn(value,text)
        self.assertIn('[REDACTED]',text)

    def test_public_diagnostic_contains_only_status_categories_markers_and_hash(self):
        raw='400 invalid_request_error: tool schema additionalProperties strict tools; private prompt body'
        public,private=probe.model_error_diagnostic({'errorMessage':raw},self.classification(),{})
        self.assertEqual(public['http_status'],400)
        self.assertIn('tool_schema',public['categories'])
        self.assertEqual(public['schema_field_markers'],['tools','additionalproperties','strict'])
        self.assertEqual(public['provider_code_markers'],['invalid_request_error'])
        self.assertEqual(public['error_message_sha256'],probe.sha(raw.encode()))
        self.assertNotIn('private prompt',json.dumps(public))
        self.assertIn('private prompt',private['error_message_redacted'])

    def test_transient_classification_return_is_unchanged_and_called_once(self):
        result=self.classification('model_http_transient',True)
        calls=[]
        runtime=SimpleNamespace(settings=SimpleNamespace(model_env={'KEY':'secret-fixture'}))
        def classify(message):
            calls.append(message)
            return result
        runtime._model_request_error=classify
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()) as output:
            original,events=probe.observe_model_errors(runtime,Path(directory))
            message={'errorMessage':'429 rate_limit_exceeded secret-fixture','toolResult':'NEVER EXPORT',
                     'content':'PRIVATE PROMPT'}
            self.assertIs(runtime._model_request_error(message),result)
            self.assertEqual(calls,[message])
            self.assertIs(original,classify)
            public=json.loads(output.getvalue())
            self.assertEqual(public['http_status'],429)
            self.assertTrue(public['retryable'])
            self.assertTrue(public['private_record_saved'])
            self.assertEqual(events,[public])
            for unsafe in ('secret-fixture','PRIVATE PROMPT','NEVER EXPORT','error_message_redacted'):
                self.assertNotIn(unsafe,output.getvalue())
            private=json.loads((Path(directory)/'model-error-001.private.json').read_text())
            self.assertNotIn('secret-fixture',private['error_message_redacted'])

    def test_categories_distinguish_context_timeout_auth_and_schema(self):
        for text,category,status in (
            ('400 context_length_exceeded maximum context length exceeded','context_limit',400),
            ('HTTP 401 Unauthorized invalid API key','authentication',401),
            ('request timed out after deadline','timeout',None),
            ('400 unsupported parameter tool_choice','tool_schema',400)):
            public,_=probe.model_error_diagnostic({'errorMessage':text},self.classification(),{})
            self.assertIn(category,public['categories'])
            self.assertEqual(public['http_status'],status)

    def test_missing_error_text_or_malicious_classification_never_exports_raw(self):
        public,_=probe.model_error_diagnostic({'errorMessage':{'prompt':'private'}},
                    self.classification('PRIVATE PROMPT'),{})
        self.assertFalse(public['error_message_present'])
        self.assertEqual(public['runtime_error_code'],'unrecognized_error_class')
        self.assertNotIn('PRIVATE PROMPT',json.dumps(public))

    def test_failure_queue_snapshot_survives_workspace_cleanup_without_error_text(self):
        snapshot=dict(state='failed',error_code='model_error',attempt=1,revision=4,
                      error='private upstream prompt/token detail',report='NEVER EXPORT')
        diagnostic=probe.queue_failure_diagnostic(snapshot,[{}])
        self.assertEqual(diagnostic['error_code'],'model_error')
        self.assertEqual(diagnostic['observed_model_error_count'],1)
        self.assertEqual(diagnostic['attempt'],1)
        self.assertNotIn('private upstream',json.dumps(diagnostic))
        self.assertNotIn('NEVER EXPORT',json.dumps(diagnostic))
        self.assertEqual(diagnostic['error_message_sha256'],probe.sha(snapshot['error'].encode()))

    def test_diagnostic_file_write_failure_does_not_change_classification(self):
        expected=self.classification()
        runtime=SimpleNamespace(settings=SimpleNamespace(model_env={}),_model_request_error=lambda message:expected)
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()) as output:
            probe.observe_model_errors(runtime,Path(directory)/'absent')
            self.assertIs(runtime._model_request_error({'errorMessage':'500 server error'}),expected)
            self.assertFalse(json.loads(output.getvalue())['private_record_saved'])


if __name__=='__main__':
    unittest.main(verbosity=2)
