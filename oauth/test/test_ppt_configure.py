"""Public PPT client rendering admits authenticated accounts without a list."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
import tomllib
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "k8s" / "configure-ppt.py"
SPEC = importlib.util.spec_from_file_location("configure_ppt", SCRIPT)
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class PptConfigureTests(unittest.TestCase):
    def test_client_binds_proxy_and_audience_without_rewriting_source(self):
        original = CONFIG.TEMPLATE.read_bytes()
        documents = list(yaml.safe_load_all(CONFIG.render_configuration("ppt-test-client")))
        maps = {doc["metadata"]["name"]: doc["data"] for doc in documents}
        self.assertEqual(set(maps), {"ppt-auth", "ppt-oidc"})
        self.assertEqual({doc["metadata"]["namespace"] for doc in documents}, {"ppt-service"})
        self.assertEqual(maps["ppt-auth"]["OIDC_AUDIENCE"], "ppt-test-client")
        self.assertEqual(tomllib.loads(maps["ppt-oidc"]["oauth2-proxy.cfg"])["client_id"],
                         "ppt-test-client")
        self.assertEqual(maps["ppt-auth"]["ALLOWED_ORIGINS"], "https://ppt-service.panghuer.top")
        self.assertEqual(CONFIG.TEMPLATE.read_bytes(), original)

    def test_site_and_proxy_admit_authenticated_accounts_without_a_list(self):
        documents = list(yaml.safe_load_all(CONFIG.render_configuration("ppt-test-client")))
        maps = {doc["metadata"]["name"]: doc["data"] for doc in documents}
        proxy = tomllib.loads(maps["ppt-oidc"]["oauth2-proxy.cfg"])
        self.assertEqual(proxy["email_domains"], ["*"])
        self.assertNotIn("INVITATION_EMAILS_FILE", maps["ppt-auth"])
        self.assertNotIn("authenticated_emails_file", proxy)
        self.assertEqual(proxy["provider"], "oidc")
        self.assertTrue(proxy["pass_authorization_header"])
        self.assertTrue(proxy["cookie_secure"])
        self.assertEqual(proxy["api_routes"], ["^/api/"])
        self.assertNotIn("INVITATION_SUBJECTS", maps["ppt-auth"])
        self.assertNotIn("allowed-emails", maps["ppt-oidc"])

    def test_client_can_be_configured_without_an_owner_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ppt-proxy-configmap.yaml"
            source.write_bytes(CONFIG.TEMPLATE.read_bytes())
            self.assertFalse(source.with_name("ppt-owner-configmap.yaml").exists())
            rendered = CONFIG.render_configuration("ppt-test-client", template=source)
            self.assertNotIn("name: ppt-owner", rendered)

    def test_reject_empty_placeholder_or_injected_client(self):
        for client in ["", " ", "REQUIRED_DEDICATED_PPT_CLIENT_ID", "placeholder", "xxx",
                       "your-client-id", "YOUR_ACTUAL_ID", "replace-me", "change-me",
                       "client\nnew", 'abc"new', "*", 12]:
            with self.subTest(case=repr(client)), self.assertRaises(CONFIG.ConfigurationError):
                CONFIG.render_configuration(client)

    def test_client_regeneration_does_not_read_render_or_change_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ppt-proxy-configmap.yaml"
            source.write_bytes(CONFIG.TEMPLATE.read_bytes())
            owner = source.with_name("ppt-owner-configmap.yaml")
            original = b"independent list: alice@example.test\n"
            owner.write_bytes(original)
            for number in range(2):
                output = Path(directory) / f"rendered-{number}.yaml"
                CONFIG.configure(f"ppt-test-client-{number}", output, template=source)
                self.assertNotIn("alice@example.test", output.read_text(encoding="utf-8"))
                self.assertNotIn("name: ppt-owner", output.read_text(encoding="utf-8"))
            self.assertEqual(owner.read_bytes(), original)

    def test_new_file_only_and_cli_does_not_print_client_value(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "rendered.yaml"
            out, err = io.StringIO(), io.StringIO()
            args = ["--client-id", "ppt-test-client", "--output", str(output)]
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(CONFIG.main(args), 0)
            first = output.read_bytes()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(CONFIG.main(args), 2)
            self.assertEqual(output.read_bytes(), first)
            self.assertNotIn("ppt-test-client", out.getvalue() + err.getvalue())
            self.assertIn("output_exists", err.getvalue())

    def test_invite_argument_is_removed_and_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "rendered.yaml"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                CONFIG.main(["--client-id", "ppt-test-client", "--output", str(output),
                             "--invites", "unused.json"])
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse(output.exists())

    def test_template_rejects_drifted_identity_or_reintroduced_list(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "template.yaml"
            text = CONFIG.TEMPLATE.read_text(encoding="utf-8")
            for modified in [text.replace("OIDC_AUDIENCE: REQUIRED_DEDICATED_PPT_CLIENT_ID",
                                          "OIDC_AUDIENCE: different"),
                             text.replace("kind: ConfigMap", "kind: Secret", 1),
                             text.replace("namespace: ppt-service", "namespace: ppt-service-test"),
                             text.replace("  OIDC_ISSUER:", "  INVITATION_SUBJECTS: legacy\n  OIDC_ISSUER:"),
                             text.replace("  OIDC_ISSUER:", "  INVITATION_EMAILS_FILE: /owner/emails\n  OIDC_ISSUER:"),
                             text.replace('email_domains = ["*"]', 'authenticated_emails_file = "/owner/emails"'),
                             text.replace('email_domains = ["*"]', 'email_domains = ["example.com"]')]:
                source.write_text(modified, encoding="utf-8")
                with self.assertRaises(CONFIG.ConfigurationError):
                    CONFIG.render_configuration("ppt-test-client", template=source)


if __name__ == "__main__":
    unittest.main()
