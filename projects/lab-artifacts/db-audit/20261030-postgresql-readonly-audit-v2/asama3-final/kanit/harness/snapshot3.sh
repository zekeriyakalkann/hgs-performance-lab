snapshot3() { local label="$1" v d B; for v in 12 16 17 18; do d="$S/snap3/$label/pg$v"; mkdir -p "$d"; B=$(binof $v)
  "$B/pg_dump.exe" -h 127.0.0.1 -p 554$v -U pgadmin -s hgs2_perftest_db | grep -avE '^.(un)?restrict ' > "$d/schema.sql"
  "$B/pg_dumpall.exe" -h 127.0.0.1 -p 554$v -U pgadmin -g 2>/dev/null | grep -avE '^.(un)?restrict |^-- (Dumped|Started|Completed)' > "$d/globals.sql"
  tpsql $v $v -U pgadmin -d hgs2_perftest_db -f "$S/h/snap3.sql" > "$d/state.txt"; done; }
