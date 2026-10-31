# FINAL_SECURITY_AUDIT — HGS2 PostgreSQL Read-Only Audit V2 (3. aşama: bağımsız denetim)

- Tarih: 2026-10-30 (+03:00)
- İlgili belgeler: `CHANGELOG_FINAL.md`, `FINAL_TEST_MATRIX.md`, `KNOWN_LIMITATIONS.md`, `FINAL_SHA256SUMS.txt`
- Kanıt: `kanit/` (çalıştırma çıktıları, anlık görüntüler, sunucu günlükleri, test düzeneği)

---

## 1. Proje özeti

`postgresql_readonly_audit_v2.sql`, HGS2'nin test veritabanı (`hgs2_perftest_db`) ile üretim veritabanı (`hibrit_giris_db`) arasındaki izolasyonu PostgreSQL sistem katalogları üzerinden **salt okunur** biçimde denetleyen bir psql betiğidir.

Betik:
- Hedefi doğrular: veritabanı adı, host ve port, sunucu adresi ve portu, system_identifier.
- Bağlantıyı doğrular: TLS ve en az yetki.
- Tek bir REPEATABLE READ, READ ONLY transaction içinde rol, ACL, ayar ve şema bilgisini raporlar.
- Sonucu makinece okunabilir işaretçilerle bildirir.

Aşama geçmişi:
- **1. aşama** (v1, `3423053a…`): ilk betik, değişmedi.
- **2. aşama** (`726771…` → `b8eb2ac6…`): transaction sondası, search_path sabitleme, zorunlu sistem kimliği, TLS raporu.
- **3. aşama** (bu rapor, `b8eb2ac6…` → `5916d12b…`): bağımsız yeniden denetim, 9 düzeltme, nihai test turu.

## 2. Denetim kapsamı

**Yöntem:**
- Dosyanın tamamı yeniden okundu; önceki düzeltmelerin hiçbiri doğru kabul edilmedi.
- Her hipotez önce **2. aşama dosyası** üzerinde gerçek PostgreSQL'de denendi (keşif turu, `kanit/runs-discovery/`).
- Gerçek bulgular düzeltildi.
- Son dosya dört sürümde baştan test edildi.

**İncelenen alanlar:**
- search_path ve nesne gölgeleme: operatör, fonksiyon, tip, cast çözümleme; psql değişken aktarımı.
- Transaction güvenliği: P2/P3, `psql -1`, önceden açık transaction'lar, `\i` ve sarmalayıcı.
- Hedef ve sistem kimliği: proxy ve replika dahil.
- Süper kullanıcı ve en az yetki.
- TLS: istemci atlaması dahil.
- Gizli değer sızıntısı.
- Katalog sorguları: 18 katalog.
- Salt okunurluk.
- Hata yönetimi ve otomasyon: çıkış kodu, stdout/stderr, psql değişkenleri, `-o`.
- Sürüm uyumluluğu.

**Katalog incelemesi:**
- `pg_roles`, `pg_auth_members` (PG16+ `inherit_option`/`set_option` dalı), `pg_database`, `pg_namespace`, `pg_class`, `pg_attribute`, `pg_constraint`, `pg_proc`, `pg_trigger`, `pg_event_trigger`, `pg_extension`, `pg_policy`, `pg_default_acl`, `pg_db_role_setting`, `pg_largeobject_metadata` ve `pg_depend` sorgularında JOIN koşulları, filtreler, nesne kapsamı ve sürüm sütunları incelendi.
- `pg_index` ve `pg_sequence` bilerek kullanılmıyor: identity ve serial ayrımı `pg_depend.deptype` ('i' / 'a') ile `pg_attribute.attidentity` üzerinden yapılıyor; referans kısıtlar `pg_constraint` ile sayılıyor. Bu yaklaşım katalog doğrulamalarıyla dört sürümde doğrulandı.
- Bulunan doğruluk sorunları: N6 (sahiplik ve etkin yetki ayrımı) ve N7 (rol yokken sequence'ların gizlenmesi). İkisi de düzeltildi.

**Saldırgan modeli:** Denetim oturumunun search_path'ini (rol veya veritabanı ayarı ya da PGOPTIONS ile) etkileyebilen ve bir şemada nesne oluşturabilen, ama süper kullanıcı **olmayan** bir taraf. Örnek: test veritabanının sahibi.

## 3. Önceki aşamalardan gelen bulgular (bağımsız olarak yeniden doğrulandı)

| Bulgu (2. aşama) | 3. aşamadaki bağımsız doğrulama |
|---|---|
| G1 transaction sondası | Korunuyor: P2 kaldırılınca sonda tek başına durduruyor (A25, M3, M5, M6 SERIALIZABLE, M7, R4 replika). İkisi birden kaldırılınca yanlış başarı geri geliyor (M4). |
| G2 search_path gölgeleme | 2. aşama düzeltmesi daha güçlü bir saldırıya da dayandı: 10 sahte operatör (text, name, int4, timestamptz, inet) ve 6 sahte fonksiyon, kalıcı rol ayarıyla (O3/O4, 4 sürüm). |
| G3 sistem kimliği zorunlu | Korunuyor (A07, A12, A13, R2). |
| G4 süper kullanıcı | Doğrudan ve rol ayarı arkası korunuyor (A14–A18); **üyelik yolu açık bulundu → N2**. |
| G5 TLS | Raporlama doğru; **son-atlama körlüğü bulundu → N3**. |
| G6/G7 kodlama ve FETCH_COUNT | Korunuyor (K1, E09). |

## 4. Yeni tespit edilen bulgular (3. aşama)

Bulgular 2. aşama dosyası (`b8eb2ac6…`) üzerinde gerçek çalıştırmayla doğrulandı.

| # | Bulgu | Önem | Kanıt (2. aşama dosyası) |
|---|---|---|---|
| N1 | 2. aşamada eklenen 5.11 `proconfig`, 5.15 politika ifadesi ve 5.14b `srvoptions` sorguları gizli değer ve bağlantı bilgisi basıyor | Yüksek | D01: `SENTETIK-TOKEN-FN`, `SENTETIK-TOKEN-POL`, `sentetik-prod-host.invalid` açık metin; O5 (4 sürüm) |
| N2 | Süper kullanıcı bir role ÜYE olan denetim rolü kabul ediliyor | Yüksek | D02 → 0 / PASS |
| N3 | TLS kapısı yalnızca son atlamayı görüyor; uzak ad + yerel proxy ile TLS'siz bağlantı kabul ediliyor | Orta-Yüksek | D04 → 0 / PASS (`tasima= tcp-loopback tls= f`) |
| N4 | Çıktı biçimi sabit değil: `-A` ile nesne adındaki satır sonu sütun 0'da sahte ABORT üretiyor; `ECHO=all` sonucu bozuyor | Orta | D17/D18, O5 (4 sürüm) → `forged_marker`; D06 |
| N5 | Denetim rolünün kendi kalıcı ayarları (ör. kötü niyetli search_path) raporlanmıyor | Orta | Bölüm 4 WHERE koşulu |
| N6 | 5.4a sahiplik / doğrudan ACL / PUBLIC / dolaylı ayrımını yapmıyor; yorum "sahip = tüm yetkiler" diyor | Doğruluk | Statik |
| N7 | 5.5b, `hgs2_perftest` rolü yoksa sequence'ları gizliyor | Doğruluk | Statik |
| N8 | psql 10/11 test edilmeden kabul ediliyor | Doğruluk | — |
| N9 | Komut satırında ON_ERROR_STOP olmadan sarmalayıcının son satırında `\i` ile çağrılınca durdurma çıkış kodu 0 | Orta (kullanım) | W2/W4 (4 sürüm); psql davranışı |

**Bulgu olmayan ve doğrulanan noktalar:**
- `-v HOST=…` ile istemci host sahteciliği yapılamıyor; psql bağlantıda değeri eziyor (E12).
- `expected_host` ve `audit_statement_timeout` üzerinden SQL enjeksiyonu engelleniyor (E13, E14).
- Önceden açık SERIALIZABLE, READ WRITE, önceki sorgulu ve aynı mesajda `BEGIN; SELECT` transaction'ları yakalanıyor (A26–A29).
- `AUTOCOMMIT=off`, `ON_ERROR_ROLLBACK=on`, `FETCH_COUNT=1`, `SINGLESTEP`, stdin ve `-o` denetimi bozmuyor (E06–E10, E16).

## 5. Düzeltilen açıklar

Ayrıntı (satırlar, önceki ve yeni davranış): `CHANGELOG_FINAL.md`.

| Düzeltme | Bulgu | Doğrulama (son dosya, 4 sürüm) |
|---|---|---|
| U1 çıktı biçimi sabitleme | N4 | F1: sahte nesnelerle `-A -t` → sütun 0'da 0 sahte satır, PASS; E03/E04/E05/E17 PASS |
| U2 psql ≥ 12 | N8 | E15 → `psql_too_old` |
| U3 echo temizleme | N4 | QA B18 |
| U4 TLS istemci atlaması + uyarı işaretçisi | N3 | T6, X3 → `insecure_transport`; T7 → WARNING ve FAIL; T7b kabulle PASS; T8 reddedildi; T9, X4 PASS |
| U5 süper kullanıcı üyeliği + en az yetki uyarısı | N2 | A30 → `superuser_membership`; A31, A32 → WARNING ve FAIL |
| U6 denetim rolü ayarları | N5 | S3: `hgs2_auditor | search_path | evil, pg_catalog | t` raporlanıyor |
| U7 yetki kaynağı | N6 | Katalog doğrulamaları (dogrudan ACL / dolayli / -) |
| U8 5.5b LEFT JOIN | N7 | Statik; mevcut senaryolarda sonuç değişmedi |
| U9 maskeleme | N1 | Karşılaştırma dışı 344 çalıştırmada 7 sentetik gizli değerden 0 |
| Başlık: ON_ERROR_STOP komut satırında zorunlu | N9 | W3 → 3; doğrulayıcı W2/W4'ü FAIL sayıyor |

## 6. Kalan riskler

Tam liste: `KNOWN_LIMITATIONS.md`. Özet:
1. **verify-full kanıtlanamaz.** TLS sertifikası ve ana bilgisayar adı doğrulaması SQL ile kanıtlanamaz; doğru bağlantı dizesi operatörün sorumluluğundadır.
2. **system_identifier ayırt edici değil.** Replika ve klon ayırt edilemez; yalnızca recovery durumu raporlanır.
3. **P3 sondası işaretçisiz durdurur.** Çıkış kodu tek başına yeterli değildir (N9); doğrulayıcının yedi kuralı birlikte uygulanmalıdır.
4. **Süper kullanıcı düzeyinde ele geçirme kapsam dışıdır.**
5. **Test edilmemiş sürüm ve platformlar:** PG 13/14/15, psql 13/14/15, Linux, unix soketi, gerçek pooler, SCRAM channel binding.

## 7. PostgreSQL sürüm matrisi

| Sunucu | Primary | Replika | Sonuç |
|---|---|---|---|
| 12.22 | Tüm çekirdek senaryolar (73) + saldırı, sahtecilik, kodlama, proxy | R1–R4 | Beklentiyle uyumlu |
| 16.15 | Tüm çekirdek senaryolar + saldırı, sahtecilik | — | Beklentiyle uyumlu |
| 17.11 | Tüm çekirdek senaryolar + saldırı, sahtecilik | — | Beklentiyle uyumlu |
| 18.6 | Tüm çekirdek senaryolar + saldırı, sahtecilik, kodlama, proxy | R1–R4 | Beklentiyle uyumlu |
| 13 / 14 / 15 | **TEST EDİLMEDİ** | | |

Sürüme bağlı kod yolları:

| Kod yolu | 12 | 16 | 17 | 18 |
|---|---|---|---|---|
| `txid_current_if_assigned` (P2, sunucu < 13) | ✓ (A24) | | | |
| `pg_current_xact_id_if_assigned` (sunucu 13+) | | ✓ | ✓ | ✓ |
| 2.3 `pg_auth_members` 12–15 dalı | ✓ | | | |
| 2.3 PG16+ dalı (`inherit_option`, `set_option`) | | ✓ | ✓ | ✓ |
| 5.4b MAINTAIN | bilgi satırı | bilgi satırı | ✓ | ✓ |
| `pg_control_system()` | ✓ | ✓ | ✓ | ✓ |
| Identity sorguları | ✓ | ✓ | ✓ | ✓ |

Hepsi katalog doğrulamalarıyla 33/33 geçti.

## 8. psql sürüm matrisi

| psql \ sunucu | 12 | 16 | 17 | 18 |
|---|---|---|---|---|
| 12 | PASS | — | — | PASS |
| 16 | — | PASS | — | PASS |
| 17 | — | — | PASS | PASS |
| 18 | PASS | PASS | PASS | PASS |

- psql 10/11 betik tarafından reddediliyor (yalnızca `VERSION_NUM` taklidiyle test edildi).
- psql 13/14/15 **test edilmedi**.

## 9. TLS test sonuçları

Ortam: sentetik CA. Sunucu sertifikasında SAN `DNS:hgs2-test.local, IP:127.0.0.1` var; ayrıca sahte bir CA hazırlandı. Uzak host adı `hostaddr=127.0.0.1` ile benzetildi, böylece hiçbir test kümesi ağa açılmadı.

| Test | Sonuç (4 sürüm) | Gösterdiği |
|---|---|---|
| T1 loopback, `sslmode=require` | PASS, `tls= t TLSv1.3` | 1. güvence (şifreleme) sunucuda görülüyor |
| T2 loopback, `disable` | PASS, `tls= f` | Uçtan uca yerel bağlantı TLS'siz kabul |
| T3 `verify-full`, doğru CA ve ad | PASS | 2. ve 3. güvence istemcide sağlandı |
| T4 `verify-full`, sahte CA | psql çıkış 2: `SSL error: certificate verify failed` | 2. güvenceyi uygulayan istemci |
| T5 `verify-full`, yanlış ad | çıkış 2: `server certificate for "hgs2-test.local" … does not match host name "wrong-name.example"` | 3. güvenceyi uygulayan istemci |
| T3 ile T9 (aynı yol, `require`) | SQL'in gördüğü TLS satırı **birebir aynı** (4 sürüm) | verify-full SQL'den kanıtlanamaz |
| T6 uzak ad, `disable` | 3 / `insecure_transport` | U4 |
| T7 / T7b `allow_insecure_transport=1` | 0 + `HGS2_AUDIT_WARNING: insecure_transport_allowed`; doğrulayıcı FAIL, açıkça kabul edilince PASS | İzin açık ve görünür |
| T8 `allow_insecure_transport=true` | 3 / `insecure_transport` | Yalnızca tam "1" kabul ediliyor |
| T10 loopback + gereksiz bayrak | PASS + "gerekmedi" bilgisi | Bayrak gereksizse uyarı üretmiyor |
| X1–X4 gerçek TCP proxy (PG 12, 18) | X1 PASS + port farkı bilgisi; X2 `client_port_mismatch`; X3 `insecure_transport`; X4 PASS | Proxy arkasında doğru yorumlama |
| Birim testi | 19 girdi × 2 sürüm = 38/38 | Sınıflama ifadesi |

**`allow_insecure_transport` kapsamı:** Yalnızca P6b kararını etkiler (QA B16: okunduğu yerler yalnızca 634, 636 ve 638. satırlar; hepsi P6b sorgusunda; `allow_superuser` yalnızca 726. satırda, P8'de). Devreye girdiğinde uyarı işaretçisi yazılır. Gerekmediğinde yalnızca bilgi satırı yazılır.

## 10. Transaction test sonuçları

Hepsi 4 sürümde ölçüldü.

| Senaryo | Sonuç | Engelleyen katman |
|---|---|---|
| Normal `psql -f` (N1) | PASS | — |
| `psql -1` (A19), RR/RO varsayılanlarıyla (A20) | 3 / `open_transaction` | P2 |
| Önceden açık: varsayılan, READ ONLY, REPEATABLE READ, SERIALIZABLE, READ WRITE, önceki sorgulu, aynı mesajda (A21–A23, A26–A29) | 3 / `open_transaction` | P2 |
| Önceden atanmış xid (A24) | 3 / `open_transaction_with_xid` | P2, zamandan bağımsız |
| P2 kaldırılmış: SAVEPOINT, `-1`+RR/RO, RR RO, SERIALIZABLE RO, RC RO (A25, M3, M5–M7) | 3, işaretçisiz (`SET TRANSACTION ISOLATION LEVEL must be called before any query`) | P3 sondası |
| P2 ve sonda kaldırılmış (M4) | **0 / COMPLETE**; stderr'deki WARNING yüzünden doğrulayıcı FAIL | Sondanın gerekliliğinin kanıtı |
| READ WRITE (M1), yanlış izolasyon (M2) | `tx_not_read_only` / `tx_not_repeatable_read` | P4 |
| Replika: `-1` (R3), P2'siz `-1` (R4) | `open_transaction` / sonda | Hot standby'da da çalışıyor |
| Sarmalayıcı `\i` (W1–W4) | W1 FAIL (COMPLETE son satır değil); W2/W4 çıkış 0 + ABORT, doğrulayıcı FAIL; W3 (belgelenen komut satırı) çıkış 3 | N9 |
| Saldırı altında önceden açık RR RO (S2) | 3 / `open_transaction` | P2 (nitelenmiş operatörler) |

- **Zaman manipülasyonu:** `now()` istemci tarafından değiştirilemez. Zaman ipucunun yanılması deterministik üretilemediği için P2'yi kaldıran mutasyonlarla sondanın tek başına yeterliliği gösterildi.
- **Etkileşimli (TTY) kullanım** test edilmedi; etkileri `KNOWN_LIMITATIONS.md` madde 9'da.
- **REPEATABLE READ anlık görüntü tutarlılığı** ve READ ONLY'nin yazmayı reddetmesi 2. aşamada ayrıca gösterildi.

## 11. search_path saldırı testleri

**Saldırı** (`kanit/harness/evil_full_setup.sql`):
- `evil` şemasında 10 sahte operatör: `=` (text,text / name,text / name,name / timestamptz), `<>` (3 varyant), `>=` (int4), `<<=` (inet), `||` (text).
- 6 sahte fonksiyon: `current_setting`, `current_database`, `now`, `pg_is_in_recovery`, `host`, `inet_server_addr`.
- Kalıcı vektör: `ALTER ROLE hgs2_auditor IN DATABASE hgs2_perftest_db SET search_path = evil, pg_catalog`. S4'te buna ek olarak PGOPTIONS kullanıldı.

| Test | Orijinal V2 (`726771…`) | 2. aşama (`b8eb…`) | **Son dosya** |
|---|---|---|---|
| Yanlış host, port ve sistem kimliği | PG17/18: **0 / COMPLETE / PASS** (tam bypass, gizli değerler açık metin); PG16: yanlış host ve kimlik kabul edildi, gizli değerler basıldı, sonra ilgisiz bir hatayla düştü; PG12: sahte `>=` sürüm dalını bozdu, P2'de hata (koruma değil) | 3 / `client_host_mismatch` | **3 / `client_host_mismatch` (S1)** |
| Önceden açık RR RO + saldırı | PG17/18: 0 / COMPLETE (yalnızca stderr kuralı yakaladı) | 3 / `open_transaction` | **3 / `open_transaction` (S2)** |
| Doğru parametreler + saldırı | — | PASS | **PASS; maskeleme sağlam; denetim rolünün kötü niyetli search_path'i raporda (S3)** |
| PGOPTIONS + yanlış host | — | — | **3 / `client_host_mismatch` (S4)** |
| Yalnızca yanlış sistem kimliği (text = text gölgeleniyor) | — | — | **3 / `system_identifier_mismatch` (S5)** |

**Statik güvence** (QA B11, B12, B15):
- `SET LOCAL search_path = pg_catalog, pg_temp` penceresi dışında (P1, P2 ve son kontrol) nitelenmemiş fonksiyon veya operatör yok; tüm operatörler `OPERATOR(pg_catalog.…)`, tipler `pg_catalog.int4` olarak nitelenmiş.
- Pencere içinde çözümleme yalnızca `pg_catalog` üzerinden yapılıyor. pg_temp fonksiyon ve operatör için aranmıyor; tablo ve tip için en sonda.
- Literallerde ters eğik çizgi yok (`standard_conforming_strings` saldırısına karşı); `= NULL` yok (`transform_null_equals`).
- psql değişkenleri SQL'e yalnızca `:'var'` ile, yani güvenli literal olarak aktarılıyor (E13/E14).
- Cast yaratmak ve varsayılan operatör sınıfı tanımlamak süper kullanıcı gerektirdiği için saldırgan modelinin dışında.

## 12. Salt okunurluk kanıtları

1. **Statik:**
   - Parser'a göre ifade türleri yalnızca SELECT, BEGIN/ROLLBACK, SET (TRANSACTION/LOCAL) ve SHOW.
   - SELECT…INTO, FOR UPDATE ve veri değiştiren CTE yok.
   - Yan etkili fonksiyon yok: nextval/setval, lo_*, pg_advisory*, set_config, dblink, pg_read_file, pg_terminate_backend, txid_current vb.
   - Tehlikeli meta-komut yok: `\!`, `\o`, `\w`, `\copy`, `\g dosya`, `\gexec`, `\setenv`, `\i`, `\c`, `\lo_*`.
   - Kaynak: `QA_FINAL.txt`.
2. **Sunucu günlüğü** (`log_statement=all`, 6 küme):
   - Betiğin SELECT/WITH dışında gönderdiği ifadeler yalnızca şu 9 tam metin: `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;`, `SET TRANSACTION ISOLATION LEVEL READ COMMITTED;`, `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;`, `SET LOCAL search_path = pg_catalog, pg_temp;`, `SET LOCAL statement_timeout = '…';`, `SET LOCAL lock_timeout = '…';`, `SHOW transaction_read_only;`, `ROLLBACK;`, `set client_encoding to 'UTF8'` (`\encoding`).
   - **İzin dışı ifade: 0.** Hatadan sonra betiğin çalıştırdığı ifade: 0.
   - Kaynak: `LOG_ANALYSIS.txt`.
3. **Anlık görüntüler:**
   - Tüm çekirdek, çapraz, proxy ve replika çalıştırmalarından önce ve sonra alındı: `pg_dump -s` (şema ve ACL), `pg_dumpall -g` (roller, üyelikler, rol ayarları), tablo verisi md5'i, sequence son değerleri, LO metadata'sı, `pg_db_role_setting`, veritabanı ACL'leri, namespace'ler, fonksiyon sayıları, politikalar, varsayılan ACL'ler, FDW sunucuları, user mapping sayısı, `pg_control_system` ACL'si.
   - Sonuç: **12/12 karşılaştırmada 0 fark.**
   - Kaynak: `READONLY_SNAPSHOT_DIFF.txt`.
4. **Geçici nesne ve kilit:**
   - Geçici nesne oluşturulmuyor; namespace listesi değişmedi.
   - Advisory lock fonksiyonu kullanılmıyor.
   - Salt okunur transaction'da geçici tablo oluşturmanın bile reddedildiği 2. aşamada gösterildi.
5. **SET'lerin kapsamı:** Tamamı transaction yerel (SET LOCAL / SET TRANSACTION) ve ROLLBACK ile geri alınıyor. Yalnızca `client_encoding` oturumluk; veritabanına yazmıyor.

## 13. Başarı ve hata işaretçisi doğrulaması

Başvuru doğrulayıcısı: `tools/validate_audit_result.py`. PASS için yedi kuralın tümü gerekir:
1. çıkış kodu 0;
2. stderr boş;
3. son satır tam olarak `HGS2_AUDIT_COMPLETE`;
4. COMPLETE tam bir kez;
5. PREFLIGHT_OK tam bir kez ve COMPLETE'ten önce;
6. sütun 0'da `HGS2_AUDIT_ABORT:` yok;
7. kabul edilmemiş `HGS2_AUDIT_WARNING:` yok.

Doğrulama:
- **Gerçek çalıştırmalar:** 344 senaryonun her biri bu doğrulayıcıyla değerlendirildi; 344/344 önceden bildirilen kararla eşleşti.
  - Başarısız her senaryoda (ABORT, işaretçisiz 3, çıkış 2, uyarı, sarmalayıcı) doğrulayıcı FAIL verdi.
  - Bir güvenlik kontrolünün başarısız olduğu hiçbir senaryoda PASS çıkmadı.
- **Sentetik uç durumlar:** 16/16 (çift COMPLETE, girintili COMPLETE, eksik PREFLIGHT, çıkış 0 ile ABORT, kabul edilmiş/edilmemiş uyarı, boş stdout, stderr'de yalnızca WARNING).
- **Kanal ayrımı:**
  - Durdurmalarda işaretçi hem stdout'ta (`\echo`) hem stderr'de (hata mesajı) bulunuyor; `VERBOSITY=terse` altında da (E11).
  - `-o` ile sonuçlar dosyaya gidiyor, işaretçiler stdout'ta kalıyor (E10).
  - Betik `\qecho` kullanmıyor.
- **Sahtecilik:** Çıktı biçimi sabitlendiği için sorgu sonuçları sütun 0'a ulaşamıyor (F1, E04, E05, E17).

## 14. Nihai SHA-256

| Dosya | SHA-256 |
|---|---|
| `asama3-final/postgresql_readonly_audit_v2.sql` (87 879 bayt, 1 630 satır, UTF-8, LF, BOM yok) | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` |
| Test başı / test sonu kaydı | aynı (`kanit/runs-final/FILE_UNDER_TEST_START.sha256`, `…_END.sha256`) |
| 2. aşama dosyası (çalışma dizininde, değişmedi) | `b8eb2ac69b04ddc9ab6407798bf490a9bf80dccb32abf5fb96118b52fd1db841` |
| V1 (değişmedi; boyut 24 630, mtime 2026-10-30 01:12:41.581) | `3423053a254ca6ff361631562e9e9a26e112fddd4e4ea5a5a9b539c0e984c7ff` |
| `asama2-kanit/` | SHA256SUMS.txt'deki 743 dosyanın tamamı doğrulandı |

Teslimattaki diğer tüm dosyalar: `FINAL_SHA256SUMS.txt`.

## 15. Test edilmemiş senaryolar

Ayrıntı: `KNOWN_LIMITATIONS.md` D bölümü.
- PG 13/14/15 sunucuları; psql 10/11 (gerçek ikili) ve 13/14/15
- Linux derlemeleri
- Unix soketi
- Gerçek pgbouncer/pgpool (yalnızca TCP proxy ile test edildi)
- SCRAM + `channel_binding=require`
- Loopback dışı gerçek ağ (yalnızca `hostaddr` ile benzetildi)
- Etkileşimli TTY oturumu
- PG17+ `login` event trigger'ı
- `*_preload_libraries` ile kütüphane yükleme
- Katalog SELECT yetkileri PUBLIC'ten geri alınmış kurulum
- `statement_timeout` / `lock_timeout` tetiklenmesi
- 5.5b'de rolün hiç olmadığı durum
- Gerçek `hgs2_perftest_db`

## 16. Kullanım kısıtlamaları

1. **Komut satırı:** Yalnızca `psql -X -v ON_ERROR_STOP=1 -f postgresql_readonly_audit_v2.sql` biçiminde ve psql ≥ 12 ile çalıştırılmalı. `-1`, `\i` ve etkileşimli kullanım desteklenmez.
2. **Zorunlu parametreler:** Beş `expected_*` parametresi zorunlu. `expected_system_identifier` hedef sunucuda `pg_controldata` ile ayrı ve onaylı bir adımda alınmalı.
3. **Bağlantı:** Ağ üzerinden bağlantıda `sslmode=verify-full` + `sslrootcert` kullanılmalı; mümkünse SCRAM + `channel_binding=require`.
4. **Denetim rolü:** Süper kullanıcı olmamalı, süper kullanıcı bir role üye olmamalı, ve CREATEROLE, BYPASSRLS, REPLICATION ya da dosya/program/tüm veri önceden tanımlı rolleri olmadan çalışmalı.
5. **Sonuç kararı:** Yalnızca `tools/validate_audit_result.py` kurallarıyla verilmeli; stdout ve stderr ayrı yakalanmalı. `HGS2_AUDIT_WARNING` uyarıları yalnızca yazılı bir kararla kabul edilmeli.
6. **Dosya bütünlüğü:** Çalıştırmadan önce dosya hash'i `5916d12b…a96aa40b` ile doğrulanmalı.

---

## 17. Son onay kriterleri ve karar

| # | Kriter | Durum | Kanıt |
|---|---|---|---|
| 1 | Güvenlik kontrolleri bağımsız incelendi | ✓ | Bölüm 2–4; keşif turu `runs-discovery/` |
| 2 | search_path saldırıları engelleniyor | ✓ | S1–S5 (4 sürüm); QA B11 |
| 3 | Transaction bypass güvenle durduruluyor | ✓ | A19–A29, M1–M7, R3–R4. Not: W2/W4'te (`\i` ile kötü kullanım) çıkış 0 olsa da sonuç başarısız işaretleniyor |
| 4 | Yanlış sistem kimliği kabul edilmiyor | ✓ | A12, R2, S5 |
| 5 | Süper kullanıcı kontrolü doğru | ✓ | A14–A18, A30–A32 |
| 6 | TLS politikası açık ve doğru | ✓ | Bölüm 9 (sınırları belgeli) |
| 7 | Hassas değerler maskeleniyor | ✓ | U9; 344 çalıştırmada 0 sızıntı |
| 8 | Salt okunur davranış test edildi | ✓ | Bölüm 12 |
| 9 | Başarı ve hata işaretçileri doğru | ✓ | Bölüm 13 (yedi kurallı doğrulayıcıyla) |
| 10 | Nihai hash test kanıtlarıyla eşleşiyor | ✓ | Bölüm 14 |
| 11 | V1 değişmedi | ✓ | Bölüm 14 |
| 12 | Gerçek veritabanına bağlanılmadı | ✓ | Aşağıda |

**12. kriterin kanıtı:**
- Tüm psql, pg_dump, pg_dumpall ve pg_basebackup çağrıları yalnızca `127.0.0.1` ve 55412/55416/55417/55418/55422/55428/55499 portlarına izin veren bir koruma fonksiyonundan geçti (`kanit/harness/env.sh`).
- PG ortam değişkenleri, servis dosyaları ve psqlrc yalıtıldı.
- Çıktılarda sunucunun bildirdiği system_identifier değerlerinin tamamı test kümelerine ait.
- 5432'deki PG 18 servisine bağlanılmadı, servis durdurulmadı veya değiştirilmedi; günlükleri ve yapılandırması okunmadı. Bu nedenle doğrulama o tarafın günlüklerinden değil, yapı ve kayıtlar üzerinden yapıldı.
- HGS2 uygulaması başlatılmadı.

### KARAR: **FINAL — test edilmiş kapsam için**

On iki kriterin tamamı gerçek test kanıtıyla karşılanıyor. Ancak:
- **PRODUCTION READY etiketi verilmiyor.** Gerçek hedefte (`hgs2_perftest_db`) henüz hiç çalıştırılmadı ve kullanılacak ortamın sürüm ve platformu test kapsamında olmayabilir.
- **Test edilmemiş ortamlar:** Betiğin PG 13/14/15, psql 13/14/15 veya Linux üzerinde kullanılması, `kanit/harness/` ile o ortamda bu test setinin yeniden çalıştırılmasını gerektirir. O zamana kadar bu ortamlar için durum **NEEDS REVIEW**.
- **Gerçek çalıştırma onayı:** Gerçek `hgs2_perftest_db` üzerinde ilk çalıştırma ayrı ve yetkili bir onay gerektirir: sistem kimliğinin bağımsız alınması, denetim rolünün hazırlanması, verify-full bağlantı dizesi.
