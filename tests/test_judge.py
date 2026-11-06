import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import read_csv, run_script, write_csv
from cmh_judge import parse_label

MOCK = textwrap.dedent('''
    import sys
    prompt = sys.stdin.read()
    if "GARBLE" in prompt:
        print("I am not sure what you mean")
    elif "click" in prompt:
        print("TARGET.")
    else:
        print("<think>hmm</think>OTHER")
''')


class ParseLabelTests(unittest.TestCase):
    allowed = ["TARGET", "OTHER", "UNSURE"]

    def test_exact(self):
        self.assertEqual(parse_label(" target. ", self.allowed, {}), "TARGET")
        self.assertEqual(parse_label("<think>x</think>\nOTHER", self.allowed, {}), "OTHER")
        self.assertIsNone(parse_label("TARGET because...", self.allowed, {}))
        self.assertIsNone(parse_label("", self.allowed, {}))

    def test_first_line_and_aliases(self):
        self.assertEqual(parse_label("OTHER\nbecause it is a rodent", self.allowed, {}, "first_line"), "OTHER")
        self.assertEqual(parse_label("yes", self.allowed, {"yes": "TARGET"}), "TARGET")

    def test_search(self):
        self.assertEqual(parse_label("The answer is TARGET", self.allowed, {}, "search"), "TARGET")
        self.assertEqual(parse_label("TARGET, not OTHER", self.allowed, {}, "search"), "TARGET")
        self.assertIsNone(parse_label("maybe TARGET or OTHER", self.allowed, {}, "search"))
        self.assertIsNone(parse_label("TARGETED", self.allowed, {}, "search"))


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "mock_model.py").write_text(MOCK, encoding="utf-8")
        (self.dir / "prompt.txt").write_text("Definition: $definition\nPassage: $text\nAnswer:", encoding="utf-8")
        (self.dir / "judge.toml").write_text(textwrap.dedent('''
            [backend]
            type = "command"
            model = "mock-model"
            argv = ["${PYTHON}", "mock_model.py"]
            max_retries = 0
            [prompt]
            template = "prompt.txt"
            [labels]
            allowed = ["TARGET", "OTHER", "UNSURE"]
        '''), encoding="utf-8")
        write_csv(self.dir / "instances.csv", ["instance_id", "unit_id", "time", "text"], [
            ["i1", "u1", "1980", "a mouse ran across the floor"],
            ["i2", "u1", "1985", "click the mouse button"],
            ["i3", "u2", "1990", "GARBLE"],
        ])
        self.defs = write_csv(self.dir / "definitions.csv", ["unit_id", "definition", "status"], [
            ["u1", "a pointing device", "approved"], ["u2", "something else", "draft"]])

    def tearDown(self):
        self.tmp.cleanup()

    def run_judge(self, *extra):
        return run_script("cmh_judge.py", "run", "--config", self.dir / "judge.toml",
                          "--instances", self.dir / "instances.csv", "--definitions", self.defs,
                          "--ledger", self.dir / "ledger.jsonl", "--out", self.dir / "labels.csv", *extra)

    def test_unreviewed_definitions_are_refused(self):
        result = self.run_judge()
        self.assertEqual(result.returncode, 2)
        self.assertIn("review definitions", result.stderr)
        self.assertFalse((self.dir / "ledger.jsonl").exists())

    def test_run_resume_and_prompt_change(self):
        result = self.run_judge("--allow-unreviewed")
        self.assertEqual(result.returncode, 0, result.stderr)
        labels = {row["instance_id"]: row for row in read_csv(self.dir / "labels.csv")}
        self.assertEqual(labels["i1"]["label"], "OTHER")
        self.assertEqual(labels["i2"]["label"], "TARGET")
        self.assertEqual(labels["i3"]["status"], "unparsed")
        ledger = [json.loads(line) for line in (self.dir / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(len(ledger), 3)
        self.assertEqual(ledger[2]["definition_status"], "draft")
        self.assertNotIn("prompt", ledger[0])

        again = self.run_judge("--allow-unreviewed")
        self.assertIn("0 new call(s)", again.stdout)
        retry = self.run_judge("--allow-unreviewed", "--retry-unparsed")
        self.assertIn("1 new call(s)", retry.stdout)

        (self.dir / "prompt.txt").write_text("Changed. $definition / $text", encoding="utf-8")
        changed = self.run_judge("--allow-unreviewed")
        self.assertIn("3 new call(s)", changed.stdout)
        summary = run_script("cmh_judge.py", "summary", "--ledger", self.dir / "ledger.jsonl")
        self.assertIn("2 prompt versions", summary.stdout)

    def test_protocol_lock_blocks_changed_files(self):
        lock = self.dir / "protocol.lock.json"
        frozen = run_script("cmh_protocol.py", "freeze", "--files", self.dir / "judge.toml",
                            self.dir / "prompt.txt", self.defs, "--out", lock)
        self.assertEqual(frozen.returncode, 0, frozen.stderr)
        ok = self.run_judge("--allow-unreviewed", "--protocol-lock", lock)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        (self.dir / "prompt.txt").write_text("edited after freezing $definition $text", encoding="utf-8")
        blocked = self.run_judge("--allow-unreviewed", "--protocol-lock", lock)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("changed since it was frozen", blocked.stderr)

    def test_missing_template_variable(self):
        (self.dir / "prompt.txt").write_text("$definition $nope", encoding="utf-8")
        result = self.run_judge("--allow-unreviewed")
        self.assertEqual(result.returncode, 2)
        self.assertIn("$nope", result.stderr)


class ProtocolTests(unittest.TestCase):
    def test_freeze_verify_amend(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rules.toml")
            path.write_text("a = 1\n", encoding="utf-8")
            lock = Path(tmp, "lock.json")
            self.assertEqual(run_script("cmh_protocol.py", "freeze", "--files", path, "--out", lock).returncode, 0)
            self.assertEqual(run_script("cmh_protocol.py", "verify", "--lock", lock).returncode, 0)
            path.write_text("a = 2\n", encoding="utf-8")
            failed = run_script("cmh_protocol.py", "verify", "--lock", lock)
            self.assertEqual(failed.returncode, 1)
            self.assertIn("changed since freeze", failed.stdout)
            refused = run_script("cmh_protocol.py", "freeze", "--files", path, "--out", lock)
            self.assertEqual(refused.returncode, 2)
            amended = run_script("cmh_protocol.py", "freeze", "--files", path, "--out", lock, "--force",
                                 "--reason", "fixed a typo before any run")
            self.assertEqual(amended.returncode, 0, amended.stderr)
            self.assertIn("fixed a typo", lock.read_text())

    def test_files_outside_lock_folder_refused(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            outside = Path(other, "x.txt")
            outside.write_text("x", encoding="utf-8")
            result = run_script("cmh_protocol.py", "freeze", "--files", outside, "--out", Path(tmp, "lock.json"))
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()


class HttpBackendTests(unittest.TestCase):
    """The openai_compatible backend against a throwaway local server."""

    def test_retry_and_auth_header(self):
        import http.server
        import os
        import threading

        seen = {"calls": 0, "auth": None, "body": None}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                seen["calls"] += 1
                length = int(self.headers.get("Content-Length", 0))
                seen["body"] = json.loads(self.rfile.read(length))
                seen["auth"] = self.headers.get("Authorization")
                if seen["calls"] == 1:
                    self.send_response(500)
                    self.end_headers()
                    return
                payload = json.dumps({"choices": [{"message": {"content": "TARGET"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / "prompt.txt").write_text("Passage: $text", encoding="utf-8")
                (d / "judge.toml").write_text(textwrap.dedent(f'''
                    [backend]
                    type = "openai_compatible"
                    model = "test-model"
                    base_url = "http://127.0.0.1:{server.server_address[1]}/v1"
                    api_key_env = "CMH_TEST_KEY"
                    max_retries = 1
                    extra_body = {{ seed = 1 }}
                    [prompt]
                    template = "prompt.txt"
                    [labels]
                    allowed = ["TARGET", "OTHER"]
                '''), encoding="utf-8")
                write_csv(d / "instances.csv", ["instance_id", "unit_id", "text"], [["i1", "u1", "hello"]])
                import subprocess
                import sys
                from helpers import SCRIPTS
                env = dict(os.environ, CMH_TEST_KEY="secret-value")
                result = subprocess.run([sys.executable, str(SCRIPTS / "cmh_judge.py"), "run", "--config",
                                         str(d / "judge.toml"), "--instances", str(d / "instances.csv"),
                                         "--ledger", str(d / "ledger.jsonl"), "--out", str(d / "labels.csv")],
                                        capture_output=True, text=True, env=env, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(read_csv(d / "labels.csv")[0]["label"], "TARGET")
                self.assertEqual(seen["calls"], 2)
                self.assertEqual(seen["auth"], "Bearer secret-value")
                self.assertEqual(seen["body"]["temperature"], 0)
                self.assertEqual(seen["body"]["seed"], 1)
                self.assertNotIn("secret-value", (d / "ledger.jsonl").read_text())
        finally:
            server.shutdown()
            server.server_close()


class PromptFilesAndDryRunTests(unittest.TestCase):
    def test_codebook_file_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "codebook.md").write_text("ECON = economy\nSEC = security", encoding="utf-8")
            (d / "prompt.txt").write_text("Codebook:\n$codebook\nDocument: $text\nAnswer:", encoding="utf-8")
            (d / "mock.py").write_text("import sys\nprint('ECON' if 'trade' in sys.stdin.read() else 'SEC')\n",
                                       encoding="utf-8")
            (d / "coder.toml").write_text(textwrap.dedent('''
                [backend]
                type = "command"
                model = "mock-coder"
                argv = ["${PYTHON}", "mock.py"]
                [prompt]
                template = "prompt.txt"
                [prompt.files]
                codebook = "codebook.md"
                [labels]
                allowed = ["ECON", "SEC", "UNCLEAR"]
            '''), encoding="utf-8")
            write_csv(d / "docs.csv", ["instance_id", "unit_id", "text"],
                      [["d1", "s1", "a speech about trade"], ["d2", "s1", "a speech about defence"]])
            dry = run_script("cmh_judge.py", "dry-run", "--config", d / "coder.toml", "--instances", d / "docs.csv",
                             "--n", "1")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("ECON = economy", dry.stdout)
            run = run_script("cmh_judge.py", "run", "--config", d / "coder.toml", "--instances", d / "docs.csv",
                             "--ledger", d / "ledger.jsonl", "--out", d / "labels.csv")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual([r["label"] for r in read_csv(d / "labels.csv")], ["ECON", "SEC"])
            (d / "codebook.md").write_text("ECON = economy and trade\nSEC = security", encoding="utf-8")
            again = run_script("cmh_judge.py", "run", "--config", d / "coder.toml", "--instances", d / "docs.csv",
                               "--ledger", d / "ledger.jsonl", "--out", d / "labels.csv")
            self.assertIn("2 new call(s)", again.stdout)  # a changed codebook is a new prompt version


class RedirectTests(unittest.TestCase):
    def test_redirect_is_refused(self):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:9/elsewhere")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / "p.txt").write_text("$text", encoding="utf-8")
                (d / "j.toml").write_text(textwrap.dedent(f'''
                    [backend]
                    type = "openai_compatible"
                    model = "m"
                    base_url = "http://127.0.0.1:{server.server_address[1]}/v1"
                    max_retries = 0
                    [prompt]
                    template = "p.txt"
                    [labels]
                    allowed = ["A"]
                '''), encoding="utf-8")
                write_csv(d / "i.csv", ["instance_id", "unit_id", "text"], [["i1", "u1", "x"]])
                result = run_script("cmh_judge.py", "run", "--config", d / "j.toml", "--instances", d / "i.csv",
                                    "--ledger", d / "l.jsonl", "--out", d / "o.csv")
                self.assertEqual(result.returncode, 2)
                self.assertIn("redirect", result.stderr)
        finally:
            server.shutdown()
            server.server_close()
