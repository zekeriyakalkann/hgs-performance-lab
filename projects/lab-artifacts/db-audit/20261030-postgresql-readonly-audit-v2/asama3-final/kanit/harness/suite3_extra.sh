# Stage-3 additional suites. Requires env.sh + run3.sh sourced.

# psql cross-version matrix against primaries
suite3_cross() { local U=(-U hgs2_auditor -d hgs2_perftest_db) v
  for v in 12 16 17; do base_params $v; run3 "N2-psql18-server$v" 18 $v "$F3" "${U[@]}" "${P[@]}"; done
  base_params 18
  run3 "N3-psql12-server18" 12 18 "$F3" "${U[@]}" "${P[@]}"
  run3 "N4-psql16-server18" 16 18 "$F3" "${U[@]}" "${P[@]}"
  run3 "N5-psql17-server18" 17 18 "$F3" "${U[@]}" "${P[@]}"
}

# proxy: 127.0.0.1:55499 -> primary <v> (TCP relay, TLS passes through)
suite3_proxy() { local v="$1" U=(-U hgs2_auditor -d hgs2_perftest_db) i pid
  py -3.13 -I "$S/h/tcpproxy.py" --listen 55499 --target "554$v" --seconds 240 > "$RUNS/proxy-pg$v.log" 2>&1 &
  pid=$!
  for i in $(seq 1 300); do tpsql 18 99 -U pgadmin -d postgres -Atc "select 1" >/dev/null 2>&1 && break; done
  local X=(-v expected_server_addr=127.0.0.1 -v "expected_server_port=554$v" -v "expected_system_identifier=$(sysid $v)")
  run3 "X1-proxy-loopback-pg$v"           $v 99 "$F3" "${U[@]}" -v expected_host=127.0.0.1 -v expected_port=55499 "${X[@]}"
  run3 "X2-proxy-expected-server-port-pg$v" $v 99 "$F3" "${U[@]}" -v expected_host=127.0.0.1 -v "expected_port=554$v" "${X[@]}"
  run3 "X3-proxy-remote-name-disable-pg$v" $v 99 "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=disable" -v expected_host=fake-remote.example -v expected_port=55499 "${X[@]}"
  run3 "X4-proxy-remote-name-require-pg$v" $v 99 "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=require" -v expected_host=fake-remote.example -v expected_port=55499 "${X[@]}"
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

# physical replica <r> of primary <v>
suite3_replica() { local v="$1" r="$2" U=(-U hgs2_auditor -d hgs2_perftest_db)
  local Rp=(-v expected_host=127.0.0.1 -v "expected_port=554$r" -v expected_server_addr=127.0.0.1 -v "expected_server_port=554$r")
  run3 "R1-standby-primary-sysid-pg$v"    $v $r "$F3" "${U[@]}" "${Rp[@]}" -v "expected_system_identifier=$(sysid $v)"
  run3 "R2-standby-wrong-sysid-pg$v"      $v $r "$F3" "${U[@]}" "${Rp[@]}" -v expected_system_identifier=1234567890123456789
  run3 "R3-standby-psql-1-pg$v"           $v $r "$F3" -1 "${U[@]}" "${Rp[@]}" -v "expected_system_identifier=$(sysid $v)"
  run3 "R4-standby-noP2-psql-1-pg$v"      $v $r "$S/mut3/new_noP2.sql" -1 "${U[@]}" "${Rp[@]}" -v "expected_system_identifier=$(sysid $v)"
}

# search_path / object shadowing attack (installs evil objects + persistent role setting, then removes them)
suite3_attack() { local v="$1" U=(-U hgs2_auditor -d hgs2_perftest_db)
  base_params "$v"; local B=("${P[@]}")
  local W=(-v expected_host=attacker.example -v expected_server_port=9999 -v expected_system_identifier=1111111111111111111)
  tpsql $v $v -U pgadmin -d hgs2_perftest_db -q -f "$S/h/evil_full_setup.sql" >/dev/null || { echo "attack setup failed pg$v"; return 1; }
  run3 "S1-attack-wrong-params-pg$v"      $v $v "$F3" "${U[@]}" "${B[@]}" "${W[@]}"
  run3 "S2-attack-preopen-RR-RO-pg$v"     $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
  run3 "S3-attack-correct-params-pg$v"    $v $v "$F3" "${U[@]}" "${B[@]}"
  PGOPTIONS='-c search_path=evil,pg_catalog' run3 "S4-attack-pgoptions-wrong-host-pg$v" $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_host=attacker.example
  run3 "S5-attack-wrong-sysid-only-pg$v"  $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_system_identifier=1111111111111111111
  run3 "O1-orig-attack-wrong-params-pg$v" $v $v "$ORIG" "${U[@]}" "${B[@]}" "${W[@]}"
  run3 "O2-orig-attack-preopen-RR-RO-pg$v" $v $v "$ORIG" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
  run3 "O3-stage2-attack-wrong-params-pg$v" $v $v "$S2" "${U[@]}" "${B[@]}" "${W[@]}"
  run3 "O4-stage2-attack-preopen-RR-RO-pg$v" $v $v "$S2" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
  echo "pg$v attack cleanup (evil_left, auditor_db_settings_left): $(tpsql $v $v -U pgadmin -d hgs2_perftest_db -qAt -f "$S/h/evil_full_cleanup.sql" 2>/dev/null | tr '\n' ' ')" >> "$RUNS/CLEANUP.txt"
}

# marker forging via object names containing real newlines
suite3_forge() { local v="$1" U=(-U hgs2_auditor -d hgs2_perftest_db)
  base_params "$v"
  tpsql $v $v -U pgadmin -d hgs2_perftest_db -qAt -f "$S/h/forge_setup.sql" >/dev/null || { echo "forge setup failed pg$v"; return 1; }
  run3 "F1-forge-unaligned-tuples-pg$v"   $v $v "$F3" "${U[@]}" "${P[@]}" -A -t
  run3 "F2-forge-default-pg$v"            $v $v "$F3" "${U[@]}" "${P[@]}"
  run3 "O5-stage2-forge-unaligned-pg$v"   $v $v "$S2" "${U[@]}" "${P[@]}" -A -t
  echo "pg$v forge cleanup (tables_left): $(tpsql $v $v -U pgadmin -d hgs2_perftest_db -qAt -f "$S/h/forge_cleanup.sql" 2>/dev/null)" >> "$RUNS/CLEANUP.txt"
}

# client encoding WIN1254 with a non-cp1254 object name
suite3_encoding() { local v="$1" U=(-U hgs2_auditor -d hgs2_perftest_db)
  base_params "$v"
  tpsql $v $v -U pgadmin -d hgs2_perftest_db -q -v ON_ERROR_STOP=1 -f "$S/h/enc_setup.sql" >/dev/null || return 1
  PGCLIENTENCODING=WIN1254 run3 "K1-WIN1254-pg$v" $v $v "$F3" "${U[@]}" "${P[@]}"
  tpsql $v $v -U pgadmin -d hgs2_perftest_db -q -v ON_ERROR_STOP=1 -f "$S/h/enc_cleanup.sql" >/dev/null
  echo "pg$v encoding cleanup (test_ schemas left): $(tpsql $v $v -U pgadmin -d hgs2_perftest_db -Atc "select count(*) from pg_namespace where nspname like 'test%'")" >> "$RUNS/CLEANUP.txt"
}
