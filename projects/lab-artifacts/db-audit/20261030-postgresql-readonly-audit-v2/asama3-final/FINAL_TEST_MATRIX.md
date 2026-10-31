# FINAL_TEST_MATRIX — HGS2 PostgreSQL Read-Only Audit V2 (3. aşama)

- **Test edilen dosya:** `asama3-final/postgresql_readonly_audit_v2.sql`
- **SHA-256:** `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`
  - Test başında: 2026-10-30T18:24:12+03:00
  - Test sonunda: 2026-10-30T18:33:02+03:00 (aynı)
- Her çalıştırmanın hash'i `kanit/runs-final/<id>/script.sha256` içinde. Doğrudan bu dosyayı yürüten çalıştırma sayısı 286; 4 stdin çalıştırması da aynı dosyayı borudan okudu.
- **Ortam:** Yalnızca geçici, izole test kümeleri kullanıldı (scratchpad; yalnızca 127.0.0.1; `trust` + `ssl=on`, sentetik CA). Sentetik veri.
- **Gerçek sistemler:** `hibrit_giris_db`, `hgs2_perftest_db` ve 5432'deki PG 18 servisi KULLANILMADI.

## 1. PostgreSQL sunucu sürüm matrisi

| Sunucu | Kaynak | Primary portu | Fiziksel replika | Durum |
|---|---|---|---|---|
| 12.22 | EDB taşınabilir zip | 55412 | 55422 (`pg_basebackup -R`) | Test edildi |
| 13.x / 14.x / 15.x | — | — | — | **TEST EDİLMEDİ** |
| 16.15 | EDB taşınabilir zip | 55416 | — | Test edildi |
| 17.11 | EDB taşınabilir zip | 55417 | — | Test edildi |
| 18.6 | Kurulu ikili dosyalar, ayrı `initdb` | 55418 | 55428 (`pg_basebackup -R`) | Test edildi |

## 2. psql istemci sürüm matrisi (tam denetim, PASS)

| psql \ sunucu | 12 | 16 | 17 | 18 |
|---|---|---|---|---|
| 12 | N1 PASS | — | — | N3 PASS |
| 16 | — | N1 PASS | — | N4 PASS |
| 17 | — | — | N1 PASS | N5 PASS |
| 18 | N2 PASS | N2 PASS | N2 PASS | N1 PASS |
| 10 / 11 | Betik reddeder (E15: `psql_too_old`, VERSION_NUM taklidiyle) — gerçek ikili dosyayla **test edilmedi** | | | |
| 13 / 14 / 15 | **TEST EDİLMEDİ** | | | |

Yalnızca Windows ikili dosyaları kullanıldı.

## 3. Senaryo × sürüm sonuçları

Hücre biçimi: `psql çıkış kodu / işaretçi (ABORT nedeni, COMPLETE veya işaretçisiz) / doğrulayıcı kararı (W: uyarı)`.

- Doğrulayıcı: `tools/validate_audit_result.py`.
- 344 senaryonun 344'ü önceden tanımlanmış beklentiyle eşleşti (`kanit/runs-final/EVALUATION.txt`).
- `O*` satırları karşılaştırma içindir: orijinal V2 (`726771…`) ve 2. aşama sonu (`b8eb…`). Beklenti değerlendirmesine dahil değildir.

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
| O5-stage2-forge-unaligned | 0 / forged_marker / **FAIL** | 0 / forged_marker / **FAIL** | 0 / forged_marker / **FAIL** | 0 / forged_marker / **FAIL** |
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

### Kodlar
- **N:** Normal / psql çapraz.
- **A01–A13:** Hedef ve kimlik.
- **A14–A18, A30–A32:** Süper kullanıcı ve en az yetki.
- **A19–A29, M1–M7:** Transaction.
  - A25 ve M3–M7: P2'nin kaldırıldığı mutasyonlar; yalnızca P3 sondası.
  - M4: P2 **ve** sonda kaldırılmış mutasyon. Yanlış başarının geri geldiğini, yani sondanın gerekliliğini gösterir.
- **E:** Hata yönetimi, psql değişkenleri, otomasyon.
- **W:** `\i` sarmalayıcı.
- **T:** TLS. T4/T5'te istemci bağlantıyı reddeder, çıkış 2.
- **X:** Gerçek TCP proxy (127.0.0.1:55499 → primary).
- **R:** Fiziksel replika.
- **S:** search_path / nesne gölgeleme saldırısı.
- **F:** İşaretçi sahteciliği.
- **K:** WIN1254 istemci kodlaması.

## 4. Ek ölçümler

| Ölçüm | Sonuç | Kanıt |
|---|---|---|
| Parser (pglast 8.7 / libpg_query PG 18.6) | 81 SQL parçası, 0 sözdizimi hatası; ifade türleri SelectStmt 73, TransactionStmt 2, VariableSetStmt 5, VariableShowStmt 1 | `kanit/runs-final/QA_FINAL.txt` |
| Statik QA (B1–B18) | Tehlikeli meta-komut yok; `\if`/`\endif` 39/39; tanımsız veya kullanılmayan değişken yok; 26 ABORT bloğu doğru biçimde; COMPLETE tek ve son; ASCII dışı ifade içeriği yok; yazma anahtar sözcüğü yok; search_path penceresi dışında nitelenmemiş fonksiyon/operatör yok; literal'lerde `\` yok; izin listeleri eşit; `= NULL` yok | aynı |
| Katalog doğrulamaları | 18 tam çıktı × 33 doğrulama = 33/33 her birinde; sızıntı 0 | `kanit/runs-final/CATALOG_ASSERTIONS.txt` |
| Salt okunurluk (önce/sonra) | 4 sürüm × (şema, globals, durum) = 12/12 karşılaştırmada 0 fark | `kanit/runs-final/READONLY_SNAPSHOT_DIFF.txt` |
| Saldırı/sahtecilik/kodlama sonrası geri dönüş | 12/12 karşılaştırmada 0 fark; temizlik sayaçları 0 | `STATE_RESTORED_AFTER_SPECIAL.txt`, `CLEANUP.txt` |
| Sunucu günlüğü (`log_statement=all`) | İzin dışı ifade 0; hata sonrası betik ifadesi 0 (yalnızca psql'in `-1` kapanış COMMIT/ROLLBACK'i) | `kanit/runs-final/LOG_ANALYSIS.txt` |
| TLS sınıflama birim testi | 19 girdi × 2 sürüm = 38/38; ifade metni betikle aynı | `kanit/runs-final/TLS_UNIT.txt` |
| Doğrulayıcı öz-testi | 16/16 | `kanit/runs-final/VALIDATOR_SELFTEST.txt` |
| Gizli değer taraması | Karşılaştırma dışı 344 çalıştırmada stdout+stderr'de 7 sentetik gizli değerden 0 | `EVALUATION.txt` |
