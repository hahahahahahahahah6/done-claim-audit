import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from done_claim_audit.cli import main


class CLITests(unittest.TestCase):
    def call(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'transcript'
            p.write_text(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(['audit', str(p), '--repo', d, *args])
            return code, out.getvalue()

    def test_json(self):
        code, out = self.call('tests passed\nFAILED', '--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['totals_by_severity']['HIGH'], 1)

    def test_human(self):
        code, out = self.call('tests passed')
        self.assertEqual(code, 0)
        self.assertIn('PASS', out)

    def test_warn(self):
        self.assertEqual(self.call('verified')[0], 1)

    def test_fail_medium(self):
        self.assertEqual(self.call('verified', '--fail-on', 'medium')[0], 2)

    def test_ignore(self):
        code, out = self.call('verified', '--ignore', '*verified*', '--ignore', 'other', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['ignored_count'], 1)

    def test_empty(self):
        code, out = self.call('', '--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['parse_error_count'], 1)

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['audit', str(Path(d) / 'missing'), '--json']), 2)
            self.assertIn('error', json.loads(out.getvalue()))

    def test_version(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as exc:
            main(['--version'])
        self.assertEqual(exc.exception.code, 0)
        self.assertIn('0.1.0', out.getvalue())

    def test_help(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as exc:
            main(['--help'])
        self.assertEqual(exc.exception.code, 0)
        self.assertIn('audit', out.getvalue())

    def test_jsonl(self):
        code, out = self.call('{"content":[{"text":"tests passed"}]}\n{"output":"FAILED"}', '--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['findings'][0]['line'], 1)

    def test_truncation(self):
        code, out = self.call('\n'.join(['verified'] * 501))
        self.assertEqual(code, 1)
        self.assertIn('truncated', out)

    def test_json_matches_human(self):
        text = 'verified\ntests passed\nFAILED'
        human_code, human = self.call(text)
        json_code, data = self.call(text, '--json')
        report = json.loads(data)
        self.assertEqual(human_code, json_code)
        self.assertIn(report['verdict'], human)
        self.assertEqual(report['totals_by_severity'], {'HIGH': 1, 'MEDIUM': 1})
