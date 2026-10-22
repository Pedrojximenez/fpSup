#!/usr/bin/env python3
"""Loopback-only HTTP interface for an injected, nonblocking AF service.

No USB or camera code belongs here.  The service is responsible for camera
ownership, current-state checks, motion limits, and cleanup.  ``start`` and
``stop`` must queue work and return promptly; status must not start camera work.
Running this module by itself uses an explicitly labelled offline demonstration.
"""

import argparse
import base64
import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_BODY_BYTES = 4096
HTML_PATH = Path(__file__).resolve().parent / "web" / "index.html"


class DemoService:
    """Synthetic state only; never imports or calls a camera transport."""

    demo = True

    def __init__(self):
        self._started_at = None
        self._kind = None
        self._stopped = False

    def status(self):
        elapsed = (time.monotonic() - self._started_at
                   if self._started_at is not None else 0)
        running = self._started_at is not None and elapsed < 3 and not self._stopped
        finished = self._started_at is not None and not running and not self._stopped
        return {
            "demo": True,
            "available": True,
            "busy": running,
            "state": "running" if running else "idle",
            "message": ("離線模擬中：沒有連接或操作相機。" if running else
                        "離線展示：所有讀值與結果都是模擬，沒有操作相機。"),
            "roi": "模擬：中央單一對焦框",
            "position": 10000 if not finished else 9990,
            "h": 123456 if not finished else 124100,
            "progress": min(1.0, elapsed / 3) if self._started_at is not None else 0,
            "outcome": ("模擬停止；沒有硬體動作。" if self._stopped else
                        "模擬完成；不能當作實機驗證。" if finished else None),
        }

    def start(self, kind="assist"):
        if self.status()["busy"]:
            return {"ok": False, "message": "已有模擬工作執行中。"}
        self._started_at = time.monotonic()
        self._kind = kind
        self._stopped = False
        return {"ok": True, "message": "已開始離線模擬，沒有操作相機。"}

    def stop(self):
        self._stopped = True
        return {"ok": True, "message": "已停止離線模擬，沒有操作相機。"}


class AssistHTTPServer(ThreadingHTTPServer):
    """The small HTTP layer serializes service entry points, not camera jobs."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, service, port=0, host="127.0.0.1"):
        if host != "127.0.0.1":
            raise ValueError("The AF interface must bind to 127.0.0.1 only")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("Invalid port")
        for method in ("status", "start", "stop"):
            if not callable(getattr(service, method, None)):
                raise TypeError("Service must implement status(), start(), and stop()")
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.service_lock = threading.Lock()
        self.html = HTML_PATH.read_text(encoding="utf-8")
        super().__init__((host, port), AssistRequestHandler)
        self.authority = "127.0.0.1:{}".format(self.server_address[1])
        self.origin = "http://" + self.authority
        self.url = self.origin + "/#token=" + self.token


class AssistRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FpAssist"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, format, *args):
        # Avoid writing tokens, request bodies, or camera information to logs.
        pass

    def _send(self, status, data, content_type="application/json; charset=utf-8", nonce=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        csp = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        if nonce:
            csp += "; script-src 'nonce-{}'; style-src 'nonce-{}'; connect-src 'self'".format(nonce, nonce)
        self.send_header("Content-Security-Policy", csp)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status, message):
        self._send(status, {"ok": False, "error": message})

    def _one_header(self, name):
        values = self.headers.get_all(name, [])
        return values[0] if len(values) == 1 else None

    def _host_ok(self):
        if self._one_header("Host") != self.server.authority:
            self._error(403, "Host 不符；請使用程式顯示的本機網址。")
            return False
        return True

    def _post_authorized(self):
        if not self._host_ok():
            return False
        if self._one_header("Origin") != self.server.origin:
            self._error(403, "Origin 不符；只能從本機控制頁面操作。")
            return False
        token = self._one_header("X-AF-Token")
        if token is None or not hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("utf-8")):
            self._error(403, "授權碼無效；請重新開啟程式顯示的本機網址。")
            return False
        return True

    def _read_json(self):
        if self.headers.get_all("Transfer-Encoding"):
            self._error(400, "不接受分段請求。")
            return None
        content_type = self._one_header("Content-Type")
        if content_type is None or content_type.lower().replace(" ", "") not in (
                "application/json", "application/json;charset=utf-8"):
            self._error(415, "請求必須使用 JSON。")
            return None
        raw_length = self._one_header("Content-Length")
        if raw_length is None or not raw_length.isascii() or not raw_length.isdecimal():
            self._error(411, "缺少有效的請求長度。")
            return None
        if len(raw_length) > 10 or int(raw_length) > MAX_BODY_BYTES:
            self._error(413, "請求內容過大。")
            return None
        try:
            size = int(raw_length)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Truncated body")
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON field")
                    result[key] = value
                return result
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                                 parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            if not isinstance(payload, dict):
                raise ValueError("Expected an object")
        except (ValueError, UnicodeError, OSError, RecursionError):
            self._error(400, "無效的 JSON 請求。")
            return None
        return payload

    def _service_call(self, method, **kwargs):
        try:
            with self.server.service_lock:
                result = getattr(self.server.service, method)(**kwargs)
                if not isinstance(result, dict):
                    raise TypeError("Service responses must be dictionaries")
                # Copy while locked so a service cannot later mutate this response.
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self._send(200, encoded)
        except Exception:
            self._error(500, "服務未能完成請求；請查看本機程式狀態。未自動重試任何動作。")

    def do_GET(self):
        if not self._host_ok():
            return
        # Read endpoints do not expose CORS headers and never start or stop jobs.
        if self.path == "/":
            nonce = base64.b64encode(secrets.token_bytes(18)).decode("ascii")
            html = self.server.html.replace("__CSP_NONCE__", nonce).encode("utf-8")
            self._send(200, html, "text/html; charset=utf-8", nonce)
        elif self.path == "/api/status":
            self._service_call("status")
        else:
            self._error(404, "找不到頁面。")

    def do_POST(self):
        if not self._post_authorized():
            return
        if self.path not in ("/api/start", "/api/stop"):
            self._error(404, "沒有這項操作。")
            return
        payload = self._read_json()
        if payload is None:
            return
        if self.path == "/api/start":
            if set(payload) != {"kind", "armed"} or payload.get("armed") is not True:
                self._error(422, "開始前必須明確勾選動作確認。")
                return
            if not isinstance(payload["kind"], str) or payload["kind"] not in ("assist", "native"):
                self._error(422, "不支援的對焦操作。")
                return
            self._service_call("start", kind=payload["kind"])
        else:
            if payload:
                self._error(422, "停止請求不得包含額外指令。")
                return
            self._service_call("stop")

    def _method_not_allowed(self):
        self._error(405, "不支援的 HTTP 方法。")

    do_OPTIONS = _method_not_allowed
    do_HEAD = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def make_server(service, port=0, host="127.0.0.1"):
    return AssistHTTPServer(service, port=port, host=host)


def serve(service=None, port=8765):
    service = DemoService() if service is None else service
    server = make_server(service, port=port)
    label = "離線展示，沒有操作相機" if getattr(service, "demo", False) else "本機 AF 輔助介面"
    print(label + "\n" + server.url, flush=True)
    print("請保留此終端視窗。關閉瀏覽器不代表已停止相機工作。", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        # Main owns camera shutdown and must call/await its cleanup outside this
        # HTTP layer.  A stopped web listener is not evidence of a stopped lens.
        server.server_close()
    return server


def main():
    parser = argparse.ArgumentParser(description="離線 AF 介面展示；此程式不連接相機。")
    parser.add_argument("--port", type=int, default=8765, help="本機連接埠，0 表示自動選擇")
    args = parser.parse_args()
    serve(port=args.port)


if __name__ == "__main__":
    main()
