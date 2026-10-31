# Stage-3 scenario suite. Requires env.sh + run3.sh sourced. Target file: $F3. Mutants: $S/mut3.
# suite3_core <v>: version-independent scenarios, version's own psql against its own primary.
suite3_core() { local v="$1" M="$S/mut3" U=(-U hgs2_auditor -d hgs2_perftest_db)
  local RRRO='-c default_transaction_isolation=repeatable\ read -c default_transaction_read_only=on'
  base_params "$v"; local B=("${P[@]}")
  omit() { local skip="$1" i; Q=(); for ((i=0;i<${#B[@]};i+=2)); do [[ "${B[i+1]}" == "$skip="* ]] || Q+=("${B[i]}" "${B[i+1]}"); done; }
  # --- normal
  run3 "N1-normal-pg$v"                 $v $v "$F3" "${U[@]}" "${B[@]}"
  # --- target / identity
  run3 "A01-wrong-db-pg$v"              $v $v "$F3" -U hgs2_auditor -d other_db "${B[@]}"
  run3 "A02-prod-db-name-pg$v"          $v $v "$F3" -U hgs2_auditor -d hibrit_giris_db "${B[@]}"
  omit expected_host;              run3 "A03-missing-host-pg$v"    $v $v "$F3" "${U[@]}" "${Q[@]}"
  omit expected_port;              run3 "A04-missing-port-pg$v"    $v $v "$F3" "${U[@]}" "${Q[@]}"
  omit expected_server_addr;       run3 "A05-missing-srvaddr-pg$v" $v $v "$F3" "${U[@]}" "${Q[@]}"
  omit expected_server_port;       run3 "A06-missing-srvport-pg$v" $v $v "$F3" "${U[@]}" "${Q[@]}"
  omit expected_system_identifier; run3 "A07-missing-sysid-pg$v"   $v $v "$F3" "${U[@]}" "${Q[@]}"
  run3 "A08-wrong-host-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_host=localhost
  run3 "A09-wrong-port-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_port=5432
  run3 "A10-wrong-srvaddr-pg$v"         $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_server_addr=10.0.0.1
  run3 "A11-wrong-srvport-pg$v"         $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_server_port=5432
  run3 "A12-wrong-sysid-pg$v"           $v $v "$F3" "${U[@]}" "${B[@]}" -v expected_system_identifier=1234567890123456789
  run3 "A13-sysid-no-privilege-pg$v"    $v $v "$F3" -U hgs2_auditor_nosysid -d hgs2_perftest_db "${B[@]}"
  # --- superuser / least privilege
  run3 "A14-superuser-pg$v"             $v $v "$F3" -U pgadmin -d hgs2_perftest_db "${B[@]}"
  run3 "A15-superuser-allow0-pg$v"      $v $v "$F3" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=0
  run3 "A16-superuser-allowtrue-pg$v"   $v $v "$F3" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=true
  run3 "A17-superuser-allow1-pg$v"      $v $v "$F3" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=1
  ACCEPT="--accept-warning superuser_allowed" run3 "A17b-superuser-allow1-accepted-pg$v" $v $v "$F3" -U pgadmin -d hgs2_perftest_db "${B[@]}" -v allow_superuser=1
  run3 "A18-su-behind-role-pg$v"        $v $v "$F3" -U hgs2_su_behind_role -d hgs2_perftest_db "${B[@]}"
  run3 "A30-member-of-superuser-pg$v"   $v $v "$F3" -U hgs2_member_of_su -d hgs2_perftest_db "${B[@]}"
  run3 "A31-member-of-su-allow1-pg$v"   $v $v "$F3" -U hgs2_member_of_su -d hgs2_perftest_db "${B[@]}" -v allow_superuser=1
  run3 "A32-excess-privilege-pg$v"      $v $v "$F3" -U hgs2_auditor_rsf -d hgs2_perftest_db "${B[@]}"
  # --- transaction
  run3 "A19-psql-1-pg$v"                $v $v "$F3" -1 "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run3 "A20-psql-1-defaults-RR-RO-pg$v" $v $v "$F3" -1 "${U[@]}" "${B[@]}"
  run3 "A21-preopen-default-pg$v"       $v $v "$F3" "${U[@]}" "${B[@]}" -c BEGIN
  run3 "A22-preopen-RO-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN READ ONLY"
  run3 "A23-preopen-RR-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ"
  run3 "A24-preopen-xid-pg$v"           $v $v "$F3" "${U[@]}" "${B[@]}" -c BEGIN -c "SELECT txid_current() > 0 AS xid_assigned"
  run3 "A26-preopen-SERIALIZABLE-pg$v"  $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL SERIALIZABLE"
  run3 "A27-preopen-READ-WRITE-pg$v"    $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN READ WRITE"
  run3 "A28-preopen-RC-prior-query-pg$v" $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL READ COMMITTED" -c "SELECT 1 AS prior_query"
  run3 "A29-preopen-same-message-pg$v"  $v $v "$F3" "${U[@]}" "${B[@]}" -c "BEGIN; SELECT 1 AS same_message"
  run3 "A25-noP2-savepoint-pg$v"        $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c BEGIN -c "SAVEPOINT s1"
  run3 "M1-readwrite-mutant-pg$v"       $v $v "$M/new_readwrite.sql" "${U[@]}" "${B[@]}"
  run3 "M2-wrong-iso-mutant-pg$v"       $v $v "$M/new_wrong_iso.sql" "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run3 "M3-noP2-psql-1-RR-RO-pg$v"         $v $v "$M/new_noP2.sql" -1 "${U[@]}" "${B[@]}"
  PGOPTIONS="$RRRO" run3 "M4-noP2-noprobe-psql-1-RR-RO-pg$v" $v $v "$M/new_noP2_noprobe.sql" -1 "${U[@]}" "${B[@]}"
  run3 "M5-noP2-preopen-RR-RO-pg$v"     $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
  run3 "M6-noP2-preopen-SERIALIZABLE-pg$v" $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY"
  run3 "M7-noP2-preopen-RC-RO-pg$v"     $v $v "$M/new_noP2.sql" "${U[@]}" "${B[@]}" -c "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY"
  # --- error handling / automation / psql variables
  omit expected_host; run3 "E01-cli-ON_ERROR_STOP0-pg$v"        $v $v "$F3" -v ON_ERROR_STOP=0 "${U[@]}" "${Q[@]}"
  omit expected_host; run3 "E02-mutant-ON_ERROR_STOP-off-pg$v"  $v $v "$M/new_onerrorstop_off.sql" "${U[@]}" "${Q[@]}"
  run3 "E03-ECHO-all-pg$v"              $v $v "$F3" "${U[@]}" "${B[@]}" -v ECHO=all
  run3 "E04-unaligned-tuples-pg$v"      $v $v "$F3" "${U[@]}" "${B[@]}" -A -t
  run3 "E05-expanded-pg$v"              $v $v "$F3" "${U[@]}" "${B[@]}" -x
  run3 "E06-SINGLESTEP-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -v SINGLESTEP=on
  run3 "E07-AUTOCOMMIT-off-pg$v"        $v $v "$F3" "${U[@]}" "${B[@]}" -v AUTOCOMMIT=off
  run3 "E08-ON_ERROR_ROLLBACK-on-pg$v"  $v $v "$F3" "${U[@]}" "${B[@]}" -v ON_ERROR_ROLLBACK=on
  run3 "E09-FETCH_COUNT-1-pg$v"         $v $v "$F3" "${U[@]}" "${B[@]}" -v FETCH_COUNT=1
  run3 "E10-output-to-file-pg$v"        $v $v "$F3" "${U[@]}" "${B[@]}" -o "$RUNS/E10-results-pg$v.txt"
  run3 "E11-VERBOSITY-terse-abort-pg$v" $v $v "$F3" "${U[@]}" "${B[@]}" -v VERBOSITY=terse -v expected_server_port=1
  run3 "E12-HOST-spoof-pg$v"            $v $v "$F3" "${U[@]}" "${B[@]}" -v HOST=spoofed.example -v expected_host=spoofed.example
  run3 "E13-inject-expected_host-pg$v"  $v $v "$F3" "${U[@]}" "${B[@]}" -v "expected_host=x' OR 'a'='a"
  run3 "E14-inject-timeout-pg$v"        $v $v "$F3" "${U[@]}" "${B[@]}" -v "audit_statement_timeout=30s'; SELECT 'INJECTED"
  run3 "E15-VERSION_NUM-11-pg$v"        $v $v "$F3" "${U[@]}" "${B[@]}" -v VERSION_NUM=110000
  STDIN_FILE="$F3" run3 "E16-stdin-pipe-pg$v" $v $v - "${U[@]}" "${B[@]}"
  run3 "E17-title-and-border0-pg$v"     $v $v "$F3" "${U[@]}" "${B[@]}" -P title=HGS2_AUDIT_COMPLETE -P border=0
  run3 "W1-wrapper-include-trailing-pg$v" $v $v "$M/wrapper_autocommit.sql" "${U[@]}" "${B[@]}"
  run3 "W2-wrapper-begin-include-pg$v"  $v $v "$M/wrapper_begin.sql" "${U[@]}" "${B[@]}"
  run3 "W3-wrapper-begin-include-cli-OES1-pg$v" $v $v "$M/wrapper_begin.sql" -v ON_ERROR_STOP=1 "${U[@]}" "${B[@]}"
  run3 "W4-wrapper-lastline-wronghost-pg$v" $v $v "$M/wrapper_last_line.sql" "${U[@]}" "${B[@]}" -v expected_host=localhost
  # --- TLS (client and server hop; verify-full is client-side only)
  local CA RG R; CA=$(cygpath -m "$S/certs3/ca.crt"); RG=$(cygpath -m "$S/certs3/rogue.crt")
  run3 "T1-loopback-require-pg$v"       $v $v "$F3" -U hgs2_auditor -d "dbname=hgs2_perftest_db sslmode=require" "${B[@]}"
  run3 "T2-loopback-disable-pg$v"       $v $v "$F3" -U hgs2_auditor -d "dbname=hgs2_perftest_db sslmode=disable" "${B[@]}"
  R=(-v expected_host=hgs2-test.local "${B[@]:2}")
  run3 "T3-verify-full-ok-pg$v"         $v $v "$F3" -U hgs2_auditor -d "host=hgs2-test.local hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=verify-full sslrootcert=$CA" "${R[@]}"
  run3 "T4-verify-full-rogue-CA-pg$v"   $v $v "$F3" -U hgs2_auditor -d "host=hgs2-test.local hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=verify-full sslrootcert=$RG" "${R[@]}"
  R=(-v expected_host=wrong-name.example "${B[@]:2}")
  run3 "T5-verify-full-wrong-hostname-pg$v" $v $v "$F3" -U hgs2_auditor -d "host=wrong-name.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=verify-full sslrootcert=$CA" "${R[@]}"
  R=(-v expected_host=fake-remote.example "${B[@]:2}")
  run3 "T6-remote-name-disable-pg$v"    $v $v "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=disable" "${R[@]}"
  run3 "T7-remote-name-disable-allow1-pg$v" $v $v "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=disable" "${R[@]}" -v allow_insecure_transport=1
  ACCEPT="--accept-warning insecure_transport_allowed" run3 "T7b-remote-disable-allow1-accepted-pg$v" $v $v "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=disable" "${R[@]}" -v allow_insecure_transport=1
  run3 "T8-remote-name-disable-allowtrue-pg$v" $v $v "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=disable" "${R[@]}" -v allow_insecure_transport=true
  run3 "T9-remote-name-require-pg$v"    $v $v "$F3" -U hgs2_auditor -d "host=fake-remote.example hostaddr=127.0.0.1 dbname=hgs2_perftest_db sslmode=require" "${R[@]}"
  run3 "T10-loopback-allow1-unneeded-pg$v" $v $v "$F3" "${U[@]}" "${B[@]}" -v allow_insecure_transport=1
}
