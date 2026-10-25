"""Deterministic pattern checks; git is the only executed program."""
import fnmatch
import re
import subprocess
from collections import Counter
from pathlib import Path


def pattern(text):
    return re.compile(text, re.I)


PASS = pattern(r"\b(all tests pass|tests passed|all .* tests passing|everything is green|all green)\b")
FAIL = pattern(r"\b(FAILED|failed|AssertionError|test(s)? failed|ERROR: test|failures?:\s*[1-9])\b")
EDIT = pattern(r"\b(fixed|updated|changed|patched|modified|edited)\s+(?:the\s+|a\s+)?([A-Za-z0-9_./-]+\.(py|js|ts|tsx|jsx|md|json|yaml|yml|toml|go|rs|sh|css|html|txt))\b")
NO_CHANGE = pattern(r"\b(no (changes|edits|modifications) (needed|required|made|necessary))\b")
DONE = pattern(r"\b(done|complete|completed|finished|shipped|all done)\b")
VERIFIED = pattern(r"\b(verified|confirmed|validated)\b")
COMMAND = pattern(r"\b(pytest|unittest|npm test|npx .*test|go test|cargo test|make test|pnpm test|vitest|jest|rspec)\b")


def git_evidence(repo):
    repo = Path(repo)
    if not (repo / ".git").exists():
        return None
    def run(*args):
        return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    try:
        diff = run("diff", "--name-only", "-z")
        status = run("status", "--porcelain=v1", "-z", "--untracked-files=all")
        head = run("show", "--pretty=format:", "--name-only", "-z", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        return None
    decode = lambda b: b.decode("utf-8", errors="surrogateescape")
    evidence = {decode(p) for p in diff.split(b"\0") + head.split(b"\0") if p}
    entries = iter(status.split(b"\0"))
    for entry in entries:
        if not entry:
            continue
        evidence.add(decode(entry[3:]))
        if b"R" in entry[:2] or b"C" in entry[:2]:
            next(entries, None)  # -z puts the destination first, then the source
    return evidence


def contained(repo, token):
    path = Path(token)
    if path.is_absolute():
        return None
    try:
        resolved = (repo / path).resolve()
        resolved.relative_to(repo.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


def audit(lines, repo, ignore=(), fail_on="high"):
    repo = Path(repo)
    evidence = git_evidence(repo)
    passing = [i for i, line in enumerate(lines) if PASS.search(line)]
    failures = [i for i, line in enumerate(lines) if not PASS.search(line) and FAIL.search(line)]
    commands = any(COMMAND.search(line) for line in lines)
    todos = []
    if evidence is not None and any(DONE.search(line) for line in lines):
        for token in sorted(evidence):
            path = contained(repo, token)
            if path is None or not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if b"\0" not in data and re.search(r"TODO|FIXME|HACK", data.decode("utf-8", errors="ignore")):
                todos.append(token)
    findings, seen = [], set()
    ignored = 0
    truncated = False
    skipped = Counter()
    def add(number, kind, claim, severity, detail):
        nonlocal ignored, truncated
        key = (number, kind, claim)
        if key in seen:
            return
        seen.add(key)
        if any(fnmatch.fnmatchcase(claim, glob) for glob in ignore):
            ignored += 1
        elif len(findings) < 500:
            findings.append(dict(line=number, kind=kind, claim=claim, severity=severity, detail=detail))
        else:
            truncated = True
    for i, line in enumerate(lines):
        number = i + 1
        if passing and failures and i == passing[-1] and failures[-1] > i:
            add(number, "test-claim-contradicted", line, "HIGH", "Failure signal after last passing claim at line %s" % (failures[-1] + 1))
        edit = EDIT.search(line)
        if edit:
            token = edit.group(2)
            path = contained(repo, token)
            if path is not None:
                token = Path(token).as_posix()
                if evidence is None:
                    skipped["edit-claim-missing-file"] += 1
                    skipped["edit-claim-not-in-diff"] += 1
                elif not path.exists():
                    add(number, "edit-claim-missing-file", token, "HIGH", "Claimed file does not exist under repo root")
                elif token not in evidence:
                    add(number, "edit-claim-not-in-diff", token, "MEDIUM", "File absent from diff, status and HEAD evidence")
        if NO_CHANGE.search(line):
            if evidence is None:
                skipped["no-change-claim-contradicted"] += 1
            elif evidence:
                add(number, "no-change-claim-contradicted", line, "HIGH", "Git evidence contains changed files")
        if DONE.search(line):
            if evidence is None:
                skipped["done-with-todo-left"] += 1
            elif todos:
                add(number, "done-with-todo-left", line, "MEDIUM", "TODO/FIXME/HACK in: " + ", ".join(todos))
        if VERIFIED.search(line) and not commands:
            add(number, "verified-without-verification", line, "MEDIUM", "No verification command appears in transcript")
    severity = Counter(f["severity"] for f in findings)
    blocked = severity["HIGH"] or (fail_on == "medium" and severity["MEDIUM"])
    # Track threshold hits beyond the cap too, so truncation cannot hide a HIGH.
    for number, kind, claim in seen:
        if any(fnmatch.fnmatchcase(claim, glob) for glob in ignore):
            continue
        if kind in {"test-claim-contradicted", "edit-claim-missing-file", "no-change-claim-contradicted"} or fail_on == "medium":
            blocked = True
    code = 2 if blocked else (1 if findings or truncated else 0)
    return dict(transcript_lines=len(lines), git_evidence_count=len(evidence or ()),
                git_available=evidence is not None, skipped_repo_checks=dict(skipped),
                skipped_repo_check_count=sum(skipped.values()), findings=findings,
                totals_by_kind=dict(Counter(f["kind"] for f in findings)),
                totals_by_severity={s: severity[s] for s in ("HIGH", "MEDIUM")},
                ignored_count=ignored, parse_error_count=0, truncated=truncated,
                verdict={0: "PASS", 1: "WARN", 2: "FAIL"}[code], exit_code=code)
