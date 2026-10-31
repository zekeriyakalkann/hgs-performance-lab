"""Compare every stage-3 run against its pre-declared expectation.

Expectation tuple: (exit code, abort reason or None (=no marker) or '*' (=don't care),
                    validator verdict, set of HGS2_AUDIT_WARNING names, extra check name or None)
"""
import os
import re
import sys

runs = sys.argv[1]
target_hash = sys.argv[2] if len(sys.argv) > 2 else None
PASS = ("0", None, "PASS", set(), None)
E = {
    "N1": PASS, "N2": PASS, "N3": PASS, "N4": PASS, "N5": PASS,
    "A01": ("3", "wrong_database", "FAIL", set(), None),
    "A02": ("3", "production_database", "FAIL", set(), None),
    "A03": ("3", "missing_parameter expected_host", "FAIL", set(), None),
    "A04": ("3", "missing_parameter expected_port", "FAIL", set(), None),
    "A05": ("3", "missing_parameter expected_server_addr", "FAIL", set(), None),
    "A06": ("3", "missing_parameter expected_server_port", "FAIL", set(), None),
    "A07": ("3", "missing_parameter expected_system_identifier", "FAIL", set(), None),
    "A08": ("3", "client_host_mismatch", "FAIL", set(), None),
    "A09": ("3", "client_port_mismatch", "FAIL", set(), None),
    "A10": ("3", "server_addr_mismatch", "FAIL", set(), None),
    "A11": ("3", "server_port_mismatch", "FAIL", set(), None),
    "A12": ("3", "system_identifier_mismatch", "FAIL", set(), None),
    "A13": ("3", "system_identifier_unverifiable", "FAIL", set(), None),
    "A14": ("3", "superuser_connection", "FAIL", set(), None),
    "A15": ("3", "superuser_connection", "FAIL", set(), None),
    "A16": ("3", "superuser_connection", "FAIL", set(), None),
    "A17": ("0", None, "FAIL", {"superuser_allowed"}, None),
    "A17b": ("0", None, "PASS", {"superuser_allowed"}, None),
    "A18": ("3", "superuser_connection", "FAIL", set(), None),
    "A30": ("3", "superuser_membership", "FAIL", set(), None),
    "A31": ("0", None, "FAIL", {"superuser_allowed"}, None),
    "A32": ("0", None, "FAIL", {"audit_role_excess_privilege"}, None),
    "A19": ("3", "open_transaction", "FAIL", set(), None),
    "A20": ("3", "open_transaction", "FAIL", set(), None),
    "A21": ("3", "open_transaction", "FAIL", set(), None),
    "A22": ("3", "open_transaction", "FAIL", set(), None),
    "A23": ("3", "open_transaction", "FAIL", set(), None),
    "A24": ("3", "open_transaction_with_xid", "FAIL", set(), None),
    "A26": ("3", "open_transaction", "FAIL", set(), None),
    "A27": ("3", "open_transaction", "FAIL", set(), None),
    "A28": ("3", "open_transaction", "FAIL", set(), None),
    "A29": ("3", "open_transaction", "FAIL", set(), None),
    "A25": ("3", None, "FAIL", set(), "probe_error"),
    "M1": ("3", "tx_not_read_only", "FAIL", set(), None),
    "M2": ("3", "tx_not_repeatable_read", "FAIL", set(), None),
    "M3": ("3", None, "FAIL", set(), "probe_error"),
    "M4": ("0", None, "FAIL", set(), "false_success_needs_stderr_rule"),
    "M5": ("3", None, "FAIL", set(), "probe_error"),
    "M6": ("3", None, "FAIL", set(), "probe_error"),
    "M7": ("3", None, "FAIL", set(), "probe_error"),
    "E01": ("3", "missing_parameter expected_host", "FAIL", set(), None),
    "E02": ("0", "missing_parameter expected_host", "FAIL", set(), None),
    "E03": PASS, "E04": PASS, "E05": PASS, "E06": PASS, "E07": PASS, "E08": PASS, "E09": PASS,
    "E10": ("0", None, "PASS", set(), "results_in_file"),
    "E11": ("3", "server_port_mismatch", "FAIL", set(), None),
    "E12": ("3", "client_host_mismatch", "FAIL", set(), None),
    "E13": ("3", "client_host_mismatch", "FAIL", set(), None),
    "E14": ("3", None, "FAIL", set(), "no_injection"),
    "E15": ("3", "psql_too_old", "FAIL", set(), None),
    "E16": PASS,
    "E17": PASS,
    "W1": ("0", None, "FAIL", set(), "trailing_output"),
    "W2": ("0", "open_transaction", "FAIL", set(), None),   # psql: i as last line w/o CLI ON_ERROR_STOP -> exit 0
    "W3": ("3", "open_transaction", "FAIL", set(), None),   # documented CLI -v ON_ERROR_STOP=1 -> exit 3
    "W4": ("0", "client_host_mismatch", "FAIL", set(), None),
    "T1": ("0", None, "PASS", set(), "tls_t"),
    "T2": ("0", None, "PASS", set(), "tls_f"),
    "T3": ("0", None, "PASS", set(), "tls_t"),
    "T4": ("2", None, "FAIL", set(), "client_cert_reject"),
    "T5": ("2", None, "FAIL", set(), "client_name_reject"),
    "T6": ("3", "insecure_transport", "FAIL", set(), None),
    "T7": ("0", None, "FAIL", {"insecure_transport_allowed"}, None),
    "T7b": ("0", None, "PASS", {"insecure_transport_allowed"}, None),
    "T8": ("3", "insecure_transport", "FAIL", set(), None),
    "T9": ("0", None, "PASS", set(), "tls_t"),
    "T10": ("0", None, "PASS", set(), "flag_unneeded"),
    # proxy / replica
    "X1": ("0", None, "PASS", set(), "port_differ"),
    "X2": ("3", "client_port_mismatch", "FAIL", set(), None),
    "X3": ("3", "insecure_transport", "FAIL", set(), None),
    "X4": ("0", None, "PASS", set(), "tls_t"),
    "R1": ("0", None, "PASS", set(), "standby"),
    "R2": ("3", "system_identifier_mismatch", "FAIL", set(), None),
    "R3": ("3", "open_transaction", "FAIL", set(), None),
    "R4": ("3", None, "FAIL", set(), "probe_error"),
    # search_path attacks (F3 only; original/S2 comparisons are judged in the report)
    "S1": ("3", "client_host_mismatch", "FAIL", set(), None),
    "S2": ("3", "open_transaction", "FAIL", set(), None),
    "S3": ("0", None, "PASS", set(), "attack_visible_and_masked"),
    "S4": ("3", "client_host_mismatch", "FAIL", set(), None),
    "S5": ("3", "system_identifier_mismatch", "FAIL", set(), None),
    # marker forging / encoding
    "F1": PASS, "F2": PASS,
    "K1": PASS,
}
SECRETS = re.compile(r"SENTETIK-GIZLI-DEGER|SENTETIK-PAROLA-GUC|SENTETIK-PAROLA-UM|SENTETIK-TOKEN-FN|"
                     r"SENTETIK-TOKEN-POL|SENTETIK-TOKEN-AUDITROLE|sentetik-prod-host")

total = bad = 0
rows = []
for name in sorted(os.listdir(runs)):
    d = os.path.join(runs, name)
    if not os.path.isdir(d):
        continue
    code = name.split("-")[0]
    if code not in E:
        continue
    total += 1
    exp_rc, exp_reason, exp_verdict, exp_warn, extra = E[code]
    rd = lambda f: open(os.path.join(d, f), encoding="utf-8", errors="replace").read()  # noqa: E731
    rc, out, err, verdict = rd("exit.txt").strip(), rd("stdout.txt"), rd("stderr.txt"), rd("verdict.txt")
    m = re.search(r"^HGS2_AUDIT_ABORT: (\S+(?: expected_[a-z_]+)?)", out, re.M)
    reason = m.group(1) if m else None
    warns = set(re.findall(r"^HGS2_AUDIT_WARNING: (\S+)", out, re.M))
    probs = []
    if rc != exp_rc:
        probs.append(f"exit {rc}!={exp_rc}")
    if exp_reason != "*" and reason != exp_reason:
        probs.append(f"reason {reason}!={exp_reason}")
    if reason and rc == "3" and ("HGS2_AUDIT_ABORT: " + reason) not in err:
        probs.append("abort marker missing from stderr")
    if verdict.splitlines()[0] != exp_verdict:
        probs.append(f"verdict {verdict.splitlines()[0]}!={exp_verdict}")
    if warns != exp_warn:
        probs.append(f"warnings {sorted(warns)}!={sorted(exp_warn)}")
    if exp_verdict == "FAIL" and any(l == "HGS2_AUDIT_COMPLETE" for l in out.splitlines()) \
            and code not in ("A17", "A31", "A32", "M4", "W1", "T7"):
        probs.append("COMPLETE present in a failing run")
    if SECRETS.search(out) or SECRETS.search(err):
        probs.append("synthetic secret leaked")
    if target_hash and os.path.exists(os.path.join(d, "script.sha256")) and code[0] not in "MW" \
            and code not in ("A25", "E02", "E16", "R4"):   # these run mutants / wrappers / stdin
        if rd("script.sha256").strip() != target_hash:
            probs.append("script hash differs from target")
    if extra == "probe_error" and "SET TRANSACTION ISOLATION LEVEL must" not in err:
        probs.append("probe error not seen")
    if extra == "false_success_needs_stderr_rule" and "there is already a transaction in progress" not in err:
        probs.append("expected WARNING not in stderr")
    if extra == "results_in_file":
        rf = os.path.join(runs, name.replace("E10-output-to-file", "E10-results") + ".txt")
        if not (os.path.exists(rf) and "perftest_role_exists" in open(rf, encoding="utf-8").read()):
            probs.append("query results not in -o file")
        if "perftest_role_exists" in out:
            probs.append("query results leaked to stdout with -o")
    if extra == "no_injection" and "INJECTED" in out:
        probs.append("injected text executed")
    if extra == "trailing_output" and "after_include" not in out:
        probs.append("trailing command output missing")
    if extra in ("tls_t", "tls_f"):
        want = " tls= t " if extra == "tls_t" else " tls= f "
        if want not in out:
            probs.append("tls state not " + want.strip())
    if extra == "client_cert_reject" and "certificate verify failed" not in err:
        probs.append("expected certificate verification failure")
    if extra == "client_name_reject" and not re.search(r"does not match host name|server certificate for", err):
        probs.append("expected host name mismatch failure")
    if extra == "flag_unneeded" and "BILGI: allow_insecure_transport=1 verildi ama gerekmedi" not in out:
        probs.append("unneeded-flag info line missing")
    if extra == "port_differ" and "istemci portu ile sunucu portu farkli" not in out:
        probs.append("port-differ info missing")
    if extra == "standby" and "recovery= t" not in out:
        probs.append("standby not reported")
    if extra == "attack_visible_and_masked" and not re.search(r"hgs2_auditor +\|.*\| search_path +\| evil, pg_catalog +\| t", out):
        probs.append("audit-role search_path tampering not reported")
    bad += bool(probs)
    rows.append(("PASS" if not probs else "FAIL", name, rc, reason or "-", verdict.splitlines()[0],
                 ",".join(sorted(warns)) or "-", "; ".join(probs)))
for r in rows:
    print("%-4s %-46s exit=%s reason=%-44s verdict=%-4s warn=%s %s" % (r[0], r[1], r[2], r[3], r[4], r[5],
                                                                     ("<- " + r[6]) if r[6] else ""))
print(f"\nTOTAL={total} MATCH={total - bad} MISMATCH={bad}")
