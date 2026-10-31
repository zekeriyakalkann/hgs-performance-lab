# FINAL_DELIVERY — HGS2 PostgreSQL Read-Only Audit V2

- Tarih: 2026-10-30 (+03:00)
- Durum: **FINAL — Tested Scope Only** (PRODUCTION READY değildir; bkz. Bölüm 9)
- Bu belge bir teslimat özetidir. Yeni bir test, ölçüm veya değişiklik içermez. Her ifade aşağıdaki mevcut belge ve kanıtlara dayanır:
  - `FINAL_SECURITY_AUDIT.md`, `FINAL_TEST_MATRIX.md`, `CHANGELOG_FINAL.md`, `KNOWN_LIMITATIONS.md`, `FINAL_SHA256SUMS.txt`
  - `kanit/runs-final/` (EVALUATION, SUMMARY, READONLY_SNAPSHOT_DIFF, TLS_UNIT, VALIDATOR_SELFTEST, FILE_UNDER_TEST_START/END)
  - `tools/validate_audit_result.py`
  - Nihai SQL dosyasının başlık yorumu (satır 1–227)
- Çelişki durumunda kaynak belgeler geçerlidir.

---

## 1. Proje özeti

`postgresql_readonly_audit_v2.sql`, HGS2'nin test veritabanı `hgs2_perftest_db` ile üretim veritabanı `hibrit_giris_db` arasındaki izolasyonu PostgreSQL sistem katalogları üzerinden **salt okunur** biçimde denetleyen bir psql betiğidir. Yalnızca `hgs2_perftest_db`'ye bağlanılarak çalıştırılır; `hibrit_giris_db`'ye bağlantıyı algılayıp durur.

Betik şunları denetler ve raporlar:

| Alan | Kapsam (betik bölümü) |
|---|---|
| PostgreSQL yapılandırması | Sunucu/istemci sürüm kapıları (P1), rol ve veritabanı düzeyindeki kalıcı ayarlar, `ALTER ROLE ALL` dahil dört kapsam (Bölüm 4); izin listesi dışındaki değerler maskelenir |
| Roller ve üyelikler | `pg_roles`, `pg_auth_members` (PG 12–15 ve PG 16+ `inherit_option`/`set_option` dalları) (Bölüm 2) |
| ACL ve etkin yetkiler | Veritabanı erişimleri (Bölüm 3); tablo ve sütun ACL'leri, etkin yetki matrisi ve yetki kaynağı — sahiplik / doğrudan ACL / PUBLIC / dolaylı (5.4, 5.4a, 5.4c), PG 17+ MAINTAIN (5.4b), varsayılan ACL'ler (5.4d) |
| Şema ve nesne yapıları | Bağlı veritabanındaki tablolar, kısıtlar, fonksiyonlar (`proconfig` maskeli, SECURITY DEFINER search_path), tetikleyiciler, event trigger'lar, eklentiler, foreign server'lar (yalnızca seçenek adları), RLS politikaları (sabitler maskeli), büyük nesne ACL sayısı (Bölüm 5) |
| Sequence ilişkileri | Identity ve serial ayrımı `pg_depend.deptype` + `pg_attribute.attidentity` ile; sequence yetkileri (5.5b) ve beklenmeyen sequence'lar (5.9) |
| Güvenlik açısından önemli yapılandırma | Hedef kimliği (veritabanı adı, host/port, sunucu adresi/portu, `system_identifier`), TLS durumu (`pg_stat_ssl`), süper kullanıcı ve fazla yetki kontrolleri, transaction güvenliği, recovery durumu |

Sonuç makinece okunabilir işaretçilerle bildirilir (`HGS2_AUDIT_PREFLIGHT_OK`, `HGS2_AUDIT_COMPLETE`, `HGS2_AUDIT_ABORT: …`, `HGS2_AUDIT_WARNING: …`).

**Kapsam sınırları** (betik başlığı, `KNOWN_LIMITATIONS.md` A bölümü):
- Yalnızca sistem katalogları ve ACL metaverisi okunur. Kullanıcı tablosu satırı, parmak izi verisi veya büyük nesne içeriği okunmaz. `pg_authid` ve `umoptions` kullanılmaz.
- Bölüm 2–4 paylaşılan katalogları okur, yani küme genelini gösterir. Bölüm 5 yalnızca bağlı veritabanını gösterir; `hibrit_giris_db`'nin şeması hakkında sonuç vermez.
- `pg_hba.conf` sorgulanmaz.

## 2. Nihai dosya bilgileri

Değerler bu belge hazırlanırken gerçek dosyadan yeniden hesaplanmıştır.

| Alan | Değer |
|---|---|
| Dosya adı | `postgresql_readonly_audit_v2.sql` |
| Dosya yolu | `C:\Users\Ceng Zeki\Desktop\Projects\hgs2-lab-artifacts\db-audit\20261030-postgresql-readonly-audit-v2\asama3-final\postgresql_readonly_audit_v2.sql` |
| SHA-256 | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` |
| Boyut | 87 879 bayt |
| Satır sayısı | 1 630 |
| Biçim (`FINAL_SECURITY_AUDIT.md` §14) | UTF-8, LF, BOM yok |
| Sürüm durumu | **FINAL — Tested Scope Only** |

**Hash tutarlılığı:**

| Kaynak | Değer | Eşleşme |
|---|---|---|
| Gerçek dosya (hesaplanan) | `5916d12b…a96aa40b` | — |
| Beklenen değer | `5916d12b…a96aa40b` | ✓ |
| `FINAL_SHA256SUMS.txt` (satır 3118) | `5916d12b…a96aa40b` | ✓ |
| `FINAL_TEST_MATRIX.md` (test başı ve sonu) | `5916d12b…a96aa40b` | ✓ |
| `kanit/runs-final/FILE_UNDER_TEST_START.sha256` (18:24:12) / `…_END.sha256` (18:33:02) | `5916d12b…a96aa40b` | ✓ |

**Teslimattaki diğer dosyalar:**

| Dosya | İçerik |
|---|---|
| `tools/validate_audit_result.py` | Başvuru doğrulayıcısı. SHA-256 `a99fcb8fefff9d4cdd560639a9ef50e8ae65ee5c429578f636912f8557c50a57` (`FINAL_SHA256SUMS.txt` ile aynı) |
| `FINAL_SECURITY_AUDIT.md` | Bağımsız denetim raporu ve nihai karar |
| `FINAL_TEST_MATRIX.md` | Senaryo × sürüm sonuçları |
| `CHANGELOG_FINAL.md` | 3. aşama değişiklikleri (U1–U9) |
| `KNOWN_LIMITATIONS.md` | Bilinen sınırlamalar ve test edilmeyen alanlar |
| `FINAL_SHA256SUMS.txt` | Teslimattaki dosyaların hash listesi (`sha256sum -c FINAL_SHA256SUMS.txt`) |
| `kanit/` | Çalıştırma çıktıları, anlık görüntüler, sunucu günlükleri, test düzeneği |

Referans hash'ler (değişmedi): 2. aşama sonu `b8eb2ac69b04ddc9ab6407798bf490a9bf80dccb32abf5fb96118b52fd1db841`; V1 `3423053a254ca6ff361631562e9e9a26e112fddd4e4ea5a5a9b539c0e984c7ff`.

## 3. Doğrulanmış test ortamları

Kaynak: `FINAL_TEST_MATRIX.md` §1–2, `FINAL_SECURITY_AUDIT.md` §7–8.

**PostgreSQL sunucu:**

| Sürüm | Kaynak | Fiziksel replika |
|---|---|---|
| 12.22 | EDB taşınabilir zip | Var (`pg_basebackup -R`) |
| 16.15 | EDB taşınabilir zip | — |
| 17.11 | EDB taşınabilir zip | — |
| 18.6 | Kurulu ikili dosyalar, ayrı `initdb` ile yeni küme | Var (`pg_basebackup -R`) |

**psql istemci** (tam denetim, PASS):

| psql \ sunucu | 12 | 16 | 17 | 18 |
|---|---|---|---|---|
| 12 | PASS | — | — | PASS |
| 16 | — | PASS | — | PASS |
| 17 | — | — | PASS | PASS |
| 18 | PASS | PASS | PASS | PASS |

**Ortam koşulları:**
- Yalnızca Windows ikili dosyaları.
- Geçici, izole test kümeleri; yalnızca `127.0.0.1`; `trust` kimlik doğrulaması + `ssl=on`, sentetik CA; sentetik veri.
- Uzak host adı `hostaddr=127.0.0.1` ile benzetildi; proxy testleri gerçek bir TCP proxy ile yapıldı (pooler değil).
- `hibrit_giris_db`, `hgs2_perftest_db` ve 5432'deki PG 18 servisi kullanılmadı.

## 4. Test sonuçları

Aşağıdaki sonuçlar yalnızca Bölüm 3'teki ortamlar için geçerlidir.

### 4.1 Senaryo değerlendirmesi

- **344 senaryonun 344'ü önceden tanımlanmış beklentiyle eşleşti** (`kanit/runs-final/EVALUATION.txt`: `TOTAL=344 MATCH=344 MISMATCH=0`).
- "Eşleşme" PASS anlamına gelmez. Senaryoların büyük kısmı bir güvenlik kontrolünün durdurmasını beklenen sonuç olarak tanımlar (yanlış hedef, süper kullanıcı, açık transaction, saldırı, sahtecilik vb.). Bu senaryolarda beklenti doğrulayıcının **FAIL** vermesidir ve öyle olmuştur.
- Bir güvenlik kontrolünün başarısız olduğu hiçbir senaryoda doğrulayıcı PASS vermedi (`FINAL_SECURITY_AUDIT.md` §13).
- Her çalıştırmada değerlendirici şunları da denetledi: çıkış kodu, ABORT nedeni, ABORT işaretçisinin stderr'de de bulunması, uyarı kümesi, doğrulayıcı kararı, betik hash'i ve sentetik gizli değer sızıntısı.
- 286 çalıştırma doğrudan nihai dosyayı yürüttü; 4 stdin çalıştırması aynı dosyayı borudan okudu. Kalanlar mutasyon ve sarmalayıcı senaryolarıdır (`FINAL_TEST_MATRIX.md` satır 7).
- `O*` satırları (orijinal V2 ve 2. aşama dosyasıyla karşılaştırma) 344'e dahil değildir.

### 4.2 search_path saldırı testleri

Kaynak: `FINAL_SECURITY_AUDIT.md` §11; senaryolar S1–S5, 4 sürüm.

- **Saldırı:** `evil` şemasında 10 sahte operatör ve 6 sahte fonksiyon (`current_setting`, `current_database`, `now`, `pg_is_in_recovery`, `host`, `inet_server_addr`). Kalıcı vektör olarak denetim rolüne veritabanı düzeyinde `search_path = evil, pg_catalog`; S4'te ek olarak PGOPTIONS.

| Senaryo | Nihai dosya sonucu |
|---|---|
| S1 yanlış host, port ve sistem kimliği | 3 / `client_host_mismatch` |
| S2 önceden açık RR RO transaction + saldırı | 3 / `open_transaction` |
| S3 doğru parametreler + saldırı | PASS; maskeleme sağlam; denetim rolünün kötü niyetli search_path'i raporda görünür |
| S4 PGOPTIONS + yanlış host | 3 / `client_host_mismatch` |
| S5 yalnızca yanlış sistem kimliği | 3 / `system_identifier_mismatch` |

- **Karşılaştırma:** Orijinal V2 (`726771…`) aynı saldırı altında PG 17/18'de yanlış hedefi `0 / COMPLETE / PASS` olarak kabul ediyordu.
- **Statik güvence** (QA B11/B12/B15): `SET LOCAL search_path = pg_catalog, pg_temp` penceresi dışında nitelenmemiş fonksiyon veya operatör yok; psql değişkenleri yalnızca `:'var'` ile aktarılıyor.
- **Kapsam sınırı:** Saldırgan modeli süper kullanıcı olmayan bir taraftır. Süper kullanıcı düzeyinde ele geçirilmiş sunucu kapsam dışıdır.

### 4.3 TLS testleri

Kaynak: `FINAL_SECURITY_AUDIT.md` §9; T1–T10 (4 sürüm), X1–X4 (PG 12 ve 18).

| Test | Sonuç |
|---|---|
| T1 loopback, `sslmode=require` | PASS, TLSv1.3 sunucuda raporlandı |
| T2 loopback, `disable` | PASS (uçtan uca yerel, TLS'siz kabul) |
| T3 `verify-full`, doğru CA ve ad | PASS |
| T4 `verify-full`, sahte CA | psql çıkış 2 (`certificate verify failed`) — istemci reddetti |
| T5 `verify-full`, yanlış ana bilgisayar adı | psql çıkış 2 (ad uyuşmazlığı) — istemci reddetti |
| T6 uzak ad, `disable` | 3 / `insecure_transport` |
| T7 / T7b `allow_insecure_transport=1` | 0 + `HGS2_AUDIT_WARNING: insecure_transport_allowed`; doğrulayıcı FAIL, uyarı açıkça kabul edilince PASS |
| T8 `allow_insecure_transport=true` | 3 / `insecure_transport` (yalnızca tam "1" kabul edilir) |
| T9 uzak ad, `require` | PASS |
| T10 loopback + gereksiz bayrak | PASS, uyarı yok, yalnızca bilgi satırı |
| X1–X4 gerçek TCP proxy | X1 PASS; X2 `client_port_mismatch`; X3 `insecure_transport`; X4 PASS |
| TLS sınıflama birim testi | 19 girdi × 2 sürüm = 38/38 (`TLS_UNIT.txt`) |

**Önemli:** T3 ve T9'da SQL'in gördüğü TLS satırı birebir aynıdır. Sertifika ve ana bilgisayar adı doğrulaması **SQL'den kanıtlanamaz**; yalnızca istemcide `sslmode=verify-full` + `sslrootcert` ile uygulanır.

### 4.4 Salt okunurluk karşılaştırmaları

Kaynak: `FINAL_SECURITY_AUDIT.md` §12, `kanit/runs-final/READONLY_SNAPSHOT_DIFF.txt`.

- **Önce/sonra anlık görüntüleri:** 4 sürüm × (şema `pg_dump -s`, globals `pg_dumpall -g`, durum dosyası) = **12/12 karşılaştırmada 0 fark**.
  - Durum dosyası tablo verisi md5'ini, sequence son değerlerini, LO metadata'sını, rol ayarlarını, veritabanı ACL'lerini ve politikaları kapsar.
- **Saldırı, sahtecilik ve kodlama senaryolarından sonra:** 12/12 karşılaştırmada 0 fark; temizlik sayaçları 0.
- **Sunucu günlüğü** (`log_statement=all`): izin dışı ifade 0; hatadan sonra betiğin çalıştırdığı ifade 0.
- **Statik:** Ayrıştırıcıya göre ifade türleri yalnızca SELECT, BEGIN/ROLLBACK, SET (TRANSACTION/LOCAL) ve SHOW. 81 SQL parçasında 0 sözdizimi hatası. Yazma anahtar sözcüğü ve tehlikeli meta-komut yok.
- Tüm SET'ler transaction yereldir ve ROLLBACK ile geri alınır. Yalnızca `\encoding UTF8` oturumluktur ve veritabanına yazmaz.

### 4.5 Hassas veri sızıntısı testleri

- **Test edilen:** Fixture'lardaki 7 sentetik gizli değer (`kanit/harness/evaluate3.py` içindeki `SECRETS` listesi): `SENTETIK-GIZLI-DEGER`, `SENTETIK-PAROLA-GUC`, `SENTETIK-PAROLA-UM`, `SENTETIK-TOKEN-FN`, `SENTETIK-TOKEN-POL`, `SENTETIK-TOKEN-AUDITROLE`, `sentetik-prod-host`.
- **Sonuç:** Karşılaştırma dışı 344 çalıştırmanın stdout ve stderr'inde bu değerlerin **hiçbiri bulunmadı**. Sızıntı, değerlendiricide (`kanit/harness/evaluate3.py`) uyuşmazlık sayılır; 344/344 eşleşme bu kontrolü de kapsar.
- Maskelenen alanların adı görünür kalır: `hgs2.api_token=<maskelendi>`, `'<maskelendi>'::text`.
- 2. aşama dosyası aynı fixture'larla bu değerleri açık metin basıyordu (bulgu N1, düzeltme U9).
- **Kapsam sınırı** (`KNOWN_LIMITATIONS.md` madde 17): Maskeleme izin listesine dayanır.
  - İzin listesindeki 15 ayarın değeri açık gösterilir.
  - Politika ifadelerinde yalnızca tırnaklı sabitler maskelenir; sayısal sabitler ve tanımlayıcılar görünür.
  - Test, bilinen 7 değerin aranmasıyla sınırlıdır.

### 4.6 Diğer doğrulamalar

| Ölçüm | Sonuç |
|---|---|
| Katalog doğrulamaları | 18 tam çıktının her birinde 33/33; sızıntı 0 |
| Transaction güvenliği | `psql -1`, önceden açık transaction'lar (7 varyant), atanmış xid, replika → durdurma. P2 kaldırılınca P3 sondası tek başına durduruyor (A25, M3, M5–M7, R4). İkisi birden kaldırılınca yanlış başarı geri geliyor (M4) |
| İşaretçi sahteciliği | Çıktı biçimi sabitlendiği için sorgu sonuçları sütun 0'a ulaşamıyor (F1, F2, E04, E05, E17) |
| Doğrulayıcı öz-testi | 16/16 (`VALIDATOR_SELFTEST.txt`) |

### 4.7 Nihai dosya hash doğrulaması

- Test başı (2026-10-30T18:24:12+03:00) ve test sonu (18:33:02) kayıtları `5916d12b…a96aa40b`.
- Her çalıştırmanın klasöründe `script.sha256` bulunur; değerlendirici, nihai dosyayı yürüten çalıştırmalarda bu hash'i hedefle karşılaştırdı.
- Bu belge hazırlanırken yeniden hesaplanan değer aynıdır (Bölüm 2).

## 5. Güvenli çalıştırma ön koşulları

Aşağıdakiler yalnızca mevcut belgelerde yazılı gereksinimlerdir. Belgelerin tanımlamadığı noktalar "belgelenmemiş" olarak işaretlenmiştir ve operasyonel prosedürde karara bağlanmalıdır.

### 5.1 Doğru PostgreSQL hedefi
- Bağlantı hedefi **yalnızca `hgs2_perftest_db`** olmalıdır.
  - Betik sunucu tarafında `current_database()` ile istemci tarafında `DBNAME` değerini karşılaştırır. Farklıysa `wrong_database` ile, `hibrit_giris_db` ise `production_database` ile durur.
- Hedef sunucunun sürümü ve platformu test kapsamında olmalıdır (Bölüm 3). Değilse durum **NEEDS REVIEW**'dur (Bölüm 8).

### 5.2 Beklenen sistem kimliği
- `expected_system_identifier` **zorunludur**. Değer, hedef kümenin veri dizininde `pg_controldata` çıktısındaki "Database system identifier" değeridir.
- Bu değer **betikten bağımsız, ayrı ve yetkili bir adımda** alınmalıdır.
- Sınırlama: `system_identifier` kriptografik kimlik değildir. Fiziksel replikalar ve aynı temel yedekten oluşturulan klonlar aynı değeri taşır. Betik recovery durumunu raporlar ama primary ile klonu ayırt edemez (R1).

### 5.3 Beklenen host ve port
Dört parametrenin tamamı zorunludur:

| Parametre | Anlamı |
|---|---|
| `expected_host` | psql'e verilen `host` değeriyle **birebir** aynı; büyük/küçük harfe duyarlı |
| `expected_port` | psql'e verilen port |
| `expected_server_addr` | Sunucunun gördüğü adres (`inet_server_addr()`); Unix soketinde `local-socket` |
| `expected_server_port` | Sunucunun dinlediği port |

- Proxy arkasında istemci portu ile sunucu portu farklı olabilir (X1, X2).
- Host ve port da kimlik kanıtı değildir (`KNOWN_LIMITATIONS.md` madde 2).

### 5.4 Süper kullanıcı olmayan denetim rolü
- Rol **süper kullanıcı olmamalıdır**. `session_user`, `current_user` ve `is_superuser` denetlenir; aksi halde `superuser_connection`.
- Rol **süper kullanıcı bir role üye olmamalıdır**; aksi halde `superuser_membership`.
  - Kontrol katıdır: PG 16+'da SET/INHERIT kapalı, yani fiilen kullanılamayan üyelik de reddedilir.
- Rolde şunlar bulunmamalıdır: CREATEROLE, BYPASSRLS, REPLICATION; `pg_execute_server_program`, `pg_read_server_files`, `pg_write_server_files`, `pg_read_all_data`, `pg_write_all_data` üyeliği. Bulunursa `HGS2_AUDIT_WARNING: audit_role_excess_privilege` yazılır ve uyarı kabul edilmedikçe sonuç FAIL'dir.
- `allow_superuser=1` yalnızca tam "1" ile etkinleşir. Kullanılırsa `superuser_allowed` uyarısı çıkar. Kullanımı yazılı bir karar gerektirir.

### 5.5 Gerekli katalog okuma yetkileri
- Katalog SELECT yetkileri varsayılan kurulumda PUBLIC'tir. Test kümelerinde süper kullanıcı olmayan bir rolle doğrulandı.
- Rolün `pg_catalog.pg_control_system()` için **EXECUTE** yetkisi olmalıdır.
  - Varsayılan kurulumda PUBLIC'e açıktır (test kümelerinde `proacl = NULL`).
  - PUBLIC'ten geri alındıysa yönetici ayrı bir adımda vermelidir: `GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO <rol>;`
  - Yetki yoksa betik `system_identifier_unverifiable` ile durur (A13).
- **Test edilmedi:** Katalog SELECT yetkilerinin PUBLIC'ten geri alındığı sertleştirilmiş kurulumlar.

### 5.6 TLS ve sertifika doğrulaması
- Ağ üzerinden bağlantıda `sslmode=verify-full` + `sslrootcert=<güvenilir CA>` kullanılmalıdır.
- Mümkünse SCRAM + `channel_binding=require` (`FINAL_SECURITY_AUDIT.md` §16). Bu kombinasyon **test edilmedi**.
- Betik TLS'in kurulduğunu sunucu tarafında görür. Sertifika ve ad doğrulamasını göremez. Doğru bağlantı dizesi operatörün sorumluluğundadır.
- `sslmode=require` trafiği şifreler ama sunucuyu doğrulamaz.
- TLS yoksa bağlantı yalnızca hem sunucu tarafı hem istemcinin bağlandığı adres yerelse kabul edilir; aksi halde `insecure_transport`.
- `allow_insecure_transport=1` yalnızca bilinçli, yazılı bir kararla kullanılmalıdır.

### 5.7 psql sürüm gereksinimi
- psql **12 veya üzeri** gerekir; daha eskisi `psql_too_old` ile reddedilir.
- Test edilmiş psql sürümleri: 12, 16, 17, 18 (Bölüm 3'teki çaprazlarla).
- psql 13/14/15 test edilmedi.
- `VERSION_NUM` kapısı yalnızca uyumluluk içindir, güvenlik kontrolü değildir.

### 5.8 Güvenli parola sağlama yöntemi
- **Belgelenen kural:** Parola **komut satırında, bağlantı URL'sinde veya `PGPASSWORD` içinde verilmemelidir** (betik başlığı, satır 82).
- **Belgelenmemiş:**
  - Mevcut belgeler parolanın hangi olumlu yöntemle verileceğini tanımlamaz.
  - Test kümeleri `trust` kimlik doğrulaması kullandığından parola ile kimlik doğrulama yolu hiç test edilmedi.
  - libpq'nun standart seçenekleri (psql'in parola istemi, erişimi yalnızca operatörle sınırlı bir parola dosyası) bu projede doğrulanmamıştır.
  - Seçim ve dosya izinleri operasyonel güvenlik prosedüründe karara bağlanmalıdır.

### 5.9 Çıktı dosyalarının korunması
- **stdout ve stderr AYRI yakalanmalıdır**; `2>&1` kullanılmamalıdır. Aksi halde doğrulayıcının "stderr boş" kuralı uygulanamaz.
- `-o` ile sorgu sonuçları dosyaya gider; işaretçiler yine stdout'tadır (E10). Karar stdout'a göre verilir.
- **Çıktının içeriği:** Küme geneli roller, üyelikler, ACL'ler ve ayar adları; izin listesindeki 15 ayarın açık değerleri; politika ifadelerindeki tanımlayıcı ve sayısal sabitler; FDW seçenek adları.
  - Maskeleme izin listesine dayandığından çıktı **hassas yapılandırma bilgisi** olarak ele alınmalıdır.
  - `CHANGELOG_FINAL.md` U9, denetim çıktısının saklandığı her yere taşındığını not eder.
- **Belgelenmemiş:** Saklama yeri, erişim izinleri ve saklama süresi. Bunlar operasyonel prosedürde tanımlanmalıdır.

### 5.10 Çalıştırma öncesi ve sonrası doğrulama

**Öncesi:**
1. Gerçek hedefte çalıştırma için **ayrı ve yetkili onay** alınmış olmalı.
2. Dosya hash'i `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` ile doğrulanmalı. İsteğe bağlı olarak teslimat klasöründe `sha256sum -c FINAL_SHA256SUMS.txt` çalıştırılabilir.
3. `expected_system_identifier` bağımsız olarak alınmış olmalı (5.2).
4. Denetim rolü 5.4–5.5'e göre hazırlanmış olmalı.
5. Bağlantı dizesi `verify-full` + güvenilir CA ile hazırlanmalı (5.6).
6. psql sürümü ≥ 12 ve test kapsamında olmalı (5.7).
7. `pg_hba.conf` ve gerçek bağlantı davranışı yetkili bir yönetici tarafından ayrı bir adımda doğrulanmalı. Betik bunu sorgulamaz.

**Sonrası:**
1. Karar **yalnızca** `tools/validate_audit_result.py` kurallarıyla verilmeli (Bölüm 7).
2. Herhangi bir `HGS2_AUDIT_WARNING` yalnızca yazılı bir kararla `--accept-warning` ile kabul edilmeli.
3. Raporlanan recovery durumu, TLS satırı ve denetim rolünün kalıcı ayarları beklentiyle karşılaştırılmalı. search_path saldırısı S3'te bu satırla görünür hale geldi.

**Test düzeneğinin uygulaması (bilgi amaçlı):** Testlerde PG ortam değişkenleri (`PGHOST`, `PGOPTIONS`, `PGPASSWORD` vb.), servis dosyaları ve psqlrc yalıtıldı. Her çalıştırmanın argümanları, çıkış kodu, stdout, stderr ve betik hash'i ayrı ayrı kaydedildi (`kanit/runs-final/<id>/`).

## 6. Örnek çalıştırma komutu

Bu örnek, betik başlığındaki (satır 34–83) belgelenmiş komut satırını ve `KNOWN_LIMITATIONS.md` B bölümündeki kuralları izler.

- Tüm `<...>` değerleri **yer tutucudur**.
- `hgs2_perftest_db` bir yer tutucu değildir: betiğin kabul ettiği tek hedeftir.
- Komut POSIX kabuk sözdizimiyle yazılmıştır.

```sh
# 0) Dosya bütünlüğü (çalıştırmadan önce)
sha256sum postgresql_readonly_audit_v2.sql
#    beklenen: 5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b

# 1) Denetim — stdout ve stderr AYRI dosyalara, çıkış kodu ayrıca kaydedilir
psql -X -v ON_ERROR_STOP=1 \
     -d "host=<HOST> port=<PORT> dbname=hgs2_perftest_db user=<DENETIM_ROLU> sslmode=verify-full sslrootcert=<GUVENILIR_CA_DOSYASI>" \
     -v expected_host=<HOST> \
     -v expected_port=<PORT> \
     -v expected_server_addr=<SUNUCUNUN_GORDUGU_ADRES> \
     -v expected_server_port=<SUNUCUNUN_DINLEDIGI_PORT> \
     -v expected_system_identifier=<PG_CONTROLDATA_SISTEM_KIMLIGI> \
     -f postgresql_readonly_audit_v2.sql \
     > <CIKTI_DIZINI>/stdout.txt 2> <CIKTI_DIZINI>/stderr.txt
echo $? > <CIKTI_DIZINI>/exit.txt
```

**Gereksinim kontrol listesi:**

| Gereksinim | Komuttaki karşılığı |
|---|---|
| `-X` (psqlrc okunmaz) | ✓ `-X` |
| ON_ERROR_STOP komut satırında açık (dosyadaki `\set` yetmez; N9) | ✓ `-v ON_ERROR_STOP=1` |
| `-1` / `--single-transaction` yok | ✓ yok (betik algılar ve `open_transaction` ile durur) |
| Yalnızca `-f` ile; `\i`, stdin sarmalayıcısı veya etkileşimli oturum değil | ✓ `-f` |
| Host, port, veritabanı, kullanıcı açık | ✓ `host=`, `port=`, `dbname=`, `user=` |
| Beş zorunlu `expected_*` değişkeni | ✓ beşi de var; biri eksikse `missing_parameter` |
| TLS `verify-full` + güvenilir CA | ✓ `sslmode=verify-full sslrootcert=…` |
| Parola komut satırında, URL'de veya `PGPASSWORD`'da yok | ✓ bağlantı dizesi key=value biçiminde ve parola içermez (yöntem için 5.8) |
| stdout/stderr ayrı yakalama | ✓ `>` ve `2>` ayrı dosyalar |

**İsteğe bağlı parametreler** (betik başlığı, satır 45–46):
- `-v audit_statement_timeout=30s` ve `-v audit_lock_timeout=5s`. Zaman aşımı tetiklenmesi test edilmedi.
- `-v allow_superuser=1` ve `-v allow_insecure_transport=1`. Örnekte bilinçli olarak yoktur; yalnızca yazılı bir kararla eklenebilir ve uyarı işaretçisi üretir.

`expected_host` değeri `host=` ile **birebir** aynı olmalıdır (büyük/küçük harf dahil).

## 7. Başarı ve başarısızlık koşulları

> **Başarı kararı hiçbir zaman yalnızca psql çıkış kodu 0'a göre verilmemelidir.**
>
> W2/W4 senaryolarında (`\i` ile sarmalama, komut satırında ON_ERROR_STOP yok) betik ABORT yazdığı halde psql **0** ile çıktı. M4, A17, A31, A32, T7 senaryolarında da çıkış 0 olmasına rağmen sonuç FAIL'dir.

### 7.1 Çıkış kodları

| psql çıkış kodu | Anlamı |
|---|---|
| 0 | Yalnızca **aday** başarı; yedi kuralın tamamı ayrıca sağlanmalı |
| 1 | psql'in kendi hatası |
| 2 | Bağlantı hatası (ör. T4 sahte CA, T5 yanlış ana bilgisayar adı) |
| 3 + stdout/stderr'de `HGS2_AUDIT_ABORT:` | Bir güvenlik kontrolü durdurdu |
| 3 + **işaretçi yok** | SQL/yetki hatası **veya P3 transaction sondası**; denetim eksik → **BAŞARISIZ** |

### 7.2 İşaretçiler

| İşaretçi | Anlamı |
|---|---|
| `HGS2_AUDIT_PREFLIGHT_OK` | Ön kontroller geçti; tam bir kez ve COMPLETE'ten önce olmalı |
| `HGS2_AUDIT_COMPLETE` | Denetim sonuna ulaştı; tam bir kez ve stdout'un son boş olmayan satırı olmalı |
| `HGS2_AUDIT_ABORT: <neden>` | Güvenlik durdurması. Testlerde görülen nedenler: `wrong_database`, `production_database`, `missing_parameter <ad>`, `client_host_mismatch`, `client_port_mismatch`, `server_addr_mismatch`, `server_port_mismatch`, `system_identifier_mismatch`, `system_identifier_unverifiable`, `superuser_connection`, `superuser_membership`, `open_transaction`, `open_transaction_with_xid`, `tx_not_read_only`, `tx_not_repeatable_read`, `insecure_transport`, `psql_too_old` |
| `HGS2_AUDIT_WARNING: <ad>` | `superuser_allowed`, `insecure_transport_allowed`, `audit_role_excess_privilege`. Açıkça kabul edilmedikçe FAIL |

İşaretçiler yalnızca **sütun 0'da** eşleştirilmelidir. Betik aligned çıktı biçimini sabitler; sorgu sonucu satırları her zaman boşlukla başlar.

### 7.3 Doğrulayıcının yedi kuralı

`tools/validate_audit_result.py` PASS için **tümünü** ister:

1. psql çıkış kodu == 0
2. stderr boş (stdout ve stderr ayrı yakalanmış olmalı)
3. stdout'un son boş olmayan satırı tam olarak `HGS2_AUDIT_COMPLETE`
4. `HGS2_AUDIT_COMPLETE` tam bir kez, tam satır olarak
5. `HGS2_AUDIT_PREFLIGHT_OK` tam bir kez ve COMPLETE'ten önce
6. Hiçbir satır `HGS2_AUDIT_ABORT:` ile başlamıyor
7. Açıkça kabul edilmemiş `HGS2_AUDIT_WARNING:` yok

### 7.4 P3 kontrolünde işaretçisiz çıkış kodu 3

- P2 kontrolü (önceden açık transaction algılama) bir şekilde atlatılırsa P3 transaction sondası PostgreSQL hatasıyla durdurur: `SET TRANSACTION ISOLATION LEVEL must be called before any query`.
- Sonuç **çıkış 3 + ABORT işaretçisi yok**'tur (A25, M3, M5–M7, R4).
- Otomasyon "3 + işaretçi yok" durumunu kesinlikle **BAŞARISIZ** saymalıdır. Doğrulayıcı bunu `exit code 3 without HGS2_AUDIT_ABORT marker … audit incomplete` olarak raporlar.
- Sonda PostgreSQL'in `check_transaction_isolation` davranışına bağlıdır; her yeni ana sürümde yeniden test edilmelidir (`KNOWN_LIMITATIONS.md` madde 8).

### 7.5 Doğrulayıcı kullanımı

Argümanlar dosyanın gerçek `argparse` tanımından alınmıştır:

```sh
python tools/validate_audit_result.py \
    --exit-code "$(cat <CIKTI_DIZINI>/exit.txt)" \
    --stdout <CIKTI_DIZINI>/stdout.txt \
    --stderr <CIKTI_DIZINI>/stderr.txt
# Yalnızca yazılı bir kararla kabul edilen uyarı varsa (tekrarlanabilir):
#   --accept-warning <UYARI_ADI>
```

- Çıktının ilk satırı `PASS` ya da `FAIL`'dir. FAIL'de nedenler `  - …` satırlarında listelenir.
- Doğrulayıcının çıkış kodu: **0 = PASS, 1 = FAIL, 2 = kullanım hatası**.

## 8. Bilinen sınırlamalar

Tam liste: `KNOWN_LIMITATIONS.md`. Aşağıdaki ortamlar **test edilmedi**. Bu ortamlarda kullanım için durum **NEEDS REVIEW**'dur ve `kanit/harness/` test setinin o ortamda yeniden çalıştırılması gerekir (`FINAL_SECURITY_AUDIT.md` §17).

| Test edilmemiş alan | Durum | Not |
|---|---|---|
| PostgreSQL 13, 14, 15 | **NEEDS REVIEW** | Sunucu 13+ kod yolu (`pg_current_xact_id_if_assigned`) yalnızca 16/17/18'de, PG 12–15 `pg_auth_members` dalı yalnızca 12'de çalıştırıldı |
| psql 13, 14, 15 | **NEEDS REVIEW** | psql 10/11 betik tarafından reddedilir; yalnızca `VERSION_NUM` taklidiyle denendi, gerçek ikili dosyayla değil |
| Linux | **NEEDS REVIEW** | Yalnızca Windows ikili dosyaları kullanıldı |
| Unix socket | **NEEDS REVIEW** | Windows'ta MAX_PATH sınırı nedeniyle kurulmadı; `local-socket` yolu çalıştırılmadı |
| Gerçek PgBouncer (ve pgpool) | **NEEDS REVIEW** | Yalnızca düz TCP proxy ile test edildi. Sunucu makinesinde TLS sonlandıran bir pooler arkasında TLS kapısı durdurur (madde 15) |
| SCRAM channel binding | **NEEDS REVIEW** | Test kümeleri `trust` kullandı; parola ile kimlik doğrulama da test edilmedi |
| Etkileşimli psql oturumu | **NEEDS REVIEW** — desteklenmez | Etkileşimli modda ON_ERROR_STOP psql'i kapatmaz; oturum iptal edilmiş transaction'da kalabilir; betik oturum ayarlarını değiştirir |
| Gerçek `hgs2_perftest_db` | **NEEDS REVIEW** | Hiç çalıştırılmadı (kapsam dışı) |

**Diğer test edilmemiş durumlar:**
- Loopback dışı gerçek ağ (yalnızca `hostaddr` ile benzetildi)
- PG 17+ `login` event trigger'ı
- `local_preload_libraries` / `session_preload_libraries`
- Katalog SELECT yetkileri PUBLIC'ten geri alınmış kurulum
- `statement_timeout` / `lock_timeout` tetiklenmesi
- 5.5b'de `hgs2_perftest` rolünün hiç olmadığı durum

**Tasarım sınırları** (test edilse de değişmez):
- verify-full SQL'den kanıtlanamaz.
- `system_identifier` replika ve klonu ayırt etmez.
- Süper kullanıcı düzeyinde ele geçirme kapsam dışıdır.
- `pg_hba.conf` sorgulanmaz.
- `\i` ile sarmalamada çıkış kodu 0 olabilir.

## 9. Production Ready uyarısı

> **Bu sürüm FINAL olarak yalnızca doğrulanmış test kapsamı için kabul edilmiştir. Gerçek hgs2_perftest_db üzerinde çalıştırılmadığından PRODUCTION READY olarak sınıflandırılmamıştır.**
>
> **Gerçek veritabanında çalıştırma ayrı bir operasyonel güvenlik prosedürü ve ayrıca onay gerektirir.**

`FINAL_SECURITY_AUDIT.md` §17'ye göre bu onay en az şunları kapsar:
- Sistem kimliğinin bağımsız alınması
- Denetim rolünün hazırlanması
- verify-full bağlantı dizesi

Bu belgenin 5.8 ve 5.9 bölümlerinde "belgelenmemiş" olarak işaretlenen noktalar da (parola yöntemi, çıktı saklama) aynı prosedürde karara bağlanmalıdır.

## 10. Üç aşamalı geliştirme geçmişi

| Aşama | Amaç | Dosya (SHA-256) | Kanıt |
|---|---|---|---|
| **1. V2 geliştirme ve ilk güvenlik iyileştirmeleri** | V1 betiğinden (`3423053a…`, değiştirilmedi) V2 üretildi | `726771681923c156…` (56 048 bayt, 1 130 satır) | `asama2-kanit/baseline/postgresql_readonly_audit_v2.ORIGINAL.sql` |
| **2. Dört PostgreSQL sürümünde gerçek sunucu testleri ve düzeltmeler** | PG 12.22 / 16.15 / 17.11 / 18.6 test kümelerinde gerçek çalıştırma; bulunan açıkların kapatılması | `726771…` → `b8eb2ac69b04ddc9…` (72 646 bayt, 1 407 satır) | `ASAMA2_RAPORU.md`, `asama2-kanit/` |
| **3. Bağımsız güvenlik denetimi, saldırı testleri ve nihai doğrulama** | Önceki düzeltmeler doğru kabul edilmeden yeniden denetim | `b8eb2ac6…` → `5916d12bb1194b69…` (87 879 bayt, 1 630 satır) | `FINAL_SECURITY_AUDIT.md`, `CHANGELOG_FINAL.md`, `kanit/` |

**1. aşama değişiklikleri (S1–S11):**
- READ ONLY doğrulaması, açık transaction algılama, hedef doğrulama
- Durdurmalarda çıkış kodu 3 ve `HGS2_AUDIT_COMPLETE`
- Etkin yetki matrisi ve sequence yetkileri
- Ayar maskeleme
- Zaman aşımı sınırları
- psqlrc'den bağımsız psql ayarları

**2. aşama değişiklikleri (T1–T9):**
- P3 transaction sondası
- Zamandan bağımsız xid kontrolü
- `SET LOCAL search_path` sabitlemesi
- Zorunlu `system_identifier`
- Katı `allow_superuser`
- TLS raporu ve kapısı
- Kapsam genişletme

2. aşamada **144 çalıştırmanın 144'ü** beklentiye uygun çıktı. Rapor kendisini nihai onay değil, 3. aşamaya girdi olarak tanımlar.

**3. aşama:**
- Dokuz bulgu (N1–N9) gerçek çalıştırmayla doğrulandı. Önemlileri:
  - Gizli değer sızıntısı
  - Süper kullanıcı üyelik yolu
  - TLS son-atlama körlüğü
  - İşaretçi sahteciliği
- Dokuz düzeltme yapıldı (U1–U9) ve ON_ERROR_STOP'un komut satırında zorunlu olduğu belgelendi.
- Son dosya dört sürümde 344 senaryoyla baştan test edildi.
- Karar: **FINAL — test edilmiş kapsam için**.
