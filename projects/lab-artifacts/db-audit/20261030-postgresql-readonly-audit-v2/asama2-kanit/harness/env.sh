# Test harness environment: isolates psql from any user/system config and the real server.
S="C:/Users/CENGZE~1/AppData/Local/Temp/claude/C--Users-Ceng-Zeki-Desktop-Projects-hgs2-lab-artifacts-db-audit-20261030-postgresql-readonly-audit-v2/68935c0c-6c43-42c8-a278-f832d7a4633e/scratchpad"
unset PGHOST PGHOSTADDR PGPORT PGDATABASE PGUSER PGOPTIONS PGSERVICE PGSSLMODE PGCLIENTENCODING PGPASSWORD
export PGSYSCONFDIR="$S/none" PGSERVICEFILE="$S/none/pg_service.conf" PGPASSFILE="$S/none/pgpass" PSQLRC="$S/none/psqlrc" PGCONNECT_TIMEOUT=5
export TMP="$S/tmp" TEMP="$S/tmp"
binof() { case "$1" in 18) echo "/c/Program Files/PostgreSQL/18/bin";; *) echo "$S/pg$1/pgsql/bin";; esac; }
portof() { echo "554$1"; }
# Guarded psql: only ever 127.0.0.1 on a 554xx test port. Usage: tpsql <psqlver> <serverver> [psql args...]
tpsql() { local pv="$1" sv="$2"; shift 2; local port; port=$(portof "$sv");
  case "$port" in 55412|55416|55417|55418) ;; *) echo "GUARD: refusing port $port" >&2; return 99;; esac
  "$(binof "$pv")/psql.exe" -X -h 127.0.0.1 -p "$port" "$@"; }
export LANG=C LC_ALL=C LC_MESSAGES=C
