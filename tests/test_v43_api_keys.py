"""API keys pasted in Settings: local storage, immediate use, masking, provider checks, same-origin guard."""
from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx

from app import secrets_store
from app.services import key_check

NAMES = list(secrets_store.SECRET_NAMES)


class SecretsStoreTests(unittest.TestCase):
    def setUp(self):
        self.saved_env = {n: os.environ.pop(n, None) for n in NAMES}
        secrets_store._original_env.clear()
        secrets_store._applied.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        for n in NAMES:
            os.environ.pop(n, None)
            if self.saved_env[n] is not None:
                os.environ[n] = self.saved_env[n]
        secrets_store._original_env.clear()
        secrets_store._applied.clear()
        self.tmp.cleanup()

    def test_save_applies_immediately_with_owner_only_file(self):
        from app.services.job_sources.job_apis import GOOGLE_JOBS
        self.assertFalse(GOOGLE_JOBS.configured())
        secrets_store.save({"SERPAPI_API_KEY": "  abcd1234efgh5678  "}, self.dir)
        self.assertEqual(os.environ["SERPAPI_API_KEY"], "abcd1234efgh5678")
        self.assertTrue(GOOGLE_JOBS.configured())  # discovery sees it without a restart
        mode = stat.S_IMODE((self.dir / "secrets.json").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_status_never_contains_the_key(self):
        secrets_store.save({"ADZUNA_APP_ID": "app12345", "ADZUNA_APP_KEY": "secretkey987654"}, self.dir)
        text = json.dumps(secrets_store.status(self.dir))
        self.assertNotIn("secretkey987654", text)
        self.assertNotIn("app12345", text)
        adzuna = next(p for p in secrets_store.status(self.dir) if p["id"] == "adzuna")
        self.assertTrue(adzuna["configured"])
        self.assertTrue(adzuna["keys"][1]["hint"].endswith("7654"))

    def test_remove_restores_environment_value(self):
        os.environ["FIRECRAWL_API_KEY"] = "fromenv1234"
        secrets_store.apply_to_environment(self.dir)
        secrets_store.save({"FIRECRAWL_API_KEY": "saved5678xyz"}, self.dir)
        self.assertEqual(os.environ["FIRECRAWL_API_KEY"], "saved5678xyz")
        secrets_store.remove(["FIRECRAWL_API_KEY"], self.dir)
        self.assertEqual(os.environ["FIRECRAWL_API_KEY"], "fromenv1234")

    def test_rejects_malformed_values_and_unknown_names(self):
        with self.assertRaises(ValueError):
            secrets_store.save({"SERPAPI_API_KEY": "has space inside"}, self.dir)
        with self.assertRaises(ValueError):
            secrets_store.save({"SERPAPI_API_KEY": "line\nbreak"}, self.dir)
        with self.assertRaises(ValueError):
            secrets_store.save({"HOME": "whatever123"}, self.dir)
        self.assertFalse((self.dir / "secrets.json").exists())

    def test_redact(self):
        secrets_store.save({"SERPAPI_API_KEY": "zz9876543210"}, self.dir)
        self.assertEqual(secrets_store.redact("bad key zz9876543210 here"), "bad key [redacted] here")


class KeyCheckTests(unittest.TestCase):
    def setUp(self):
        self.saved_env = {n: os.environ.pop(n, None) for n in NAMES}

    def tearDown(self):
        for n in NAMES:
            os.environ.pop(n, None)
            if self.saved_env[n] is not None:
                os.environ[n] = self.saved_env[n]

    def run_check(self, provider, handler):
        return asyncio.run(key_check.check(provider, transport=httpx.MockTransport(handler)))

    def test_not_configured(self):
        result = self.run_check("serpapi", lambda r: httpx.Response(500))
        self.assertFalse(result["ok"])
        self.assertIn("Not configured", result["message"])

    def test_serpapi_valid_and_invalid(self):
        os.environ["SERPAPI_API_KEY"] = "goodkey12345"

        def handler(request):
            self.assertEqual(request.url.path, "/account.json")  # free endpoint, no search spent
            if request.url.params["api_key"] == "goodkey12345":
                return httpx.Response(200, json={"plan_name": "Free Plan", "total_searches_left": 248})
            return httpx.Response(401, json={"error": "Invalid API key."})
        ok = self.run_check("serpapi", handler)
        self.assertTrue(ok["ok"])
        self.assertIn("248 searches left", ok["message"])
        os.environ["SERPAPI_API_KEY"] = "badkey12345"
        bad = self.run_check("serpapi", handler)
        self.assertFalse(bad["ok"])
        self.assertNotIn("badkey12345", bad["message"])

    def test_adzuna_and_firecrawl(self):
        os.environ.update({"ADZUNA_APP_ID": "id123456", "ADZUNA_APP_KEY": "key123456", "FIRECRAWL_API_KEY": "fc-123456"})

        def handler(request):
            if request.url.host == "api.adzuna.com":
                return httpx.Response(200, json={"count": 15234, "results": []})
            if request.url.path.endswith("credit-usage"):
                return httpx.Response(200, json={"success": True, "data": {"remaining_credits": 480}})
            return httpx.Response(404)
        self.assertIn("15,234", self.run_check("adzuna", handler)["message"])
        self.assertIn("480 credits", self.run_check("firecrawl", handler)["message"])
        self.assertFalse(self.run_check("adzuna", lambda r: httpx.Response(401))["ok"])


class RejectedKeyRollbackTests(unittest.TestCase):
    def test_rejected_key_is_not_kept_and_previous_key_survives(self):
        from unittest import mock
        from app.config import Settings
        from app.web import Application
        saved_env = {n: os.environ.pop(n, None) for n in NAMES}
        secrets_store._original_env.clear()
        secrets_store._applied.clear()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                app = Application(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"))
                try:
                    async def good(provider_id, **kw):
                        return {"ok": True, "rejected": False, "message": "works", "detail": {}}

                    async def bad(provider_id, **kw):
                        return {"ok": False, "rejected": True, "message": "SerpApi rejected the key (HTTP 401).", "detail": {}}
                    with mock.patch("app.services.key_check.check", good):
                        out = app.save_api_keys("serpapi", {"SERPAPI_API_KEY": "firstgoodkey1"})
                    self.assertTrue(out["check"]["ok"])
                    with mock.patch("app.services.key_check.check", bad):
                        out = app.save_api_keys("serpapi", {"SERPAPI_API_KEY": "typo-badkey22"})
                    self.assertIn("previous key was kept", out["check"]["message"])
                    self.assertEqual(os.environ["SERPAPI_API_KEY"], "firstgoodkey1")
                    app.remove_api_keys("serpapi")
                    with mock.patch("app.services.key_check.check", bad):
                        out = app.save_api_keys("serpapi", {"SERPAPI_API_KEY": "typo-badkey22"})
                    self.assertIn("not saved", out["check"]["message"])
                    self.assertIsNone(os.environ.get("SERPAPI_API_KEY"))
                finally:
                    app._executor.shutdown(wait=False)
        finally:
            for n in NAMES:
                os.environ.pop(n, None)
                if saved_env[n] is not None:
                    os.environ[n] = saved_env[n]
            secrets_store._original_env.clear()
            secrets_store._applied.clear()


class EndpointGuardTests(unittest.TestCase):
    def test_keys_endpoint_rejects_other_origins_and_never_returns_keys(self):
        from app.config import Settings
        from app.http_handler import make_handler
        from app.web import Application
        saved_env = {n: os.environ.pop(n, None) for n in NAMES}
        secrets_store._original_env.clear()
        secrets_store._applied.clear()
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def call(path, body=None, headers=None):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                             headers=headers or {}, method="POST" if body is not None else "GET")
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        return resp.status, json.loads(resp.read())
                except urllib.error.HTTPError as exc:
                    payload = json.loads(exc.read() or b"{}")
                    exc.close()
                    return exc.code, payload
            try:
                status, _ = call("/api/keys", {"provider": "serpapi", "values": {"SERPAPI_API_KEY": "evil12345678"}},
                                 {"Content-Type": "application/json", "Origin": "https://evil.example"})
                self.assertEqual(status, 403)
                status, _ = call("/api/keys", {"provider": "serpapi", "values": {"SERPAPI_API_KEY": "evil12345678"}},
                                 {"Content-Type": "text/plain"})
                self.assertEqual(status, 403)  # simple cross-site form posts are refused
                self.assertIsNone(os.environ.get("SERPAPI_API_KEY"))
                # The whole API is guarded, not only keys: other sites cannot trigger actions or read data.
                status, _ = call("/api/discover", {}, {"Content-Type": "text/plain"})
                self.assertEqual(status, 403)
                status, _ = call("/api/preferences", {}, {"Content-Type": "application/json",
                                                          "Origin": "http://attacker.test"})
                self.assertEqual(status, 403)
                status, _ = call("/api/bootstrap", None, {"Host": "attacker.test:80"})  # DNS rebinding
                self.assertEqual(status, 403)
                status, _ = call("/api/health")
                self.assertEqual(status, 200)
                os.environ["SERPAPI_API_KEY"] = "envonly987654"
                status, data = call("/api/keys")
                self.assertEqual(status, 200)
                self.assertNotIn("envonly987654", json.dumps(data))
            finally:
                server.shutdown()
                server.server_close()
                app._executor.shutdown(wait=False)
                for n in NAMES:
                    os.environ.pop(n, None)
                    if saved_env[n] is not None:
                        os.environ[n] = saved_env[n]
                secrets_store._original_env.clear()
                secrets_store._applied.clear()


if __name__ == "__main__":
    unittest.main()
