"""Stage-3 server-log analysis (log_statement=all) restricted to the final-round sessions.

Every statement of every final-round session (identified by application_name = run id) is classified:
  script   : SELECT/WITH, or one of the exact non-SELECT statements the audit script may send
  harness  : statements injected by the test harness (-c ..., psql -1 BEGIN/COMMIT/ROLLBACK, wrappers)
  mutant   : statements that exist only in deliberately mutated copies (READ WRITE / SERIALIZABLE probe)
  VIOLATION: anything else
Also reports statements executed after the first ERROR of a session.
"""
import collections
import os
import re
import sys

S, runs = sys.argv[1], sys.argv[2]
final_ids = {n for n in os.listdir(runs) if os.path.isdir(os.path.join(runs, n))}
SCRIPT_EXACT = {
    "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;",
    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED;",
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;",
    "SET LOCAL search_path = pg_catalog, pg_temp;",
    "SHOW transaction_read_only;",
    "ROLLBACK;",
    "set client_encoding to 'UTF8'",
}
SCRIPT_PREFIX = ("SET LOCAL statement_timeout = '", "SET LOCAL lock_timeout = '")
HARNESS_EXACT = {
    "BEGIN", "BEGIN;", "COMMIT", "ROLLBACK", "BEGIN READ ONLY", "BEGIN READ WRITE",
    "BEGIN ISOLATION LEVEL REPEATABLE READ", "BEGIN ISOLATION LEVEL SERIALIZABLE",
    "BEGIN ISOLATION LEVEL READ COMMITTED", "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
    "BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY", "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY",
    "SELECT txid_current() > 0 AS xid_assigned", "SAVEPOINT s1", "SELECT 1 AS prior_query",
    "BEGIN; SELECT 1 AS same_message", "SELECT 'after_include' AS trailing_command;",
}
MUTANT_EXACT = {"BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE;",
                "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;"}
# the original v1/v2 scripts (O* comparison runs) send their own statements; only checked for kind
line_re = re.compile(r"^\S+ \S+ \S+ \[(\d+)\] user=(\S*) db=(\S*) app=(\S*) (LOG|ERROR|WARNING|FATAL|STATEMENT|DETAIL|HINT):\s+(.*)$")
logs = [f"{S}/c{v}.log" for v in ("12", "16", "17", "18")] + [f"{S}/r{v}.log" for v in ("12", "18")]

sessions = collections.OrderedDict()
cur = None
for path in logs:
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            m = line_re.match(raw)
            if not m:
                if cur is not None and raw.startswith("\t") and sessions[cur] and sessions[cur][-1][0] == "stmt":
                    k, t = sessions[cur][-1]
                    sessions[cur][-1] = (k, t + "\n" + raw[1:])
                else:
                    cur = None
                continue
            pid, user, db, app, level, msg = m.groups()
            if app not in final_ids:
                cur = None
                continue
            cur = (os.path.basename(path), pid, app)
            sessions.setdefault(cur, [])
            if level == "LOG" and msg.startswith("statement: "):
                sessions[cur].append(("stmt", msg[len("statement: "):]))
            elif level in ("ERROR", "FATAL"):
                sessions[cur].append(("error", msg))
            else:
                cur = None if level != "LOG" else cur

classes = collections.Counter()
script_nonselect = collections.Counter()
harness = collections.Counter()
violations, after_error = [], []
apps_seen = set()
for (log, pid, app), evs in sessions.items():
    apps_seen.add(app)
    is_comparison = app.startswith("O")
    err_seen = False
    for kind, text in evs:
        if kind == "error":
            err_seen = True
            continue
        first = text.lstrip().split(None, 1)[0].upper().rstrip(";") if text.strip() else ""
        if text in HARNESS_EXACT:
            cls = "harness"
            harness[text] += 1
        elif text in MUTANT_EXACT:
            cls = "mutant"
        elif first in ("SELECT", "WITH"):
            cls = "script-select"
        elif text in SCRIPT_EXACT or text.startswith(SCRIPT_PREFIX):
            cls = "script-control"
            script_nonselect[re.sub(r"= '.*';$", "= '<value>';", text)] += 1
        elif is_comparison and first in ("BEGIN", "SET", "SHOW", "ROLLBACK"):
            cls = "comparison-script-control"
        else:
            cls = "VIOLATION"
            violations.append((app, text[:120]))
        classes[cls] += 1
        if err_seen and cls != "harness":
            after_error.append((app, text[:100]))
        elif err_seen:
            after_error.append((app, "[harness/psql] " + text[:60]))

print("final-round run directories:", len(final_ids), " sessions found in server logs:", len(sessions),
      " distinct run ids with sessions:", len(apps_seen))
print("statement classes:", dict(classes))
print("non-SELECT statements sent by the audit script (exact texts):")
for k, n in sorted(script_nonselect.items()):
    print(f"   {n:5d}  {k}")
print("harness-injected statements:")
for k, n in sorted(harness.items()):
    print(f"   {n:5d}  {k}")
print("VIOLATIONS:", len(violations))
for v in violations[:30]:
    print("   ", v)
ae = collections.Counter(t if t.startswith("[harness") else "SCRIPT: " + t for _, t in after_error)
print("statements after the first ERROR of a session:", len(after_error))
for k, n in ae.most_common():
    print(f"   {n:5d}  {k}")
