# done-claim-audit

An offline, deterministic, stdlib-only Python CLI that audits an agent's completion
claims against a finished transcript and git state on disk. No LLM, network, keys,
project code execution, or test/build command execution. Git is its only subprocess.
Python 3.9+ is required; setuptools and wheel are build-time requirements only.

Install a locally built wheel with `python -m pip install dist/done_claim_audit-0.1.0-py3-none-any.whl`.

## Transcript formats

Accepts plain text and JSONL, including mixed files. Each physical input line is one
logical line, numbered from 1. For JSON objects, string values are recursively
collected in document order and joined with spaces. For top-level arrays, only
string items are joined. Other JSON values and malformed JSON use the raw line.
Empty or whitespace-only transcripts are parse errors, never a silent PASS.

## Checks and severities

| Kind | Severity | Trigger |
| --- | --- | --- |
| test-claim-contradicted | HIGH | Last failure signal comes after the last passing claim |
| edit-claim-missing-file | HIGH | Claimed relative file does not exist |
| edit-claim-not-in-diff | MEDIUM | Claimed file exists but is absent from git evidence |
| no-change-claim-contradicted | HIGH | No-change claim with nonempty git evidence |
| done-with-todo-left | MEDIUM | Done claim and TODO, FIXME, or HACK in an evidence file |
| verified-without-verification | MEDIUM | Verified claim without any verification command in transcript |

Matching is heuristic and case-insensitive for claims. Passing phrases are
`all tests pass`, `tests passed`, `all .* tests passing`, `everything is green`,
and `all green`. Failures include `FAILED`, `failed`, `AssertionError`,
`tests failed`, `ERROR: test`, and `failures: N` for positive N. A passing line is
excluded from failure signals.

Edit verbs are fixed, updated, changed, patched, modified, and edited, optionally
followed by “the” or “a”, then a path with a recognized source/text extension
(py, js, ts, tsx, jsx, md, json, yaml, yml, toml, go, rs, sh, css, html, txt).
Only the first edit path per line counts. Leading `./` is stripped; absolute paths
and paths resolving outside the repo are skipped.

No-change phrases use “no changes/edits/modifications” followed by
“needed/required/made/necessary”. Done triggers include done, complete, completed,
finished, shipped, and all done. A bare “done” inside a longer sentence counts.
Verified/confirmed/validated requires a command mention anywhere: pytest,
unittest, npm test, npx …test, go test, cargo test, make test, pnpm test,
vitest, jest, or rspec. A command mention does not establish that it ran.

Git evidence is the union of unstaged diff, porcelain status (including staged
and untracked files; rename destinations), and files from the HEAD commit.
A `.git` entry is required. Missing git or any failed git command causes all
applicable repo checks to be skipped and counted, while transcript checks run.
This includes repositories with no HEAD commit. Binary files containing a null
byte are skipped for TODO scanning; unreadable files are ignored.

Findings are deduplicated by (line, kind, claim), ordered by transcript line then
check order, and capped at 500. Reports note truncation; kind/severity totals
count retained findings. Exit status still accounts for findings beyond the cap.
Repeatable `--ignore` globs match the claim (file path for edits, whole logical
line for other checks); excluded findings are counted once each.

## Usage and exit codes

```text
done-claim-audit audit TRANSCRIPT [--repo PATH] [--json] [--fail-on high|medium] [--ignore GLOB ...]
done-claim-audit --version
done-claim-audit --help
```

Repeat the flag for multiple patterns: `--ignore '*.md' --ignore '*confirmed*'`.
Repo defaults to the current directory. Human and JSON reports include transcript
line count, git evidence count, skipped repo checks, findings with line/kind/claim/
severity/detail, kind and severity totals, ignored count, parse-error count, and
verdict. Human findings use `transcript:line` locations.

| Exit | Verdict | Meaning |
| --- | --- | --- |
| 0 | PASS | No findings |
| 1 | WARN | Findings exist, all below the fail threshold |
| 2 | FAIL | Finding at or above threshold, or input/parse error |

Default threshold is HIGH; `--fail-on medium` makes any finding fail. Argument
errors also exit 2. PASS describes only these configured checks.

## Examples

Prepare a local fixture so the good example has the required repo evidence.
Use a new empty temporary directory; the git configuration below is repo-local.
The auditor itself does not run tests; the example transcript records a command.
Run these commands from this project's root:

```sh
fixture=$(mktemp -d)
git -C "$fixture" init -q
git -C "$fixture" config user.name Fixture
git -C "$fixture" config user.email fixture@example.invalid
printf 'x = 1\n' > "$fixture/app.py"
git -C "$fixture" add app.py
git -C "$fixture" commit -qm fixture
done-claim-audit audit examples/good-transcript.txt --repo "$fixture"
# PASS: 5 lines; 1 git evidence files; 0 skipped repo checks
# Kinds: {}; severities: {'HIGH': 0, 'MEDIUM': 0}; ignored: 0; parse errors: 0
# exit 0

done-claim-audit audit examples/bad-transcript.txt --repo "$fixture"
# FAIL: 5 lines; 1 git evidence files; 0 skipped repo checks
# line 1: HIGH test-claim-contradicted (failure at line 2)
# line 3: HIGH edit-claim-missing-file: missing.py
# line 4: HIGH no-change-claim-contradicted
# Kinds: one of each above; severities: HIGH 3, MEDIUM 0
# ignored: 0; parse errors: 0; exit 2

done-claim-audit audit examples/bad-transcript.txt --repo "$fixture" --json
```

Alternatively, run the good example inside a git repo with `app.py` changed or
in its HEAD commit, or point `--repo` at an equivalent prepared fixture.

## Honest limitations

This is pattern matching, not semantic judgement. A finding means “check this
claim”, not “the agent lied”. Paraphrased claims are not checked. Speaker roles
are not interpreted: user quotations, command output, and assistant text can all
match. Bare “done” inside a longer sentence still counts.

It executes nothing in the project, so it cannot establish that tests actually
passed; it only catches claims contradicted by the transcript or repo evidence,
or lacking the specific evidence described above. Git evidence is uncommitted
diff + status + HEAD commit only; older history is not scanned. A TODO in a
changed file may be pre-existing, rather than introduced by this session. The
current repo may differ from its state during the recorded session. Missing git
evidence skips checks and must not be interpreted as a successful verification.

## Differentiation

- **compact-audit** audits a summary against its transcript; this audits completion
  claims against transcript + repo evidence.
- **agent-guard** blocks bad behaviour at runtime; this is a post-hoc auditor that
  runs on a finished transcript, with no hooks.
- **session-handover** distils a session for the next session; this verifies the
  previous session's claims using the limited checks described here.
- **DoneAudit** is a Node tool that installs a completion rule and EXECUTES
  test/build/lint checks live with a trust score. This is stdlib Python, offline,
  executes nothing in the project, and audits a finished transcript against git
  state: no score, no repo installation, no Action. Installing this CLI does not
  install any completion rule in a repo.
- **Heavy runtimes:** this is an offline stdlib CLI, with no daemon, no LLM,
  and no network.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m build --no-isolation
```

The build uses the standard setuptools backend. `--no-isolation` uses already
installed setuptools and wheel for offline builds. Distribution artifacts belong
in local `dist/` (ignored by git); do not commit them, egg-info, internal drafts,
`.env`, or `dev.db`. MIT licensed.
