import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from done_claim_audit.audit import audit, git_evidence


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('stable.py', 'x = 1\n')
        self.commit()
        self.write('app.py', 'x = 2\n')
        self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)

    def write(self, name, text):
        (self.repo / name).write_text(text)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def run_audit(self, text, **kwargs):
        return audit(text.splitlines(), self.repo, **kwargs)

    def test_good(self):
        self.assertEqual(self.run_audit('python -m unittest\nUpdated app.py\nAll tests pass\nDone')['exit_code'], 0)

    def test_failure_after(self):
        self.assertEqual(self.run_audit('All tests pass\nFAILED')['exit_code'], 2)

    def test_failure_before(self):
        self.assertEqual(self.run_audit('FAILED\nAll tests pass')['findings'], [])

    def test_last_pass(self):
        self.assertEqual(self.run_audit('tests passed\nFAILED\ntests passed')['exit_code'], 0)

    def test_pass_excludes_failure(self):
        self.assertEqual(self.run_audit('tests passed; previously FAILED')['exit_code'], 0)

    def test_missing(self):
        self.assertEqual(self.run_audit('fixed missing.py')['exit_code'], 2)

    def test_not_diff(self):
        self.assertEqual(self.run_audit('fixed stable.py')['exit_code'], 1)

    def test_medium_threshold(self):
        self.assertEqual(self.run_audit('fixed stable.py', fail_on='medium')['exit_code'], 2)

    def test_unstaged(self):
        self.write('stable.py', 'x = 4\n')
        self.assertEqual(self.run_audit('fixed stable.py')['exit_code'], 0)

    def test_staged(self):
        self.write('stable.py', 'x = 4\n')
        self.git('add', '.')
        self.assertEqual(self.run_audit('fixed stable.py')['exit_code'], 0)

    def test_head(self):
        self.assertEqual(self.run_audit('fixed app.py')['exit_code'], 0)

    def test_untracked(self):
        self.write('new.py', 'x = 1')
        self.assertIn('new.py', git_evidence(self.repo))

    def test_no_change(self):
        self.assertEqual(self.run_audit('no changes needed')['exit_code'], 2)

    def test_clean_empty_commit(self):
        self.git('commit', '--allow-empty', '-qm', 'empty')
        self.assertEqual(self.run_audit('no changes made')['exit_code'], 0)

    def test_todo(self):
        self.write('app.py', '# TODO later')
        self.assertEqual(self.run_audit('done')['exit_code'], 1)

    def test_fixme(self):
        self.write('app.py', '# FIXME later')
        self.assertEqual(self.run_audit('finished')['exit_code'], 1)

    def test_hack(self):
        self.write('app.py', '# HACK later')
        self.assertEqual(self.run_audit('shipped')['exit_code'], 1)

    def test_no_todo(self):
        self.assertEqual(self.run_audit('done')['exit_code'], 0)

    def test_binary(self):
        (self.repo / 'app.py').write_bytes(b'\0TODO')
        self.assertEqual(self.run_audit('done')['exit_code'], 0)

    def test_deleted(self):
        (self.repo / 'app.py').unlink()
        self.assertEqual(self.run_audit('done')['exit_code'], 0)

    def test_verified(self):
        self.assertEqual(self.run_audit('verified')['exit_code'], 1)

    def test_command(self):
        self.assertEqual(self.run_audit('verified\npytest')['exit_code'], 0)

    def test_non_git(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(['fixed missing.py', 'done', 'no changes needed', 'verified'], d)
        self.assertEqual(result['skipped_repo_check_count'], 4)
        self.assertEqual(result['totals_by_kind'], {'verified-without-verification': 1})

    def test_git_missing(self):
        with patch('done_claim_audit.audit.subprocess.run', side_effect=FileNotFoundError):
            self.assertIsNone(git_evidence(self.repo))

    def test_git_failure(self):
        with patch('done_claim_audit.audit.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'git')):
            self.assertIsNone(git_evidence(self.repo))

    def test_ignore(self):
        result = self.run_audit('fixed missing.py', ignore=['missing.*'])
        self.assertEqual((result['exit_code'], result['ignored_count']), (0, 1))

    def test_ignore_repeat_dedup(self):
        result = self.run_audit('fixed missing.py', ignore=['*', '*'])
        self.assertEqual(result['ignored_count'], 1)

    def test_dedup_todo(self):
        self.write('app.py', '# TODO\n# TODO')
        self.write('other.py', '# FIXME')
        self.assertEqual(len(self.run_audit('done')['findings']), 1)

    def test_truncation(self):
        result = self.run_audit('\n'.join('verified' for _ in range(501)))
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['findings']), 500)

    def test_hidden_high_still_fails(self):
        result = self.run_audit('\n'.join(['verified'] * 500 + ['fixed missing.py']))
        self.assertEqual(result['exit_code'], 2)

    def test_order(self):
        self.write('app.py', '# TODO')
        kinds = [f['kind'] for f in self.run_audit('verified done; fixed missing.py')['findings']]
        self.assertEqual(kinds, ['edit-claim-missing-file', 'done-with-todo-left', 'verified-without-verification'])

    def test_absolute(self):
        self.assertEqual(self.run_audit('fixed /missing.py')['findings'], [])

    def test_escape(self):
        self.assertEqual(self.run_audit('fixed ../missing.py')['findings'], [])

    def test_dot_prefix(self):
        self.assertEqual(self.run_audit('fixed ./app.py')['exit_code'], 0)

    def test_first_edit_only(self):
        self.assertEqual(self.run_audit('fixed app.py and fixed missing.py')['findings'], [])

    def test_rename_spaces(self):
        self.git('mv', 'app.py', 'new name.py')
        evidence = git_evidence(self.repo)
        self.assertIn('new name.py', evidence)
        self.assertNotIn('name.py', evidence)

    def test_nested_untracked(self):
        (self.repo / 'nested').mkdir()
        self.write('nested/x.py', 'x=1')
        self.assertIn('nested/x.py', git_evidence(self.repo))

    def test_done_in_sentence(self):
        self.write('app.py', '# TODO')
        self.assertEqual(self.run_audit('I am done with this task')['exit_code'], 1)

    def test_verification_commands(self):
        for command in ['unittest', 'npm test', 'npx foo test', 'go test', 'cargo test', 'make test', 'pnpm test', 'vitest', 'jest', 'rspec']:
            with self.subTest(command=command):
                self.assertEqual(self.run_audit('validated\n' + command)['exit_code'], 0)

    def test_failure_patterns(self):
        for text in ['AssertionError', 'ERROR: test', 'failures: 2']:
            with self.subTest(text=text):
                self.assertEqual(self.run_audit('everything is green\n' + text)['exit_code'], 2)

    def test_non_git_transcript_high(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(['tests passed', 'FAILED'], d)
        self.assertEqual(result['exit_code'], 2)
        self.assertFalse(result['git_available'])

    def test_unborn_repo(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['git', '-C', d, 'init', '-q'], check=True, capture_output=True)
            self.assertIsNone(git_evidence(d))

    def test_symlink_outside(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'outside.py'
            target.write_text('# TODO')
            (self.repo / 'link.py').symlink_to(target)
            result = self.run_audit('fixed link.py\ndone')
        self.assertEqual(result['exit_code'], 0)

    def test_exact_cap_not_truncated(self):
        result = self.run_audit('\n'.join(['verified'] * 500))
        self.assertFalse(result['truncated'])
        self.assertEqual(len(result['findings']), 500)
