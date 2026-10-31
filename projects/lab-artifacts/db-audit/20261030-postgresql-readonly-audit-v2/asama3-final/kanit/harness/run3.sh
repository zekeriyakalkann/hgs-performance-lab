# Stage-3 runner. RUNS (output dir) and ACCEPT (validator --accept-warning args) may be set by caller.
S2="C:/Users/Ceng Zeki/Desktop/Projects/hgs2-lab-artifacts/db-audit/20261030-postgresql-readonly-audit-v2/postgresql_readonly_audit_v2.sql"
ORIG="$S/baseline/postgresql_readonly_audit_v2.ORIGINAL.sql"
F3="C:/Users/Ceng Zeki/Desktop/Projects/hgs2-lab-artifacts/db-audit/20261030-postgresql-readonly-audit-v2/asama3-final/postgresql_readonly_audit_v2.sql"
: "${RUNS:=$S/runs3}"
sysid() { cat "$S/h/sysid$1"; }
base_params() { P=(-v expected_host=127.0.0.1 -v "expected_port=554$1" -v expected_server_addr=127.0.0.1
                   -v "expected_server_port=554$1" -v "expected_system_identifier=$(sysid "$1")"); }
# run3 <id> <psqlver> <serverver> <sqlfile|-> [psql args...]   ('-' = read script from STDIN_FILE)
run3() { local id="$1" pv="$2" sv="$3" f="$4"; shift 4
  local d="$RUNS/$id"; rm -rf "$d"; mkdir -p "$d"; printf '%q ' "$@" > "$d/args.txt"
  if [ "$f" = "-" ]; then PGAPPNAME="$id" tpsql "$pv" "$sv" "$@" <"$STDIN_FILE" >"$d/stdout.txt" 2>"$d/stderr.txt"
  else PGAPPNAME="$id" tpsql "$pv" "$sv" "$@" -f "$f" </dev/null >"$d/stdout.txt" 2>"$d/stderr.txt"; fi
  local rc=$?; echo "$rc" > "$d/exit.txt"; [ "$f" != "-" ] && sha256sum "$f" | cut -c1-64 > "$d/script.sha256"
  py -3.13 -I "$S/h/validate_audit_result.py" --exit-code "$rc" --stdout "$d/stdout.txt" --stderr "$d/stderr.txt" ${ACCEPT:-} > "$d/verdict.txt"
  local ab; ab=$(grep -m1 -o '^HGS2_AUDIT_ABORT: [a-z_]*\( expected_[a-z_]*\)\?' "$d/stdout.txt" | sed 's/^HGS2_AUDIT_ABORT: //')
  local wn; wn=$(grep -o '^HGS2_AUDIT_WARNING: [a-z_]*' "$d/stdout.txt" | sed 's/^HGS2_AUDIT_WARNING: //' | tr '\n' ',')
  printf '%-44s exit=%s verdict=%s abort=[%s] warn=[%s]\n' "$id" "$rc" "$(head -1 "$d/verdict.txt")" "${ab:--}" "${wn%,}" | tee -a "$RUNS/SUMMARY.txt"; }
