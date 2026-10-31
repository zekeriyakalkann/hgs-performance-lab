# Audit scenario runner. Requires env.sh sourced.
NEW="C:/Users/Ceng Zeki/Desktop/Projects/hgs2-lab-artifacts/db-audit/20261030-postgresql-readonly-audit-v2/postgresql_readonly_audit_v2.sql"
OLD="$S/baseline/postgresql_readonly_audit_v2.ORIGINAL.sql"
sysid() { cat "$S/h/sysid$1"; }
# base_params <sv> -> fills global array P with the five required parameters
base_params() { P=(-v expected_host=127.0.0.1 -v "expected_port=554$1" -v expected_server_addr=127.0.0.1
                   -v "expected_server_port=554$1" -v "expected_system_identifier=$(sysid "$1")"); }
# run <id> <psqlver> <serverver> <sqlfile> [psql args...]
run() { local id="$1" pv="$2" sv="$3" f="$4"; shift 4
  local d="$S/runs/$id"; rm -rf "$d"; mkdir -p "$d"
  printf '%q ' "$@" > "$d/args.txt"
  PGAPPNAME="$id" tpsql "$pv" "$sv" "$@" -f "$f" >"$d/stdout.txt" 2>"$d/stderr.txt"; local rc=$?
  echo "$rc" > "$d/exit.txt"
  local ab; ab=$(grep -m1 -o '^HGS2_AUDIT_ABORT: [a-z_]*\( expected_[a-z_]*\)\?' "$d/stdout.txt" | sed 's/^HGS2_AUDIT_ABORT: //')
  local abe; abe=$(grep -c 'HGS2_AUDIT_ABORT' "$d/stderr.txt")
  local last; last=$(grep -v '^[[:space:]]*$' "$d/stdout.txt" | tail -1)
  local comp=no; [ "$last" = "HGS2_AUDIT_COMPLETE" ] && comp=yes
  local pre; pre=$(grep -c '^HGS2_AUDIT_PREFLIGHT_OK$' "$d/stdout.txt")
  local err1; err1=$(grep -m1 -E 'ERROR|FATAL' "$d/stderr.txt" | sed 's/^psql:.*[.]sql:[0-9]*: //' | cut -c1-90)
  printf '%-34s exit=%s abort=[%s] abort_in_stderr=%s preflight_ok=%s complete_last=%s | %s\n' \
         "$id" "$rc" "${ab:--}" "$abe" "$pre" "$comp" "${err1:--}" | tee -a "$S/runs/SUMMARY.txt"
}
snapshot () 
{ 
    local label="$1";
    for v in 12 16 17 18;
    do
        local d="$S/snap/$label/pg$v";
        mkdir -p "$d";
        B=$(binof $v);
        "$B/pg_dump.exe" -h 127.0.0.1 -p 554$v -U pgadmin -s hgs2_perftest_db > "$d/schema.sql";
        "$B/pg_dumpall.exe" -h 127.0.0.1 -p 554$v -U pgadmin -g 2> /dev/null | grep -v '^-- Dumped\|^-- Started\|^-- Completed\|^\restrict\|^\unrestrict' > "$d/globals.sql";
        tpsql $v $v -U pgadmin -d hgs2_perftest_db -f "$S/h/snap.sql" > "$d/state.txt";
    done
}
