import concurrent.futures
import http.client
import json
import threading
import time
import unittest

from assist_server import DemoService, MAX_BODY_BYTES, make_server


class FakeService:
    def __init__(self):
        self.calls = []
        self.active = 0
        self.max_active = 0

    def status(self):
        self.calls.append(("status",))
        return {"available": True, "busy": False, "message": "測試"}

    def start(self, kind="assist"):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.005)
        self.calls.append(("start", kind))
        self.active -= 1
        return {"ok": True}

    def stop(self):
        self.calls.append(("stop",))
        return {"ok": True}


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.server = make_server(self.service)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method="GET", path="/api/status", data=None, headers=None, raw=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        normal = {}
        if method == "POST":
            normal = {"Origin": self.server.origin, "X-AF-Token": self.server.token,
                      "Content-Type": "application/json"}
        if headers:
            for key, value in headers.items():
                if value is None:
                    normal.pop(key, None)
                else:
                    normal[key] = value
        connection.request(method, path, body=body, headers=normal)
        response = connection.getresponse()
        status, received_headers, body = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, received_headers, body

    def start(self, **kwargs):
        return self.request("POST", "/api/start", data={"kind": "assist", "armed": True}, **kwargs)

    def test_loopback_only(self):
        for host in ("0.0.0.0", "localhost", "::1", "192.168.1.1"):
            with self.assertRaises(ValueError):
                make_server(self.service, host=host)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_random_token_and_url_fragment(self):
        second = make_server(self.service)
        try:
            self.assertNotEqual(self.server.token, second.token)
            self.assertGreaterEqual(len(self.server.token), 32)
            self.assertEqual(self.server.url, self.server.origin + "/#token=" + self.server.token)
        finally:
            second.server_close()

    def test_status_read_does_not_trigger_motion(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["available"])
        self.assertEqual(self.service.calls, [("status",)])
        self.assertNotIn(self.server.token.encode(), body)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_start_and_stop_delegate_once(self):
        self.assertEqual(self.start()[0], 200)
        self.assertEqual(self.request("POST", "/api/start", {"kind": "native", "armed": True})[0], 200)
        self.assertEqual(self.request("POST", "/api/stop", {})[0], 200)
        self.assertEqual(self.service.calls, [("start", "assist"), ("start", "native"), ("stop",)])

    def test_all_post_endpoints_require_token_and_origin(self):
        for path, data in (("/api/start", {"kind": "assist", "armed": True}), ("/api/stop", {})):
            for headers in ({"X-AF-Token": None}, {"X-AF-Token": "bad"},
                            {"Origin": None}, {"Origin": "null"},
                            {"Origin": "https://example.com"},
                            {"Origin": self.server.origin + "/"}):
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.request("POST", path, data, headers)[0], 403)
        self.assertEqual(self.service.calls, [])

    def test_exact_host_on_read_and_write(self):
        for host in ("evil.test", "localhost:" + str(self.server.server_address[1]),
                     self.server.authority + ".evil.test"):
            self.assertEqual(self.request(headers={"Host": host})[0], 403)
            self.assertEqual(self.start(headers={"Host": host})[0], 403)
        self.assertEqual(self.service.calls, [])

    def test_no_get_mutations_or_post_status(self):
        for path in ("/api/start", "/api/stop", "/api/start?kind=assist", "/api/status?start=1"):
            self.assertEqual(self.request(path=path)[0], 404)
        self.assertEqual(self.request("POST", "/api/status", {})[0], 404)
        self.assertEqual(self.service.calls, [])

    def test_whitelisted_payload_and_explicit_boolean_arm(self):
        invalid = [{}, {"kind": "assist"}, {"kind": "assist", "armed": False},
                   {"kind": "assist", "armed": 1}, {"kind": "assist", "armed": "true"},
                   {"kind": "shell", "armed": True}, {"kind": ["assist"], "armed": True},
                   {"kind": "assist", "armed": True, "target": 5},
                   {"kind": "assist", "armed": True, "command": "anything"}]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.request("POST", "/api/start", value)[0], 422)
        self.assertEqual(self.request("POST", "/api/stop", {"command": "anything"})[0], 422)
        self.assertEqual(self.service.calls, [])

    def test_bounded_body_before_parsing(self):
        self.assertEqual(self.request("POST", "/api/start", raw=b"x" * (MAX_BODY_BYTES + 1))[0], 413)
        self.assertEqual(self.request("POST", "/api/start", raw=b"{}",
                                      headers={"Content-Length": "999999999999999999"})[0], 413)
        self.assertEqual(self.service.calls, [])

    def test_malformed_and_ambiguous_json_rejected(self):
        values = [b"[]", b"null", b"not json", b"\xff", b'{"armed":true,"armed":false}',
                  b'{"kind":"assist","armed":NaN}', b"[" * 1100]
        for raw in values:
            with self.subTest(raw=raw[:50]):
                self.assertEqual(self.request("POST", "/api/start", raw=raw)[0], 400)
        self.assertEqual(self.service.calls, [])

    def test_non_json_and_chunked_rejected(self):
        self.assertEqual(self.start(headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.start(headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.service.calls, [])

    def test_duplicate_security_headers_rejected(self):
        for field, value in (("Host", self.server.authority), ("Origin", self.server.origin),
                             ("X-AF-Token", self.server.token)):
            connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
            connection.putrequest("POST", "/api/stop", skip_host=True)
            for key, item in (("Host", self.server.authority), ("Origin", self.server.origin),
                              ("X-AF-Token", self.server.token), ("Content-Type", "application/json"),
                              ("Content-Length", "2")):
                connection.putheader(key, item)
            connection.putheader(field, value)
            connection.endheaders(b"{}")
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.close()
        self.assertEqual(self.service.calls, [])

    def test_other_methods_do_not_delegate(self):
        for method in ("OPTIONS", "HEAD", "PUT", "PATCH", "DELETE"):
            self.assertEqual(self.request(method, "/api/start")[0], 405)
        self.assertEqual(self.service.calls, [])

    def test_index_has_csp_nonce_and_no_secret_or_remote_assets(self):
        code, headers, body = self.request(path="/")
        self.assertEqual(code, 200)
        self.assertNotIn(b"__CSP_NONCE__", body)
        self.assertNotIn(self.server.token.encode(), body)
        self.assertNotIn(b"https://", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("script-src 'nonce-", headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
        self.assertEqual(self.service.calls, [])

    def test_concurrent_requests_serialize_service_entry_points(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            statuses = list(workers.map(lambda _: self.start()[0], range(12)))
        self.assertEqual(statuses, [200] * 12)
        self.assertEqual(self.service.max_active, 1)
        self.assertEqual(len(self.service.calls), 12)

    def test_service_error_never_retries_or_leaks_traceback(self):
        def broken_start(kind):
            self.service.calls.append(("start", kind))
            raise RuntimeError("private camera debug details")
        self.service.start = broken_start
        code, _, body = self.start()
        self.assertEqual(code, 500)
        self.assertNotIn(b"private", body)
        self.assertEqual(self.service.calls, [("start", "assist")])

    def test_validated_port(self):
        for port in (-1, 65536, True, "8000"):
            with self.assertRaises(ValueError):
                make_server(self.service, port=port)


class DemoTest(unittest.TestCase):
    def test_demo_explicitly_marks_synthetic_data(self):
        demo = DemoService()
        self.assertTrue(demo.status()["demo"])
        self.assertFalse(demo.status()["busy"])
        self.assertTrue(demo.start()["ok"])
        self.assertTrue(demo.status()["busy"])
        self.assertFalse(demo.start("native")["ok"])
        self.assertTrue(demo.stop()["ok"])
        self.assertFalse(demo.status()["busy"])
        self.assertIn("模擬", demo.status()["outcome"])


if __name__ == "__main__":
    unittest.main()
