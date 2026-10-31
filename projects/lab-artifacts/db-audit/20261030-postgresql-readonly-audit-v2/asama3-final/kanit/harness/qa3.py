"""Static QA for the audit script.

Part A (parser): PostgreSQL's real parser (pglast / libpg_query) on every SQL statement of every
psql branch. This checks SQL SYNTAX only - not catalog columns, functions, privileges or versions.
Part B (static): psql meta-command structure, variables, markers, write-command scan.
"""
import collections
import json
import os
import re
import sys

script, pyl = sys.argv[1], sys.argv[2]
sys.path.insert(0, pyl)
import pglast  # noqa: E402
from pglast import parser as pgparser  # noqa: E402

BS = "\\"
text = open(script, encoding="utf-8").read()
lines = text.split("\n")
raw = open(script, "rb").read()

print("=" * 78)
print("FILE")
print("  bytes:", len(raw), " lines:", text.count("\n"), " CRLF:", raw.count(b"\r\n"),
      " BOM:", raw.startswith(b"\xef\xbb\xbf"))

# --------------------------------------------------------------------------- helpers
def is_meta(line):
    return line.lstrip().startswith(BS)


def meta_cmd(line):
    return line.lstrip().split()[0]


# Build SQL chunks: text between terminators (';' at end of statement, or a \gset line)
chunks = []          # (start_line, sql_text, terminated_by_gset)
buf, start = [], None
for i, line in enumerate(lines, 1):
    if is_meta(line):
        if meta_cmd(line) == BS + "gset":
            chunks.append((start, "\n".join(buf), True))
            buf, start = [], None
        continue
    stripped = line.strip()
    if not buf and (not stripped or stripped.startswith("--")):
        continue
    if start is None:
        start = i
    buf.append(line)
    if re.search(r";\s*(--.*)?$", line):
        chunks.append((start, "\n".join(buf), False))
        buf, start = [], None
assert not "".join(buf).strip(), "unterminated SQL at end: " + "\n".join(buf)

# --------------------------------------------------------------------------- Part A
print("=" * 78)
print("PART A - PARSER (pglast %s, libpg_query PostgreSQL %s.%s)" % (
    pglast.__version__, *pgparser.get_postgresql_version()))
VAR = re.compile(r":'([A-Za-z_][A-Za-z0-9_]*)'")
stmt_types = collections.Counter()
funcs = collections.Counter()
parse_errors = []
select_into = []
locking = []
modifying_cte = []
gset_aliases = collections.OrderedDict()


def walk(node, visit):
    if isinstance(node, dict):
        visit(node)
        for v in node.values():
            walk(v, visit)
    elif isinstance(node, list):
        for v in node:
            walk(v, visit)


for start, sql, gset in chunks:
    sub = VAR.sub("'psqlvar'", sql)
    try:
        tree = json.loads(pgparser.parse_sql_json(sub))
    except Exception as e:  # noqa: BLE001
        parse_errors.append((start, str(e)))
        continue
    for st in tree.get("stmts", []):
        node = st["stmt"]
        kind = next(iter(node))
        stmt_types[kind] += 1
        body = node[kind]
        if kind == "SelectStmt":
            if body.get("intoClause"):
                select_into.append(start)
            if body.get("lockingClause"):
                locking.append(start)
            wc = body.get("withClause", {})
            for cte in wc.get("ctes", []):
                q = cte["CommonTableExpr"]["ctequery"]
                if next(iter(q)) != "SelectStmt":
                    modifying_cte.append(start)
            if gset:
                for t in body.get("targetList", []):
                    name = t["ResTarget"].get("name")
                    if name:
                        gset_aliases[name] = start

        def visit(d):
            if "FuncCall" in d:
                parts = [p["String"]["sval"] for p in d["FuncCall"]["funcname"]]
                funcs[".".join(parts)] += 1
        walk(body, visit)

print("  SQL chunks parsed:", len(chunks), " parse errors:", len(parse_errors))
for e in parse_errors:
    print("   PARSE ERROR at line", e)
print("  statement types:", dict(stmt_types))
print("  SELECT ... INTO:", select_into or "none", " FOR UPDATE/SHARE:", locking or "none",
      " data-modifying CTE:", modifying_cte or "none")
print("  functions called (%d distinct):" % len(funcs))
print("   ", ", ".join(sorted(funcs)))
DANGEROUS_FN = re.compile(r"(^|\.)(nextval|setval|set_config|lo_\w+|pg_advisory\w*|pg_terminate_backend|"
                          r"pg_cancel_backend|pg_reload_conf|pg_rotate_logfile|pg_switch_wal|pg_create\w*|"
                          r"pg_drop\w*|dblink\w*|pg_read_file|pg_read_binary_file|pg_ls_\w+|pg_stat_file|"
                          r"pg_current_xact_id|txid_current|pg_notify|pg_sleep\w*|pg_import_system_collations|"
                          r"pg_logical_\w+|pg_replication_\w+|pg_promote|pg_backup_\w+|pg_start_backup|"
                          r"pg_stop_backup|pg_log_backend_memory_contexts|pg_signal_backend|lo_\w+)$")
bad_fn = sorted(f for f in funcs if DANGEROUS_FN.search(f))
print("  side-effect / sensitive functions:", bad_fn or "none")

# --------------------------------------------------------------------------- Part B
print("=" * 78)
print("PART B - STATIC CHECKS (no server involved)")

# B1 meta-commands inventory and dangerous ones
metas = collections.Counter(meta_cmd(l) for l in lines if is_meta(l))
print("  B1 meta-commands used:", dict(metas))
DANGER = {"!", "o", "out", "w", "write", "copy", "g", "gx", "gexec", "setenv", "cd", "lo_import",
          "lo_export", "lo_unlink", "lo_list", "i", "include", "ir", "include_relative", "c", "connect",
          "password", "s", "e", "edit", "ef", "ev", "getenv", "sf", "sv", "bind", "parse", "bind_named",
          "startpipeline", "endpipeline", "syncpipeline", "watch", "crosstabview", "prompt", "unset"}
dangerous = {m: c for m, c in metas.items() if m[1:] in DANGER}
print("     dangerous meta-commands:", dangerous or "none")

# B2 conditional balance
stack, cond_err = [], []
for i, l in enumerate(lines, 1):
    if not is_meta(l):
        continue
    m = meta_cmd(l)
    if m == BS + "if":
        stack.append(i)
    elif m in (BS + "elif", BS + "else"):
        if not stack:
            cond_err.append((i, m + " without \\if"))
    elif m == BS + "endif":
        if not stack:
            cond_err.append((i, "\\endif without \\if"))
        else:
            stack.pop()
print("  B2 \\if:", metas.get(BS + "if", 0), " \\elif:", metas.get(BS + "elif", 0), " \\else:",
      metas.get(BS + "else", 0), " \\endif:", metas.get(BS + "endif", 0),
      " unclosed:", stack or "none", " errors:", cond_err or "none")

# B3 variables
BUILTIN = {"VERSION_NUM", "SERVER_VERSION_NUM", "HOST", "PORT", "DBNAME"}
PARAMS = {"expected_host", "expected_port", "expected_server_addr", "expected_server_port",
          "expected_system_identifier", "allow_superuser", "allow_insecure_transport",
          "audit_statement_timeout", "audit_lock_timeout"}
set_vars = {}
for i, l in enumerate(lines, 1):
    if is_meta(l) and meta_cmd(l) == BS + "set":
        name = l.split()[1]
        set_vars[name] = i
used = collections.defaultdict(list)
for i, l in enumerate(lines, 1):
    if l.strip().startswith("--"):
        continue
    # psql does not interpolate inside quoted literals: protect :'var', then drop plain literals
    l = re.sub(r":'([A-Za-z_]\w*)'", r":{?\1}", l)
    l = re.sub(r"'(?:[^']|'')*'", "''", l)
    for m in re.finditer(r":\{\?([A-Za-z_]\w*)\}|:'([A-Za-z_]\w*)'|:\"([A-Za-z_]\w*)\"|(?<![:\w]):([A-Za-z_]\w*)", l):
        name = next(g for g in m.groups() if g)
        used[name].append(i)
defined = set(gset_aliases) | set(set_vars) | BUILTIN | PARAMS
undefined = sorted(n for n in used if n not in defined)
psql_settings = {"ON_ERROR_STOP", "AUTOCOMMIT", "ON_ERROR_ROLLBACK", "FETCH_COUNT", "QUIET"}
unused_gset = sorted(n for n in gset_aliases if n not in used)
print("  B3 \\gset variables:", len(gset_aliases), " \\set variables:", sorted(set_vars))
print("     used but never defined (excl. psql built-ins/params):", undefined or "none")
print("     \\gset variables never used:", unused_gset or "none")
print("     parameters used:", sorted(n for n in used if n in PARAMS))
print("     psql built-ins used:", sorted(n for n in used if n in BUILTIN))

# B4 ON_ERROR_STOP never switched off
oes = [(i, l.strip()) for i, l in enumerate(lines, 1) if is_meta(l) and "ON_ERROR_STOP" in l]
print("  B4 ON_ERROR_STOP assignments:", oes)

# B5 abort blocks: echo marker -> int4 cast with the same reason -> \quit
abort_ok, abort_bad = 0, []
for i, l in enumerate(lines):
    if is_meta(l) and meta_cmd(l) == BS + "echo" and "'HGS2_AUDIT_ABORT: " in l:
        reason = re.search(r"HGS2_AUDIT_ABORT: ([a-z_]+(?: expected_[a-z_]+)?)", l).group(1)
        nxt = lines[i + 1].strip()
        nxt2 = lines[i + 2].strip()
        if (nxt == f"SELECT 'HGS2_AUDIT_ABORT: {reason}'::pg_catalog.int4;" and nxt2 == BS + "quit"):
            abort_ok += 1
        else:
            abort_bad.append((i + 1, reason))
print("  B5 abort blocks well-formed:", abort_ok, " malformed:", abort_bad or "none")

# B6 COMPLETE marker
comp = [i for i, l in enumerate(lines, 1) if "HGS2_AUDIT_COMPLETE" in l and not l.strip().startswith("--")]
non_abort = [s for s, sql, _ in chunks if "HGS2_AUDIT_ABORT" not in sql]
last_ok_stmt = max(non_abort)
after = [s for s, sql, _ in chunks if comp and s > comp[0]]
after_kinds = ["abort" if "HGS2_AUDIT_ABORT" in sql else "OTHER"
               for s, sql, _ in chunks if comp and s > comp[0]]
print("  B6 HGS2_AUDIT_COMPLETE emitted at lines:", comp,
      " last non-abort SQL chunk starts at line", last_ok_stmt)
print("     after every non-abort SQL statement:", all(c > last_ok_stmt for c in comp),
      " count == 1:", len(comp) == 1,
      " SQL after marker:", list(zip(after, after_kinds)) or "none")
# the marker must sit in the THEN branch of the final \if whose condition comes from the last \gset
enclosing = None
for i in range(comp[0] - 2, -1, -1):
    if is_meta(lines[i]) and meta_cmd(lines[i]) == BS + "if":
        enclosing = (i + 1, lines[i].strip())
        break
print("     enclosing condition:", enclosing)

# B7 transaction control (from parser)
txn = []
for start, sql, _ in chunks:
    tree = json.loads(pgparser.parse_sql_json(VAR.sub("'psqlvar'", sql)))
    for st in tree["stmts"]:
        node = st["stmt"]
        if "TransactionStmt" in node:
            txn.append((start, node["TransactionStmt"]["kind"]))
        if "VariableSetStmt" in node:
            v = node["VariableSetStmt"]
            txn.append((start, "SET " + ("LOCAL " if v.get("is_local") else "") + v.get("name", "")))
print("  B7 transaction-control / SET statements in order:")
for t in txn:
    print("       line %4d  %s" % t)

# B8 non-ASCII outside full-line comments
nonascii = [i for i, l in enumerate(lines, 1)
            if any(ord(ch) > 127 for ch in l) and not l.strip().startswith("--")]
print("  B8 non-ASCII characters outside full-line comments:", nonascii or "none")

# B9 regex write-command scan on SQL with comments and string literals removed
WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|GRANT|REVOKE|COPY|VACUUM|"
                   # END/ABORT omitted: they collide with CASE ... END; transaction statements
                   # are taken from the parser in B7 instead.
                   r"ANALYZE|CLUSTER|REINDEX|COMMENT|SECURITY\s+LABEL|LOCK|CALL|DO|COMMIT|"
                   r"PREPARE|EXECUTE|NOTIFY|LISTEN|UNLISTEN|REFRESH|IMPORT|DISCARD|CHECKPOINT|LOAD|RESET|"
                   r"SAVEPOINT|RELEASE|DECLARE|FETCH|MOVE|CLOSE|INTO)\b", re.I)
hits = []
for start, sql, _ in chunks:
    s = re.sub(r"--[^\n]*", "", sql)
    s = re.sub(r"'(?:[^']|'')*'", "''", s)
    for m in WRITE.finditer(s):
        hits.append((start, m.group(1)))
print("  B9 write/DDL/DCL keyword hits in SQL (comments and literals removed):", hits or "none")

# B11 search_path hardening: outside the pinned window (before SET LOCAL search_path, after ROLLBACK)
#     every function must be schema-qualified and every operator written as OPERATOR(pg_catalog.x)
pin = next(s for s, sql, _ in chunks if re.search(r"SET LOCAL search_path", sql))
unpin = next(s for s, sql, _ in chunks if re.match(r"\s*ROLLBACK;", sql))
OPS = re.compile(r"(?<![A-Za-z_(.])(=|<>|>=|<=|<|>|<<=|\|\||\+|-|\*)(?![A-Za-z_)])")
issues = []
for start, sql, _ in chunks:
    if pin <= start < unpin + 1 and start != unpin:
        continue
    s = re.sub(r"--[^\n]*", "", sql)
    s = re.sub(r"'(?:[^']|'')*'", "''", s)
    s = s.replace("OPERATOR(pg_catalog.", "OPERATOR(")
    s2 = re.sub(r"OPERATOR\([^)]*\)", " ", s)
    s2 = re.sub(r"::[A-Za-z_.0-9]+", " ", s2)
    for m in OPS.finditer(s2):
        issues.append((start, "operator " + m.group(1)))
    tree = json.loads(pgparser.parse_sql_json(VAR.sub("'psqlvar'", sql)))

    def visit(d, start=start):
        if "FuncCall" in d:
            parts = [p["String"]["sval"] for p in d["FuncCall"]["funcname"]]
            if len(parts) == 1:
                issues.append((start, "unqualified function " + parts[0]))
    walk(tree, visit)
print("  B11 search_path pinned between lines", pin, "and", unpin,
      "; unqualified functions/operators outside that window:", issues or "none")

# B10 version branches
branches = [(i, l.strip()) for i, l in enumerate(lines, 1)
            if is_meta(l) and meta_cmd(l) in (BS + "if", BS + "elif")
            and re.search(r":(pg\d+|server_v\d+|psql_v\d+)_or_newer", l)]
print("  B10 version branches:", branches)

# ---------------------------------------------------------------- stage-3 additions
print("  --- stage-3 checks")
# B12 no backslash inside SQL string literals (independent of standard_conforming_strings)
bs_lits = []
for start, sql, _ in chunks:
    s = re.sub(r"--[^\n]*", "", sql)
    for m in re.finditer(r"'(?:[^']|'')*'", s):
        if BS in m.group(0):
            bs_lits.append((start, m.group(0)[:40]))
print("  B12 backslash inside SQL string literals:", bs_lits or "none")

# B13 the masking allow-lists of Section 4 and 5.11 must be identical
def allowlist_after(marker_regex):
    for start, sql, _ in chunks:
        if re.search(marker_regex, sql):
            m = re.search(r"IN \(\s*('search_path'.*?)\)\s*\n?\s*(THEN|$)", sql, re.S)
            m = re.search(r"\)\) IN \((.*?)\)", sql, re.S)
            return start, tuple(re.findall(r"'([a-z_]+)'", m.group(1)))
    return None, ()
s4, l4 = allowlist_after(r"AS setting_value")
s11, l11 = allowlist_after(r"AS proconfig_masked")
print("  B13 Section 4 allow-list (line %s) == 5.11 allow-list (line %s):" % (s4, s11), l4 == l11,
      " entries:", len(l4))

# B14 \gset aliases must not overwrite psql special variables
SPECIAL = re.compile(r"^[A-Z_]+$")
clash = [a for a in gset_aliases if SPECIAL.match(a)]
print("  B14 \\gset aliases colliding with psql special (UPPERCASE) variables:", clash or "none")

# B15 no '= NULL' / '<> NULL' comparisons (transform_null_equals independence)
eqnull = [(s, "") for s, sql, _ in chunks if re.search(r"(=|<>)\s*NULL\b", re.sub(r"'(?:[^']|'')*'", "''", sql), re.I)]
print("  B15 '= NULL' comparisons:", eqnull or "none")

# B16 scope of override flags: lines that read them
for flag in ("allow_superuser", "allow_insecure_transport"):
    uses = [i for i, l in enumerate(lines, 1)
            if (":'" + flag + "'") in l and not l.strip().startswith("--")]
    print("  B16 :'%s' read at lines:" % flag, uses)

# B17 warning markers: each echoed only inside an \if block
warn = [(i, l.strip()) for i, l in enumerate(lines, 1)
        if is_meta(l) and meta_cmd(l) == BS + "echo" and "HGS2_AUDIT_WARNING:" in l]
print("  B17 warning markers:", warn)

# B18 every \echo that interpolates a variable: which variables (name-based ones must be *_safe)
echo_vars = collections.Counter()
for l in lines:
    if is_meta(l) and meta_cmd(l) == BS + "echo":
        for v in re.findall(r"(?<!:):([A-Za-z_]\w*)", l):
            echo_vars[v] += 1
print("  B18 variables printed by \\echo:", sorted(echo_vars))
