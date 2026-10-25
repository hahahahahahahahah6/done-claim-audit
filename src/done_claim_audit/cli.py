"""Command line interface."""
import argparse
import json
from pathlib import Path
from . import __version__
from .audit import audit
from .transcript import ParseError, parse_transcript


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline completion claim audit (heuristic; executes no project code)")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("audit")
    cmd.add_argument("transcript")
    cmd.add_argument("--repo", default=".")
    cmd.add_argument("--json", action="store_true")
    cmd.add_argument("--fail-on", choices=("high", "medium"), default="high")
    cmd.add_argument("--ignore", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        lines = parse_transcript(args.transcript)
    except (OSError, ParseError) as exc:
        report = dict(transcript_lines=0, git_evidence_count=0, skipped_repo_checks={},
                      skipped_repo_check_count=0, findings=[], totals_by_kind={},
                      totals_by_severity={"HIGH": 0, "MEDIUM": 0}, ignored_count=0,
                      parse_error_count=1, truncated=False, verdict="FAIL", exit_code=2,
                      error=str(exc))
    else:
        report = audit(lines, Path(args.repo), args.ignore, args.fail_on)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("%s: %s lines; %s git evidence files; %s skipped repo checks" %
              (report["verdict"], report["transcript_lines"], report["git_evidence_count"], report["skipped_repo_check_count"]))
        for f in report["findings"]:
            print("%s:%s: %s %s: %s — %s" % (args.transcript, f["line"], f["severity"], f["kind"], f["claim"], f["detail"]))
        print("Kinds: %s; severities: %s; ignored: %s; parse errors: %s" %
              (report["totals_by_kind"], report["totals_by_severity"], report["ignored_count"], report["parse_error_count"]))
        if report["truncated"]:
            print("Findings truncated at 500; totals count retained findings.")
        if "error" in report:
            print("Error: " + report["error"])
    return report["exit_code"]
