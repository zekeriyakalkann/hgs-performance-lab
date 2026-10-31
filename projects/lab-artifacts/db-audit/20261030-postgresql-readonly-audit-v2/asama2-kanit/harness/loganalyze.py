"""Analyse server logs (log_statement=all) for every audit session, identified by application_name.

Checks:
  1. Every statement sent by the audit script starts with an allowed read-only keyword.
  2. In runs that stopped on an error, no statement was executed after the first ERROR.
Statements injected by the test harness itself (-c BEGIN, -c SAVEPOINT, psql -1 BEGIN/COMMIT) are
reported separately and are not attributed to the script.
"""
import collections
import re
import sys

S = sys.argv[1]
ALLOWED = {"SELECT", "WITH", "BEGIN", "SET", "SHOW", "ROLLBACK"}
HARNESS = {"A21": {"BEGIN"}, "A22": {"BEGIN"}, "A23": {"BEGIN"}, "A24": {"BEGIN"},
           "A25": {"BEGIN", "SAVEPOINT"}, "M5": {"BEGIN"}}
line_re = re.compile(r"^\S+ \S+ \S+ \[(\d+)\] user=(\S*) db=(\S*) app=(\S*) (LOG|ERROR|WARNING|FATAL|STATEMENT):\s+(.*)$")
run_re = re.compile(r"^(N\d|A\d\d|M\d|E\d|T\d|O\d+)-")

events = collections.defaultdict(list)   # app -> [(kind, text)]
for v in ("12", "16", "17", "18"):
    with open(f"{S}/c{v}.log", encoding="utf-8", errors="replace") as f:
        for raw in f:
            m = line_re.match(raw.rstrip("\n"))
            if not m:
                continue
            pid, user, db, app, level, msg = m.groups()
            if not run_re.match(app):
                continue
            key = f"{app}@pg{v}:{pid}"
            if level == "LOG" and msg.startswith("statement: "):
                events[key].append(("stmt", msg[len("statement: "):]))
            elif level in ("ERROR", "FATAL"):
                events[key].append(("error", msg))

kinds = collections.Counter()
violations = []
after_error = []
harness_stmts = collections.Counter()
sessions = 0
for key, evs in sorted(events.items()):
    sessions += 1
    app = key.split("@")[0]
    rid = run_re.match(app).group(1)
    seen_error = False
    for kind, text in evs:
        if kind == "error":
            seen_error = True
            continue
        word = text.split(None, 1)[0].upper().rstrip(";") if text.strip() else ""
        if seen_error:
            after_error.append((key, text[:80]))
        if word in HARNESS.get(rid, set()) and not text.startswith("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ"):
            harness_stmts[(rid, word)] += 1
            continue
        if text in ("BEGIN", "COMMIT") and app.split("-")[1:2] and "psql-1" in app:
            harness_stmts[(rid, "psql -1 " + text)] += 1
            continue
        kinds[word] += 1
        if word not in ALLOWED:
            violations.append((key, text[:100]))

print("audit sessions analysed:", sessions)
print("statement kinds sent by the script:", dict(kinds))
print("harness-injected statements (not from the script):", dict(harness_stmts))
print("NON-ALLOWED statements:", len(violations))
for v in violations[:20]:
    print("   ", v)
print("statements executed AFTER an error in the same session:", len(after_error))
for a in after_error:
    print("   ", a)
