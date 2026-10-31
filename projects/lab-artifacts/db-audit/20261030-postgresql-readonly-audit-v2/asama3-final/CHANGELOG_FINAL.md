# CHANGELOG_FINAL — HGS2 PostgreSQL Read-Only Audit V2, 3. aşama

| | SHA-256 |
|---|---|
| Önceki sürüm (2. aşama sonu; değiştirilmedi, çalışma dizininde duruyor) | `b8eb2ac69b04ddc9ab6407798bf490a9bf80dccb32abf5fb96118b52fd1db841` |
| Bu sürüm (`asama3-final/postgresql_readonly_audit_v2.sql`) | `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b` |

- Satır numaraları yeni dosyaya göredir.
- "Kanıt" sütunundaki kodlar `FINAL_TEST_MATRIX.md` ve `kanit/runs-final/<kod>-pgNN/` klasörlerine karşılık gelir.
- "Önceki davranış" değerleri, 2. aşama dosyasının (`b8eb…`) aynı test kümelerinde gerçekten çalıştırılmasıyla ölçüldü (`kanit/runs-discovery/`, `kanit/runs-final/O*`).

---

### U1 — psql çıktı ve davranış ayarlarının sabitlenmesi (bulgu N4a)
- **Satırlar:** 229–251 (`\set ECHO none` … `\pset title`)
- **Bulgu:**
  - Betik çıktı biçimini sabitlemiyordu. Operatör `-A` (unaligned) kullanırsa, adında gerçek satır sonu bulunan bir nesne (ör. veritabanı sahibinin oluşturduğu tablo) sütun 0'da `HGS2_AUDIT_ABORT: …` satırı üretebiliyordu.
  - `-v ECHO=all` çıktı akışını bozuyordu.
- **Güvenlik etkisi:** İşaretçi bütünlüğü bozuluyordu. Etki yanlış başarısızlık ve yanlış neden bildirimiydi; tam doğrulayıcı kurallarıyla sahte başarı üretilemedi.
- **Değişiklik:**
  - `ECHO none`, `ECHO_HIDDEN`/`SINGLESTEP`/`SINGLELINE off`
  - `\pset format aligned`, `border 1`, `expanded off`, `tuples_only off`, `title` (boş)
- **Önceki davranış:** D17/D18 ve O5 (4 sürüm): `-A -t` ile sütun 0'da 2 sahte ABORT satırı; doğrulayıcı FAIL (`forged_marker`). D06: `ECHO=all` ile FAIL.
- **Yeni davranış:**
  - F1 (4 sürüm): aynı sahte nesnelerle `-A -t` → sütun 0'da 0 sahte satır, PASS.
  - E03/E04/E05/E17 (4 sürüm): `ECHO=all`, `-A -t`, `-x`, `-P title=HGS2_AUDIT_COMPLETE -P border=0` altında PASS. Çıktı yapısı normal çalıştırmayla aynı: 1 hizalı başlık, 32 ayraç, 34 satır sayacı; sütun 0'da betik dışı veri satırı 0.

### U2 — psql alt sınırı 12 (N8)
- **Satırlar:** 266, 271–276
- **Bulgu:** Kapı psql 10'u kabul ediyordu, ama psql 10/11 hiç test edilmedi.
- **Etki:** Doğruluk. Test edilmemiş istemci destekleniyor görünüyordu.
- **Değişiklik:** `VERSION_NUM >= 120000`; mesaj "psql 12 veya uzeri".
- **Kanıt:** E15 (`-v VERSION_NUM=110000`) → 3 / `psql_too_old` (4 sürüm); N1–N5 psql 12/16/17/18 → PASS.
- **Not:** `VERSION_NUM` `-v` ile ezilebilir. Bu bir uyumluluk kapısıdır, güvenlik kontrolü değildir (yorumda belirtildi).

### U3 — `\echo` ile yazılan adlarda kontrol karakteri temizleme (N4b)
- **Satırlar:** 459–474 (Bölüm 0), 746–747 (P8)
- **Bulgu:** Veritabanı ve rol adları `\echo` ile doğrudan sütun 0'a yazılıyordu; adlarda satır sonu bulunabilir.
- **Değişiklik:**
  - `regexp_replace(…, '[[:cntrl:]]', '?', 'g')` ile `*_safe` değişkenleri eklendi.
  - Karşılaştırmalar ham değerle yapılmaya devam ediyor.
  - v1 sorgusundaki kullanılmayan `connected_database`/`connected_role` sütunları kaldırıldı (QA B3).
- **Kanıt:** QA B18 (yalnızca `*_safe` ve sayısal/sınıf değişkenleri echo ediliyor); N1 çıktıları.

### U4 — TLS kapısı: istemci atlaması (N3)
- **Satırlar:** 576–659 (P6b)
- **Bulgu:** Kapı yalnızca sunucuya gelen son atlamayı (`inet_server_addr`, `pg_stat_ssl`) görüyordu. İstemci uzak bir ada bağlanıp sunucu makinesindeki bir proxy/tünel üzerinden loopback ile gelirse "tcp-loopback" kabul ediliyordu.
- **Güvenlik etkisi:** İstemci–proxy atlaması şifresiz olsa da denetim başarılı sayılıyordu.
- **Değişiklik:**
  - psql `HOST` değeri socket/loopback/remote olarak sınıflanıyor.
  - TLS yoksa yalnızca her iki taraf da yerel ise kabul ediliyor.
  - `allow_insecure_transport=1` yalnızca devreye girdiğinde `HGS2_AUDIT_WARNING: insecure_transport_allowed` yazılıyor; gereksizse BİLGİ satırı yazılıyor.
  - Literallerde ters eğik çizgi yok (`standard_conforming_strings`'ten bağımsız; QA B12).
- **Önceki davranış:** D04 (`host=fake-remote.example hostaddr=127.0.0.1 sslmode=disable`) → 0 / PASS.
- **Yeni davranış:**
  - T6 → 3 / `insecure_transport`; X3 (gerçek TCP proxy üzerinden) → 3 / `insecure_transport` (PG 12, 18)
  - T9/X4 (aynı yol + TLS) → PASS
  - T7 (`allow=1`) → 0 + WARNING, doğrulayıcı FAIL; T7b (uyarı açıkça kabul edildi) → PASS
  - T8 (`allow=true`) → 3; T10 → PASS + "gerekmedi" bilgisi
  - Birim testi 19 girdi × 2 sürüm = 38/38 doğru

### U5 — Rol üyeliğiyle süper kullanıcı; en az yetki uyarısı (N2)
- **Satırlar:** 701–782 (P8)
- **Bulgu:** Süper kullanıcı bir role üye olan rol (her an `SET ROLE` ile süper kullanıcı olabilir) kabul ediliyordu.
- **Güvenlik etkisi:** En az yetki ilkesi ihlal ediliyordu; `allow_superuser` kontrolü dolaylı yoldan atlanabiliyordu.
- **Değişiklik:**
  - `pg_has_role(session_user|current_user, r, 'MEMBER')` ile süper kullanıcı rol üyeliği arandığında → `superuser_membership` ile durdurma.
  - İzin kullanılırsa `HGS2_AUDIT_WARNING: superuser_allowed`.
  - CREATEROLE/BYPASSRLS/REPLICATION veya `pg_execute_server_program`, `pg_read_server_files`, `pg_write_server_files`, `pg_read_all_data`, `pg_write_all_data` üyeliği varsa → `HGS2_AUDIT_WARNING: audit_role_excess_privilege`.
- **Önceki davranış:** D02 → 0 / PASS; D03 → 0 / PASS (uyarısız).
- **Yeni davranış:**
  - A30 → 3 / `superuser_membership`; A31 (`allow=1`) → 0 + WARNING, FAIL
  - A32 → 0 + WARNING, FAIL
  - A14–A18 değişmedi (3 / `superuser_connection`); A17 artık WARNING üretiyor ve yalnızca uyarı kabul edilirse PASS (A17b)

### U6 — Denetim rolünün kendi kalıcı ayarları raporlanıyor (N5)
- **Satırlar:** 934–1000 (Bölüm 4)
- **Bulgu:** Denetim oturumunu manipüle etmeye yönelik kalıcı ayarlar (ör. `ALTER ROLE <denetim> IN DATABASE … SET search_path = evil, pg_catalog`) raporda görünmüyordu.
- **Değişiklik:**
  - WHERE koşulu `r.rolname IN ('hgs2_perftest', session_user)` oldu.
  - `name_suggests_secret` sınıflaması eklendi.
- **Kanıt:**
  - S3 (4 sürüm): saldırı altında doğru parametrelerle PASS ve çıktıda `hgs2_auditor | search_path | evil, pg_catalog | t` satırı.
  - Katalog doğrulaması "denetim rolu kalici ayari gorunur ve maskeli".

### U7 — 5.4a yetki kaynağı ayrımı (N6)
- **Satırlar:** 1094–1148
- **Bulgu:** Etkin yetki görünüyordu ama kaynağı (sahiplik / doğrudan ACL / PUBLIC / rol üyeliği) ayrılmıyordu. Yorumdaki "sahip = tüm yetkiler" ifadesi de yanlıştı (sahip kendi yetkisini REVOKE edebilir).
- **Değişiklik:** `direct_acl`, `public_acl`, `privilege_source` sütunları eklendi (superuser | sahiplik | dogrudan ACL | PUBLIC | dolayli (rol uyeligi) | -); yorum düzeltildi.
- **Kanıt:** Katalog doğrulamaları:
  - users SELECT/INSERT = `dogrudan ACL`
  - logs SELECT = `dolayli (rol uyeligi)`
  - admins SELECT = `-` (`any_column = t`)
  - 18 tam çıktıda 33/33

### U8 — 5.5b rol yoksa da sequence listesi (N7)
- **Satırlar:** 1238–1276
- **Değişiklik:** `CROSS JOIN me` yerine `LEFT JOIN me ON true` (yorumda "TÜM sequence'lar" deniyordu ama rol yoksa sonuç boş dönüyordu).
- **Kanıt:** Statik inceleme; mevcut senaryolarda sonuç değişmedi (5.5b doğrulamaları 33/33).
- **Not:** "Rol yok" durumu ayrıca çalıştırılarak test edilmedi.

### U9 — Gizli değer ve bağlantı bilgisi sızıntıları (N1)
- **Satırlar:**
  - 1399–1449 (5.11 `proconfig_masked`, `secdef_search_path_unpinned`)
  - 1481–1503 (5.14b `option_names`, `options_reference_hibrit_giris_db`)
  - 1505–1533 (5.15 literal maskeleme)
- **Bulgu:** 2. aşamada eklenen sorgular ham değer basıyordu:
  - fonksiyon düzeyi `SET` değerleri (token)
  - politika ifadelerindeki literal'ler
  - FDW sunucu seçenekleri (host/port/dbname)
- **Güvenlik etkisi:** Parola/token/bağlantı bilgisi denetim çıktısına (ve onu saklayan her yere) taşınıyordu.
- **Değişiklik:**
  - 5.11: Bölüm 4 ile **aynı** izin listesi (QA B13: 15 girdi, eşit).
  - 5.14b: yalnızca seçenek adları ve hibrit bayrağı.
  - 5.15: `'…'` sabitleri `'<maskelendi>'` oluyor.
- **Önceki davranış:** D01 → `SENTETIK-TOKEN-FN`, `SENTETIK-TOKEN-POL` açık metin; srvoptions'ta `sentetik-prod-host.invalid`. O5 (4 sürüm) aynı sızıntıları gösteriyor.
- **Yeni davranış:**
  - Son turdaki karşılaştırma dışı 344 çalıştırmanın stdout ve stderr'inde 7 sentetik gizli değerin hiçbiri yok.
  - Maskelenen alanların adı ve sınıflaması görünür kalıyor: `hgs2.api_token=<maskelendi>, search_path=pg_catalog`; `host, port, dbname | t`; `((device_id)::text <> '<maskelendi>'::text)`.

### Belge — `-v ON_ERROR_STOP=1` komut satırında zorunlu (yeni bulgu N9)
- **Satırlar:** 73–78 (başlık)
- **Bulgu (psql davranışı; betikten düzeltilemez):** Denetim, komut satırında `ON_ERROR_STOP` verilmemiş bir sarmalayıcının **son satırında** `\i` ile çağrılırsa her durdurma `HGS2_AUDIT_ABORT` yazıyor ama psql **çıkış kodu 0** veriyor.
- **Kanıt:** W2, W4 (4 sürüm) → 0 / ABORT / doğrulayıcı FAIL. Belgelenen komut satırıyla (W3) → 3. Sarmalayıcıda sonraki bir komut varsa (Wd, deneme) → 3.
- **Karar:** Kendi oturumunu sonlandırarak (`pg_terminate_backend`) çıkış kodunu zorlama seçeneği reddedildi. Bu, salt okunur araca oturum öldüren bir yan etki ekler; pooler'da ve etkileşimli yeniden bağlanmada davranış öngörülemez. Bunun yerine başlık uyarısı ve doğrulayıcı kuralı kullanıldı.

### Başlık ve belge güncellemeleri
- Test edilen ve edilmeyen sürümler açıkça yazıldı.
- Üç TLS güvencesinin ayrımı yazıldı.
- Başarı kuralları (7 koşul) ve uyarı işaretçileri eklendi.
- `\i` ve etkileşimli kullanım etkileri eklendi.
- stdout/stderr'in ayrı yakalanması ve `-o` davranışı eklendi.
- 3. aşama değişiklik listesi (U1–U9) eklendi.

## Değiştirilmeyenler (incelendi, doğru bulundu)
- P1/P2/P3 transaction mantığı (sonda dahil).
- `SET LOCAL search_path` sabitlemesi.
- P6 host/port, P7 system_identifier.
- 2.x, 3.x, 5.1–5.10, 5.12–5.14, 5.16, 5.17.

Bunlar biçimsel nedenlerle değiştirilmedi. Bağımsız saldırı ve regresyon testleri `FINAL_SECURITY_AUDIT.md` içindedir.
