| Senaryo | PG12 | PG16 | PG17 | PG18 |
|---|---|---|---|---|
| A01-wrong-db | 3 / wrong_database / **FAIL** | 3 / wrong_database / **FAIL** | 3 / wrong_database / **FAIL** | 3 / wrong_database / **FAIL** |
| A02-prod-db-name | 3 / production_database / **FAIL** | 3 / production_database / **FAIL** | 3 / production_database / **FAIL** | 3 / production_database / **FAIL** |
| A03-missing-host | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** |
| A04-missing-port | 3 / missing_parameter expected_port / **FAIL** | 3 / missing_parameter expected_port / **FAIL** | 3 / missing_parameter expected_port / **FAIL** | 3 / missing_parameter expected_port / **FAIL** |
| A05-missing-srvaddr | 3 / missing_parameter expected_server_addr / **FAIL** | 3 / missing_parameter expected_server_addr / **FAIL** | 3 / missing_parameter expected_server_addr / **FAIL** | 3 / missing_parameter expected_server_addr / **FAIL** |
| A06-missing-srvport | 3 / missing_parameter expected_server_port / **FAIL** | 3 / missing_parameter expected_server_port / **FAIL** | 3 / missing_parameter expected_server_port / **FAIL** | 3 / missing_parameter expected_server_port / **FAIL** |
| A07-missing-sysid | 3 / missing_parameter expected_system_identifier / **FAIL** | 3 / missing_parameter expected_system_identifier / **FAIL** | 3 / missing_parameter expected_system_identifier / **FAIL** | 3 / missing_parameter expected_system_identifier / **FAIL** |
| A08-wrong-host | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| A09-wrong-port | 3 / client_port_mismatch / **FAIL** | 3 / client_port_mismatch / **FAIL** | 3 / client_port_mismatch / **FAIL** | 3 / client_port_mismatch / **FAIL** |
| A10-wrong-srvaddr | 3 / server_addr_mismatch / **FAIL** | 3 / server_addr_mismatch / **FAIL** | 3 / server_addr_mismatch / **FAIL** | 3 / server_addr_mismatch / **FAIL** |
| A11-wrong-srvport | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** |
| A12-wrong-sysid | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** |
| A13-sysid-no-privilege | 3 / system_identifier_unverifiable / **FAIL** | 3 / system_identifier_unverifiable / **FAIL** | 3 / system_identifier_unverifiable / **FAIL** | 3 / system_identifier_unverifiable / **FAIL** |
| A14-superuser | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** |
| A15-superuser-allow0 | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** |
| A16-superuser-allowtrue | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** |
| A17-superuser-allow1 | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) |
| A17b-superuser-allow1-accepted | 0 / COMPLETE / **PASS** (W: superuser_allowed) | 0 / COMPLETE / **PASS** (W: superuser_allowed) | 0 / COMPLETE / **PASS** (W: superuser_allowed) | 0 / COMPLETE / **PASS** (W: superuser_allowed) |
| A18-su-behind-role | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** | 3 / superuser_connection / **FAIL** |
| A19-psql-1 | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A20-psql-1-defaults-RR-RO | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A21-preopen-default | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A22-preopen-RO | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A23-preopen-RR | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A24-preopen-xid | 3 / open_transaction_with_xid / **FAIL** | 3 / open_transaction_with_xid / **FAIL** | 3 / open_transaction_with_xid / **FAIL** | 3 / open_transaction_with_xid / **FAIL** |
| A25-noP2-savepoint | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| A26-preopen-SERIALIZABLE | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A27-preopen-READ-WRITE | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A28-preopen-RC-prior-query | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A29-preopen-same-message | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| A30-member-of-superuser | 3 / superuser_membership / **FAIL** | 3 / superuser_membership / **FAIL** | 3 / superuser_membership / **FAIL** | 3 / superuser_membership / **FAIL** |
| A31-member-of-su-allow1 | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) | 0 / COMPLETE / **FAIL** (W: superuser_allowed) |
| A32-excess-privilege | 0 / COMPLETE / **FAIL** (W: audit_role_excess_privilege) | 0 / COMPLETE / **FAIL** (W: audit_role_excess_privilege) | 0 / COMPLETE / **FAIL** (W: audit_role_excess_privilege) | 0 / COMPLETE / **FAIL** (W: audit_role_excess_privilege) |
| E01-cli-ON_ERROR_STOP0 | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** | 3 / missing_parameter expected_host / **FAIL** |
| E02-mutant-ON_ERROR_STOP-off | 0 / missing_parameter expected_host / **FAIL** | 0 / missing_parameter expected_host / **FAIL** | 0 / missing_parameter expected_host / **FAIL** | 0 / missing_parameter expected_host / **FAIL** |
| E03-ECHO-all | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E04-unaligned-tuples | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E05-expanded | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E06-SINGLESTEP | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E07-AUTOCOMMIT-off | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E08-ON_ERROR_ROLLBACK-on | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E09-FETCH_COUNT-1 | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E10-output-to-file | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E11-VERBOSITY-terse-abort | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** | 3 / server_port_mismatch / **FAIL** |
| E12-HOST-spoof | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| E13-inject-expected_host | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| E14-inject-timeout | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| E15-VERSION_NUM-11 | 3 / psql_too_old / **FAIL** | 3 / psql_too_old / **FAIL** | 3 / psql_too_old / **FAIL** | 3 / psql_too_old / **FAIL** |
| E16-stdin-pipe | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| E17-title-and-border0 | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| F1-forge-unaligned-tuples | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| F2-forge-default | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| K1-WIN1254 | 0 / COMPLETE / **PASS** |  |  | 0 / COMPLETE / **PASS** |
| M1-readwrite-mutant | 3 / tx_not_read_only / **FAIL** | 3 / tx_not_read_only / **FAIL** | 3 / tx_not_read_only / **FAIL** | 3 / tx_not_read_only / **FAIL** |
| M2-wrong-iso-mutant | 3 / tx_not_repeatable_read / **FAIL** | 3 / tx_not_repeatable_read / **FAIL** | 3 / tx_not_repeatable_read / **FAIL** | 3 / tx_not_repeatable_read / **FAIL** |
| M3-noP2-psql-1-RR-RO | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| M4-noP2-noprobe-psql-1-RR-RO | 0 / COMPLETE / **FAIL** | 0 / COMPLETE / **FAIL** | 0 / COMPLETE / **FAIL** | 0 / COMPLETE / **FAIL** |
| M5-noP2-preopen-RR-RO | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| M6-noP2-preopen-SERIALIZABLE | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| M7-noP2-preopen-RC-RO | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** |
| N1-normal | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| N2-psql18 | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |  |
| N3-psql12 |  |  |  | 0 / COMPLETE / **PASS** |
| N4-psql16 |  |  |  | 0 / COMPLETE / **PASS** |
| N5-psql17 |  |  |  | 0 / COMPLETE / **PASS** |
| O1-orig-attack-wrong-params | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| O2-orig-attack-preopen-RR-RO | 3 / isaretcisiz / **FAIL** | 3 / isaretcisiz / **FAIL** | 0 / COMPLETE / **FAIL** | 0 / COMPLETE / **FAIL** |
| O3-stage2-attack-wrong-params | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| O4-stage2-attack-preopen-RR-RO | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| O5-stage2-forge-unaligned | 0 / forged_marker|r|pgadmin|f / **FAIL** | 0 / forged_marker|r|pgadmin|f / **FAIL** | 0 / forged_marker|r|pgadmin|f / **FAIL** | 0 / forged_marker|r|pgadmin|f / **FAIL** |
| R1-standby-primary-sysid | 0 / COMPLETE / **PASS** |  |  | 0 / COMPLETE / **PASS** |
| R2-standby-wrong-sysid | 3 / system_identifier_mismatch / **FAIL** |  |  | 3 / system_identifier_mismatch / **FAIL** |
| R3-standby-psql-1 | 3 / open_transaction / **FAIL** |  |  | 3 / open_transaction / **FAIL** |
| R4-standby-noP2-psql-1 | 3 / isaretcisiz / **FAIL** |  |  | 3 / isaretcisiz / **FAIL** |
| S1-attack-wrong-params | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| S2-attack-preopen-RR-RO | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| S3-attack-correct-params | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| S4-attack-pgoptions-wrong-host | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** | 3 / client_host_mismatch / **FAIL** |
| S5-attack-wrong-sysid-only | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** | 3 / system_identifier_mismatch / **FAIL** |
| T1-loopback-require | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| T2-loopback-disable | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| T3-verify-full-ok | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| T4-verify-full-rogue-CA | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** |
| T5-verify-full-wrong-hostname | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** | 2 / isaretcisiz / **FAIL** |
| T6-remote-name-disable | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** |
| T7-remote-name-disable-allow1 | 0 / COMPLETE / **FAIL** (W: insecure_transport_allowed) | 0 / COMPLETE / **FAIL** (W: insecure_transport_allowed) | 0 / COMPLETE / **FAIL** (W: insecure_transport_allowed) | 0 / COMPLETE / **FAIL** (W: insecure_transport_allowed) |
| T7b-remote-disable-allow1-accepted | 0 / COMPLETE / **PASS** (W: insecure_transport_allowed) | 0 / COMPLETE / **PASS** (W: insecure_transport_allowed) | 0 / COMPLETE / **PASS** (W: insecure_transport_allowed) | 0 / COMPLETE / **PASS** (W: insecure_transport_allowed) |
| T8-remote-name-disable-allowtrue | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** | 3 / insecure_transport / **FAIL** |
| T9-remote-name-require | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| T10-loopback-allow1-unneeded | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** | 0 / COMPLETE / **PASS** |
| W1-wrapper-include-trailing | 0 / isaretcisiz / **FAIL** | 0 / isaretcisiz / **FAIL** | 0 / isaretcisiz / **FAIL** | 0 / isaretcisiz / **FAIL** |
| W2-wrapper-begin-include | 0 / open_transaction / **FAIL** | 0 / open_transaction / **FAIL** | 0 / open_transaction / **FAIL** | 0 / open_transaction / **FAIL** |
| W3-wrapper-begin-include-cli-OES1 | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** | 3 / open_transaction / **FAIL** |
| W4-wrapper-lastline-wronghost | 0 / client_host_mismatch / **FAIL** | 0 / client_host_mismatch / **FAIL** | 0 / client_host_mismatch / **FAIL** | 0 / client_host_mismatch / **FAIL** |
| X1-proxy-loopback | 0 / COMPLETE / **PASS** |  |  | 0 / COMPLETE / **PASS** |
| X2-proxy-expected-server-port | 3 / client_port_mismatch / **FAIL** |  |  | 3 / client_port_mismatch / **FAIL** |
| X3-proxy-remote-name-disable | 3 / insecure_transport / **FAIL** |  |  | 3 / insecure_transport / **FAIL** |
| X4-proxy-remote-name-require | 0 / COMPLETE / **PASS** |  |  | 0 / COMPLETE / **PASS** |
