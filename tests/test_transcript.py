import tempfile
import unittest
from pathlib import Path
from done_claim_audit.transcript import parse_transcript, ParseError


class TranscriptTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'log'
            p.write_text(text)
            return parse_transcript(p)

    def test_plain(self):
        self.assertEqual(self.parse('hello\nworld'), ['hello', 'world'])

    def test_nested(self):
        self.assertEqual(self.parse('{"role":"assistant","content":[{"text":"done"}]}'), ['assistant done'])

    def test_list(self):
        self.assertEqual(self.parse('["a",1,"b",{"x":"excluded"}]'), ['a b'])

    def test_scalar(self):
        self.assertEqual(self.parse('42'), ['42'])

    def test_invalid_json(self):
        self.assertEqual(self.parse('{broken'), ['{broken'])

    def test_empty(self):
        with self.assertRaises(ParseError): self.parse('')

    def test_whitespace(self):
        with self.assertRaises(ParseError): self.parse(' \n\t')

    def test_order(self):
        self.assertEqual(self.parse('{"b":"first","a":"second"}'), ['first second'])

    def test_blank_line_number(self):
        self.assertEqual(self.parse('a\n\nb'), ['a', '', 'b'])

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(OSError): parse_transcript(Path(d) / 'absent')

    def test_empty_objects(self):
        with self.assertRaises(ParseError): self.parse('{}\n[]')

    def test_mixed(self):
        self.assertEqual(self.parse('raw\n{"x":"done"}'), ['raw', 'done'])
