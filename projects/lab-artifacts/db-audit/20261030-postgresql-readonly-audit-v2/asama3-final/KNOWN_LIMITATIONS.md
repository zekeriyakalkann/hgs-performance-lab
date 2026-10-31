# KNOWN_LIMITATIONS — HGS2 PostgreSQL Read-Only Audit V2 (3. aşama)

Dosya: `postgresql_readonly_audit_v2.sql`, SHA-256 `5916d12bb1194b6978cbe480b60a2d2311dee6afe3e3da3dabf93bb7a96aa40b`

Her madde test edilmiş bir davranışı ya da açıkça test edilmemiş bir alanı tanımlar.

## A. Doğrulanamayan güvenceler (tasarım sınırı)

1. **TLS sertifika ve ana bilgisayar adı doğrulaması SQL ile kanıtlanamaz.** Sunucu yalnızca kendisine gelen son atlamanın TLS kullanıp kullanmadığını görür.
   - `sslmode=require` ile `verify-full` sunucu tarafında aynı görünür.
   - Sertifika ve ad doğrulaması yalnızca istemcide (`sslmode=verify-full` + `sslrootcert`) uygulanır.
   - Kanıt: T3, T4 ve T5 testlerinde reddi istemci yaptı (çıkış 2).
2. **system_identifier kriptografik bir kimlik değildir.** Fiziksel replikalar ve aynı temel yedekten oluşturulan kopyalar aynı değeri taşır (R1: replika, primary'nin kimliğiyle PASS). Betik recovery durumunu raporlar, ama primary ile bir klonu ayırt edemez. Host ve port da kimlik kanıtı değildir.
3. **Süper kullanıcı düzeyinde ele geçirilmiş bir sunucu kapsam dışıdır.** Süper kullanıcı `pg_catalog` nesnelerini, katalog içeriğini ve `pg_control_system()` sonucunu etkileyebilir.
4. **`pg_hba.conf` sorgulanmaz.** ACL sonuçları gerçek bağlantı davranışının tamamını göstermez.
5. **Paylaşılan kataloglar** (Bölüm 2–4) küme geneli durumu gösterir. Bölüm 5 yalnızca bağlı veritabanını gösterir; `hibrit_giris_db`'nin şeması hakkında sonuç vermez.
6. **TLS kapısının istemci sınıflaması psql'in `HOST` değerine dayanır.**
   - `localhost` hosts dosyasında başka bir yere yönlendirilmişse istemci tarafı "loopback" sayılır. Bu durumda sunucu tarafı yine de uzak adresi görür ve TLS ister; yalnızca sunucu makinesinde bir proxy varsa kör nokta oluşur.
   - Çoklu host bağlantı dizelerinde yalnızca bağlanılan host değerlendirilir.

## B. Kullanım hatasına bağlı riskler

7. **`\i` ile sarmalama (psql davranışı).** Komut satırında `-v ON_ERROR_STOP=1` verilmemiş bir sarmalayıcının son satırında `\i` ile çağrılırsa, her durdurma ABORT işaretçisi yazar ama **çıkış kodu 0** olur (W2/W4, 4 sürüm).
   - Belgelenen komut satırıyla çıkış 3 olur (W3).
   - Doğrulayıcı her iki durumu da FAIL sayar.
   - Karar hiçbir zaman yalnızca çıkış koduna dayanmamalıdır.
8. **P3 transaction sondası işaretçisizdir.** P2 atlatılırsa sonda PostgreSQL hatasıyla durdurur (çıkış 3, ABORT işaretçisi yok; A25, M3, M5–M7, R4). Otomasyon "3 + işaretçi yok" durumunu BAŞARISIZ saymalıdır. Bunun için sondanın PostgreSQL'in `check_transaction_isolation` davranışına bağlı olduğu bilinmelidir; her yeni ana sürümde yeniden test edilmelidir.
9. **Etkileşimli kullanım test edilmedi (TTY).** psql belgelerine göre etkileşimli modda ON_ERROR_STOP psql'i kapatmaz, yalnızca betiği keser:
   - BEGIN'den sonraki bir durdurmada oturum iptal edilmiş READ ONLY transaction'da kalır ve ROLLBACK gerekir.
   - Açık bir kullanıcı transaction'ı içinde çağrılırsa o transaction iptal olur.
   - Betik psql ayarlarını (ON_ERROR_STOP, AUTOCOMMIT, çıktı biçimi, ECHO) oturum için değiştirir.
10. **Çıktı kanalları.**
    - stdout ve stderr AYRI yakalanmalıdır; `2>&1` ile birleştirilirse "stderr boş" kuralı uygulanamaz.
    - `-o` ile sorgu sonuçları dosyaya gider; işaretçiler yine stdout'tadır (E10).
11. **İzin bayrakları.**
    - `allow_superuser=1` ve `allow_insecure_transport=1` yalnızca tam "1" ile etkinleşir.
    - Devreye girdiklerinde `HGS2_AUDIT_WARNING` yazılır; otomasyon bu uyarıyı açıkça kabul etmelidir. Her bayrak yalnızca kendi kararını etkiler (QA B16).
12. **Uyumluluk kapılarını sahtelemek.** `VERSION_NUM` / `SERVER_VERSION_NUM` `-v` ile ezilebilir (E15). Sunucu sürümü Bölüm 1'de sunucu tarafında yeniden denetlenir. psql kapısı ise yalnızca uyumluluk içindir.

## C. Bilinçli katılık (olası yanlış pozitifler)

13. **`superuser_membership` katıdır.** PostgreSQL 16+'da SET/INHERIT seçenekleri kapalı, yani fiilen kullanılamayan bir üyelik de reddedilir.
14. **`audit_role_excess_privilege` uyarısı** `pg_read_all_data` gibi denetim ekiplerinde yaygın rollerde de çıkar. Kabul açık bir karar olmalıdır.
15. **TLS kapısı, sunucu makinesinde TLS'i sonlandıran bir pooler/proxy arkasında** (istemci→proxy TLS, proxy→PG loopback düz) durdurur. SQL istemci atlamasının şifreli olduğunu göremez; `allow_insecure_transport=1` ile bilinçli olarak geçilebilir.
16. **Host karşılaştırması büyük/küçük harfe duyarlıdır** (`expected_host` psql'e verilen değerle birebir aynı olmalı).
17. **Gizli değer maskeleme izin listesine dayanır.**
    - İzin listesindeki 15 ayarın (search_path, role, timeout'lar, kütüphaneler …) değeri açık gösterilir.
    - Politika ifadelerinde yalnızca tırnaklı sabitler maskelenir; sayısal sabitler ve tanımlayıcılar görünür.
    - 5.14b'de FDW seçenek değerleri hiç gösterilmez, yalnızca adlar ve `hibrit_giris_db` bayrağı.

## D. Test edilmeyenler

18. **Sunucu ve istemci sürümleri:** PostgreSQL 13/14/15 ve psql 10/11/13/14/15 test edilmedi. psql 10/11 betik tarafından reddedilir (alt sınır 12).
19. **Platform:** Yalnızca Windows (EDB taşınabilir ikili dosyaları ve kurulu 18.6) kullanıldı; Linux derlemeleri test edilmedi.
20. **Kurulmayan bileşenler:** Unix soketi (Windows'ta MAX_PATH sınırı nedeniyle kurulmadı), gerçek pgbouncer/pgpool (yalnızca TCP proxy), SCRAM + `channel_binding=require` (test kümeleri `trust`), loopback dışı gerçek ağ (yalnızca `hostaddr` ile benzetildi).
21. **Diğer test edilmeyen durumlar:**
    - PG 17+ `login` event trigger'ı denetim oturumunda kod çalıştırabilir. Bunu yalnızca süper kullanıcı oluşturabilir. 5.13 raporlar, ama davranış test edilmedi.
    - `local_preload_libraries` / `session_preload_libraries` ile denetim oturumuna kütüphane yüklenmesi test edilmedi. Bölüm 4 bu ayarları raporlar.
    - Katalog SELECT yetkileri PUBLIC'ten geri alınmış sertleştirilmiş kurulumlar.
    - `statement_timeout` / `lock_timeout` tetiklenmesi.
    - Saat geri ayarı gibi zaman damgası anomalileri. Yerine P2'yi kaldıran mutasyonlarla sondanın tek başına yeterliliği gösterildi.
    - 5.5b'de `hgs2_perftest` rolünün hiç olmadığı durum (U8).
22. **Gerçek hedef çalıştırılmadı.** Gerçek `hgs2_perftest_db` üzerinde hiçbir çalıştırma yapılmadı (kapsam dışı).
