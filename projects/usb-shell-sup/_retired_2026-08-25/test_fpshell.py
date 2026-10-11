#!/usr/bin/env python3
import concurrent.futures
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parent


class FPShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="fpshell-test-")
        self.socket = pathlib.Path(self.temp.name) / "fpshell.sock"
        env = os.environ.copy()
        env["FPSHELL_SOCKET"] = str(self.socket)
        self.env = env
        self.daemon = subprocess.Popen(
            [str(ROOT / "fpshelld"), "--mock", "--limit", "4"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5
        while not self.socket.exists() and time.monotonic() < deadline:
            if self.daemon.poll() is not None:
                self.fail(self.daemon.stderr.read())
            time.sleep(0.02)
        self.assertTrue(self.socket.exists())

    def tearDown(self) -> None:
        if self.daemon.poll() is None:
            subprocess.run(
                [str(ROOT / "fpshell"), "quit"], env=self.env, check=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        self.daemon.communicate(timeout=5)
        self.temp.cleanup()

    def client(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "fpshell"), *args], env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_status_info_and_socket_permissions(self) -> None:
        status_result = self.client("status")
        self.assertEqual(status_result.returncode, 0)
        self.assertIn("backend=mock", status_result.stdout)
        self.assertIn("inter_wait_ms=0", status_result.stdout)
        self.assertIn("protocol=1", status_result.stdout)
        self.assertIn("frame=64", self.client("info").stdout)
        mode = stat.S_IMODE(self.socket.stat().st_mode)
        self.assertEqual(mode, 0o600)

        json_status = self.client("--json", "status")
        self.assertEqual(json_status.returncode, 0)
        document = json.loads(json_status.stdout)
        self.assertTrue(document["ok"])
        self.assertEqual(document["request"], "STATUS")

    def test_four_parallel_clients_keep_identity(self) -> None:
        names = ["agent-A", "agent-B", "agent-C", "agent-D"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda name: self.client("echo", name), names))
        self.assertTrue(all(result.returncode == 0 for result in results))
        combined = "".join(result.stdout for result in results)
        for name in names:
            self.assertIn(f"payload={name}", combined)
        for sequence in range(4):
            self.assertIn(f"sequence={sequence}", combined)
        self.assertIn("used=4", self.client("status").stdout)
        limited = self.client("ping")
        self.assertEqual(limited.returncode, 1)
        self.assertIn("session-limit", limited.stdout)

    def test_ping_and_payload_limit(self) -> None:
        ping = self.client("ping")
        self.assertEqual(ping.returncode, 0)
        self.assertIn("command=ping payload=PING", ping.stdout)
        oversized = self.client("echo", "x" * 45)
        self.assertEqual(oversized.returncode, 2)
        self.assertIn("44 UTF-8 bytes", oversized.stderr)
        self.assertIn("used=1", self.client("status").stdout)

        oversized_utf8 = self.client("echo", "測" * 15)
        self.assertEqual(oversized_utf8.returncode, 2)
        self.assertIn("44 UTF-8 bytes", oversized_utf8.stderr)

        multiline = self.client("echo", "line1\nline2")
        self.assertEqual(multiline.returncode, 2)
        self.assertIn("NUL, CR, or LF", multiline.stderr)

    def test_json_connection_error(self) -> None:
        missing = pathlib.Path(self.temp.name) / "missing.sock"
        result = subprocess.run(
            [str(ROOT / "fpshell"), "--socket", str(missing), "--json", "status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 2)
        document = json.loads(result.stdout)
        self.assertFalse(document["ok"])
        self.assertIn("error", document)

    def test_second_daemon_cannot_replace_live_socket(self) -> None:
        second = subprocess.run(
            [str(ROOT / "fpshelld"), "--mock", "--socket", str(self.socket)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        self.assertEqual(second.returncode, 2)
        self.assertIn("daemon lock unavailable", second.stderr)
        self.assertEqual(self.client("status").returncode, 0)


class FPShellControlTests(unittest.TestCase):
    def test_background_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fpshell-ctl-") as directory:
            socket_path = pathlib.Path(directory) / "service.sock"
            base = [str(ROOT / "fpshellctl"), "--socket", str(socket_path), "--json"]
            started = subprocess.run(
                [*base, "start", "--mock", "--arm-wait", "0", "--limit", "2", "--wait", "5"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            document = json.loads(started.stdout)
            self.assertTrue(document["ok"])
            self.assertIn("backend=mock", document["response"])

            client = subprocess.run(
                [str(ROOT / "fpshell"), "--socket", str(socket_path), "echo", "managed"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
            )
            self.assertEqual(client.returncode, 0)
            self.assertIn("payload=managed", client.stdout)

            stopped = subprocess.run(
                [*base, "stop", "--wait", "5"], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
            self.assertFalse(socket_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
