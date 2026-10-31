"""Compare every recorded run against its expected outcome. Reads the run directories directly."""
import os
import re
import sys

runs = sys.argv[1]
OK = ("0", None, True)            # exit, abort reason, complete-last-line
EXPECT = {
    "N1": OK, "N2": OK, "N3": OK,
    "A01": ("3", "wrong_database", False),
    "A02": ("3", "production_database", False),
    "A03": ("3", "missing_parameter expected_host", False),
    "A04": ("3", "missing_parameter expected_port", False),
    "A05": ("3", "missing_parameter expected_server_addr", False),
    "A06": ("3", "missing_parameter expected_server_port", False),
    "A07": ("3", "missing_parameter expected_system_identifier", False),
    "A08": ("3", "client_host_mismatch", False),
    "A09": ("3", "client_port_mismatch", False),
    "A10": ("3", "server_addr_mismatch", False),
    "A11": ("3", "server_port_mismatch", False),
    "A12": ("3", "system_identifier_mismatch", False),
    "A13": ("3", "system_identifier_unverifiable", False),
    "A14": ("3", "superuser_connection", False),
    "A15": ("3", "superuser_connection", False),
    "A16": ("3", "superuser_connection", False),
    "A17": OK,
    "A18": ("3", "superuser_connection", False),
    "A19": ("3", "open_transaction", False),
    "A20": ("3", "open_transaction", False),
    "A21": ("3", "open_transaction", False),
    "A22": ("3", "open_transaction", False),
    "A23": ("3", "open_transaction", False),
    "A24": ("3", "open_transaction_with_xid", False),
    "A25": ("3", "", False),        # P3 probe error, no marker by design
    "M1": ("3", "tx_not_read_only", False),
    "M2": ("3", "tx_not_repeatable_read", False),
    "M3": ("3", "", False),         # P3 probe alone stops psql -1
    "M4": ("0", None, True),      # mutant WITHOUT P2 and probe: FALSE SUCCESS (stderr has only WARNINGs) - demonstrates need
    "M5": ("3", "", False),
    "E1": ("3", "missing_parameter expected_host", False),
    "E2": ("0", "missing_parameter expected_host", False),  # ON_ERROR_STOP forced off: \quit, no COMPLETE
    "T1": OK, "T2": OK,
    "O": None,                      # original-v2 comparisons are judged separately
}

bad = 0
total = 0
for name in sorted(os.listdir(runs)):
    d = os.path.join(runs, name)
    if not os.path.isdir(d):
        continue
    key = name.split("-")[0]
    exp = EXPECT.get(key) if key in EXPECT else EXPECT.get(key[0])
    if exp is None:
        continue
    total += 1
    rc = open(os.path.join(d, "exit.txt")).read().strip()
    out = open(os.path.join(d, "stdout.txt"), encoding="utf-8", errors="replace").read()
    err = open(os.path.join(d, "stderr.txt"), encoding="utf-8", errors="replace").read()
    lines = [l for l in out.splitlines() if l.strip()]
    complete_last = bool(lines) and lines[-1] == "HGS2_AUDIT_COMPLETE"
    complete_any = any(l == "HGS2_AUDIT_COMPLETE" for l in out.splitlines())
    m = re.search(r"^HGS2_AUDIT_ABORT: ([a-z_]+(?: expected_[a-z_]+)?)", out, re.M)
    reason = m.group(1) if m else ""
    in_err = ("HGS2_AUDIT_ABORT: " + reason) in err if reason else False
    e_rc, e_reason, e_complete = exp
    problems = []
    if rc != e_rc:
        problems.append(f"exit {rc}!={e_rc}")
    if e_reason is not None and reason != e_reason:
        problems.append(f"reason [{reason}]!=[{e_reason}]")
    if e_reason and e_rc == "3" and not in_err:
        problems.append("marker missing in stderr")
    if complete_last != e_complete or (not e_complete and complete_any):
        problems.append(f"complete_last={complete_last} complete_any={complete_any}")
    if e_rc == "0" and e_complete and err.strip() and key != "M4":
        problems.append("unexpected stderr on success")
    status = "PASS" if not problems else "FAIL"
    bad += bool(problems)
    print(f"{status} {name:38s} exit={rc} reason=[{reason or '-'}] complete_last={complete_last}"
          + ("  <- " + "; ".join(problems) if problems else ""))
print(f"\nTOTAL={total} PASS={total - bad} FAIL={bad}")
