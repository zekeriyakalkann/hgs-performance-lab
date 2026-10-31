| Senaryo | PG12 | PG16 | PG17 | PG18 |
|---|---|---|---|---|
| A01-wrong-db | 3 / wrong_database | 3 / wrong_database | 3 / wrong_database | 3 / wrong_database |
| A02-prod-db-name | 3 / production_database | 3 / production_database | 3 / production_database | 3 / production_database |
| A03-missing-host | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host |
| A04-missing-port | 3 / missing_parameter expected_port | 3 / missing_parameter expected_port | 3 / missing_parameter expected_port | 3 / missing_parameter expected_port |
| A05-missing-srvaddr | 3 / missing_parameter expected_server_addr | 3 / missing_parameter expected_server_addr | 3 / missing_parameter expected_server_addr | 3 / missing_parameter expected_server_addr |
| A06-missing-srvport | 3 / missing_parameter expected_server_port | 3 / missing_parameter expected_server_port | 3 / missing_parameter expected_server_port | 3 / missing_parameter expected_server_port |
| A07-missing-sysid | 3 / missing_parameter expected_system_identifier | 3 / missing_parameter expected_system_identifier | 3 / missing_parameter expected_system_identifier | 3 / missing_parameter expected_system_identifier |
| A08-wrong-host | 3 / client_host_mismatch | 3 / client_host_mismatch | 3 / client_host_mismatch | 3 / client_host_mismatch |
| A09-wrong-port | 3 / client_port_mismatch | 3 / client_port_mismatch | 3 / client_port_mismatch | 3 / client_port_mismatch |
| A10-wrong-srvaddr | 3 / server_addr_mismatch | 3 / server_addr_mismatch | 3 / server_addr_mismatch | 3 / server_addr_mismatch |
| A11-wrong-srvport | 3 / server_port_mismatch | 3 / server_port_mismatch | 3 / server_port_mismatch | 3 / server_port_mismatch |
| A12-wrong-sysid | 3 / system_identifier_mismatch | 3 / system_identifier_mismatch | 3 / system_identifier_mismatch | 3 / system_identifier_mismatch |
| A13-sysid-no-privilege | 3 / system_identifier_unverifiable | 3 / system_identifier_unverifiable | 3 / system_identifier_unverifiable | 3 / system_identifier_unverifiable |
| A14-superuser | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection |
| A15-superuser-allow0 | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection |
| A16-superuser-allowtrue | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection |
| A17-superuser-allow1 | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
| A18-su-behind-role | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection | 3 / superuser_connection |
| A19-psql-1 | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction |
| A20-psql-1-defaults-RR-RO | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction |
| A21-preopen-tx | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction |
| A22-preopen-RO-tx | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction |
| A23-preopen-RR-tx | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction | 3 / open_transaction |
| A24-preopen-tx-with-xid | 3 / open_transaction_with_xid | 3 / open_transaction_with_xid | 3 / open_transaction_with_xid | 3 / open_transaction_with_xid |
| A25-preopen-savepoint | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz |
| E1-cli-ON_ERROR_STOP0 | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host | 3 / missing_parameter expected_host |
| E2-mutant-ON_ERROR_STOP-off | 0 / missing_parameter expected_host | 0 / missing_parameter expected_host | 0 / missing_parameter expected_host | 0 / missing_parameter expected_host |
| M1-readwrite-mutant | 3 / tx_not_read_only | 3 / tx_not_read_only | 3 / tx_not_read_only | 3 / tx_not_read_only |
| M2-wrong-iso-mutant | 3 / tx_not_repeatable_read | 3 / tx_not_repeatable_read | 3 / tx_not_repeatable_read | 3 / tx_not_repeatable_read |
| M3-noP2-psql-1-RR-RO | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz |
| M4-noP2-noprobe-psql-1-RR-RO | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
| M5-noP2-preopen-RR | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz | 3 / isaretcisiz |
| N1-normal | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
| N2-psql18 | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |  |
| N3-psql12 |  |  |  | 0 / COMPLETE |
| T1-sslmode-require | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
| T2-sslmode-disable | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE | 0 / COMPLETE |
