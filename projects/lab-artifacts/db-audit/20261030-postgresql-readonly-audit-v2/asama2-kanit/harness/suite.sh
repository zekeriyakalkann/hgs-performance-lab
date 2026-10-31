# suite <ver>: security-abort scenarios with the version's own psql against its own server
suite() { local v="$1" U=(-U hgs2_auditor -d hgs2_perftest_db) M="$S/mut"
  local RRRO='-c default_transaction_isolation=repeatable\ read -c default_transaction_read_only=on'
  base_params "$v"; local B=("${P[@]}")
  omit() { local skip="$1" i; Q=(); for ((i=0;i<${#B[@]};i+=2)); do [[ "${B[i+1]}" == "$skip="* ]] || Q+=("${B[i]}" "${B[i+1]}"); done; }
  run "A01-wrong-db-pg$v"            $v $v "$NEW" -U hgs2_auditor -d other_db "${B[@]}"
  run "A02-prod-db-name-pg$v"        $v $v "$NEW" -U hgs2_auditor -d hibrit_giris_db "${B[@]}"
  omit expected_host;        run "A03-missing-host-pg$v"         $v $v "$NEW" "${U[@]}" "${Q[@]}"
  omit expected_port;        run "A04-missing-port-pg$v"         $v $v "$NEW" "${U[@]}" "${Q[@]}"
  omit expected_server_addr; run "A05-missing-srvaddr-pg$v"      $v $v "$NEW" "${U[@]}" "${Q[@]}"
  omit expected_server_port; run "A06-missing-srvport-pg$v"      $v $v "$NEW" "${U[@]}" "${Q[@]}"
  omit expected_system_identifier; run "A07-missing-sysid-pg$v"  $v $v "$NEW" "${U[@]}" "${Q[@]}"
  run "A08-wrong-host-pg$v"          $v $v "$NEW" "${U[@]}" "${B[@]}" -v expected_host=localhost
  run "A09-wrong-port-pg$v"          $v $v "$NEW" "${U[@]}" "${B[@]}" -v expected_port=5432
  run "A10-wrong-srvaddr-pg$v"       $v $v "$NEW" "${U[@]}" "${B[@]}" -v expected_server_addr=10.0.0.1
  run "A11-wrong-srvport-pg$v"       $v $v "$NEW" "${U[@]}" "${B[@]}" -v expected_server_port=5432
  run "A12-wrong-sysid-pg$v"         $v $v "$NEW" "${U[@]}" "${B[@]}" -v expected_system_identifier=1234567890123456789
  run "A13-sysid-no-privilege-pg$v"  $v $v "$NEW" -U hgs2_auditor_nosysid -d hgs2_perftest_db "${B[@]}"
  run "A14-superuser-pg$v"           $v $v "$NEW" -U pgadmin -d hgs2_perftest_db "${B[@]}"
  run "A15-superuser-allow0-pg$v"    $v $v "$NEW" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=0
  run "A16-superuser-allowtrue-pg$v" $v $v "$NEW" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=true
  run "A17-superuser-allow1-pg$v"    $v $v "$NEW" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=1
  run "A18-su-behind-role-pg$v"      $v $v "$NEW" -U hgs2_su_behind_role -d hgs2_perftest_db "${B[@]}"
  run "A19-psql-1-pg$v"              $v $v "$NEW" -1 "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run "A20-psql-1-defaults-RR-RO-pg$v" $v $v "$NEW" -1 "${U[@]}" "${B[@]}"
  run "A21-preopen-tx-pg$v"          $v $v "$NEW" "${U[@]}" "${B[@]}" -c BEGIN
  run "A22-preopen-RO-tx-pg$v"       $v $v "$NEW" "${U[@]}" "${B[@]}" -c "BEGIN READ ONLY"
  run "A23-preopen-RR-tx-pg$v"       $v $v "$NEW" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ"
  run "A24-preopen-tx-with-xid-pg$v" $v $v "$NEW" "${U[@]}" "${B[@]}" -c BEGIN -c "SELECT txid_current() > 0 AS xid_assigned"
  run "A25-preopen-savepoint-pg$v"   $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c BEGIN -c "SAVEPOINT s1"
  run "M1-readwrite-mutant-pg$v"     $v $v "$M/new_readwrite.sql" "${U[@]}" "${B[@]}"
  run "M2-wrong-iso-mutant-pg$v"     $v $v "$M/new_wrong_iso.sql" "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run "M3-noP2-psql-1-RR-RO-pg$v"         $v $v "$M/new_noP2.sql" -1 "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run "M4-noP2-noprobe-psql-1-RR-RO-pg$v" $v $v "$M/new_noP2_noprobe.sql" -1 "${U[@]}" "${B[@]}"
  run "M5-noP2-preopen-RR-pg$v"      $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
  omit expected_host; run "E1-cli-ON_ERROR_STOP0-pg$v"     $v $v "$NEW" -v ON_ERROR_STOP=0 "${U[@]}" "${Q[@]}"
  omit expected_host; run "E2-mutant-ON_ERROR_STOP-off-pg$v" $v $v "$M/new_onerrorstop_off.sql" "${U[@]}" "${Q[@]}"
  run "T1-sslmode-require-pg$v"      $v $v "$NEW" -U hgs2_auditor -d "dbname=hgs2_perftest_db sslmode=require" "${B[@]}"
  run "T2-sslmode-disable-pg$v"      $v $v "$NEW" -U hgs2_auditor -d "dbname=hgs2_perftest_db sslmode=disable" "${B[@]}"
}
