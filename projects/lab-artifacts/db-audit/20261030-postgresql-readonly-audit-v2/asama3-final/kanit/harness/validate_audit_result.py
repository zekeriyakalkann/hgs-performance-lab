"""Reference validator for postgresql_readonly_audit_v2.sql runs.

Decides PASS/FAIL from the three independent channels psql produces. Searching a file for the word
COMPLETE is NOT sufficient; every rule below must hold for PASS.

Usage:
  python validate_audit_result.py --exit-code N --stdout STDOUT_FILE --stderr STDERR_FILE
                                  [--accept-warning NAME ...]

Rules for PASS (all required):
  1. psql exit code == 0
  2. stderr is empty (stdout and stderr must be captured SEPARATELY; never 2>&1)
  3. the last non-empty stdout line is exactly HGS2_AUDIT_COMPLETE
  4. HGS2_AUDIT_COMPLETE occurs exactly once as a whole line
  5. HGS2_AUDIT_PREFLIGHT_OK occurs exactly once as a whole line, before COMPLETE
  6. no line starts with HGS2_AUDIT_ABORT:
  7. no line starts with HGS2_AUDIT_WARNING: unless that warning name is explicitly accepted
Markers are matched only at column 0. The script pins psql's aligned output format, so query result
lines always start with a space and cannot imitate a marker.

Exit status of this tool: 0 = PASS, 1 = FAIL, 2 = usage error.
"""
import argparse
import re
import sys

COMPLETE = "HGS2_AUDIT_COMPLETE"
PREFLIGHT = "HGS2_AUDIT_PREFLIGHT_OK"
ABORT_RE = re.compile(r"^HGS2_AUDIT_ABORT: (\S+(?: \S+)?)")
WARN_RE = re.compile(r"^HGS2_AUDIT_WARNING: (\S+)")


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def validate(exit_code, out, err, accepted=()):
    lines = out.splitlines()
    non_empty = [l for l in lines if l.strip()]
    reasons = []
    aborts = [m.group(1) for l in lines for m in [ABORT_RE.match(l)] if m]
    warnings = [m.group(1) for l in lines for m in [WARN_RE.match(l)] if m]
    if exit_code != 0:
        if aborts:
            reasons.append(f"exit code {exit_code}; security abort: {aborts[0]}")
        elif exit_code == 3:
            reasons.append("exit code 3 without HGS2_AUDIT_ABORT marker "
                           "(SQL/permission error or P3 transaction probe) - audit incomplete")
        else:
            reasons.append(f"exit code {exit_code} (1=psql error, 2=connection error)")
    elif aborts:
        reasons.append(f"HGS2_AUDIT_ABORT present with exit code 0: {aborts[0]}")
    if err.strip():
        first = err.strip().splitlines()[0]
        reasons.append("stderr not empty: " + first[:160])
    if not non_empty or non_empty[-1] != COMPLETE:
        reasons.append("last non-empty stdout line is not exactly " + COMPLETE)
    n_complete = sum(1 for l in lines if l == COMPLETE)
    if n_complete != 1:
        reasons.append(f"{COMPLETE} occurs {n_complete} times (expected exactly 1)")
    pre = [i for i, l in enumerate(lines) if l == PREFLIGHT]
    comp = [i for i, l in enumerate(lines) if l == COMPLETE]
    if len(pre) != 1:
        reasons.append(f"{PREFLIGHT} occurs {len(pre)} times (expected exactly 1)")
    elif comp and pre[0] > comp[-1]:
        reasons.append(f"{PREFLIGHT} after {COMPLETE}")
    for w in warnings:
        if w not in accepted:
            reasons.append("unaccepted warning: " + w)
    return ("PASS" if not reasons else "FAIL"), reasons, aborts, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exit-code", type=int, required=True)
    ap.add_argument("--stdout", required=True)
    ap.add_argument("--stderr", required=True)
    ap.add_argument("--accept-warning", action="append", default=[])
    a = ap.parse_args()
    verdict, reasons, aborts, warnings = validate(a.exit_code, read(a.stdout), read(a.stderr),
                                                  a.accept_warning)
    print(verdict)
    for r in reasons:
        print("  - " + r)
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
