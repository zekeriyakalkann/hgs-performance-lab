# KNOWN_LIMITATIONS — V1 izole küme yürütmesi

- Bu liste, `asama3-final\KNOWN_LIMITATIONS.md` dosyasındaki 21 maddeye **ek olarak** geçerlidir. O maddeler değişmedi ve hâlâ geçerlidir.
- Aşağıdaki maddeler bu yürütmeye özgüdür.

## A. Kapsam sınırları

1. **Gerçek kümeye ilişkin hiçbir şey doğrulanmadı.** Gerçek veritabanına bağlanmak yasaktı.
   - Gerçek kümede `hgs2_perftest`'in bugün 42501 aldığı **UNVERIFIED** kalır (plan §6.5, P5).
   - Gerçek kümede `hibrit_giris_db`'nin PUBLIC CONNECT durumu bilinmiyor.
   - Gerçek `pg_hba.conf` içeriği bilinmiyor.
2. **V1 dışı testler NOT RUN durumundadır:** T2–T7, T8-b/c/e, T9 (IPv6 bağlantısı), T10 ve RC-02/04/05.
   - `::1:55438` dinleyicisi oluştu, ancak IPv6 üzerinden `hgs2_audit` bağlantısı sınanmadı.
3. **Sahiplik kapsamı:** Diğer veritabanlarındaki şema ve nesne sahipliği **doğrudan doğrulanmadı**.
   - Doğrudan doğrulanan: `hgs2_perftest_db`'de sahiplik yok.
   - Dolaylı gösterge: Paylaşılan `pg_shdepend` kataloğunda sahiplik kaydı yok.
4. **TLS doğrulaması:** Bağlantılar `sslmode=require` ile yapıldı.
   - Sunucu sertifikası ve ana bilgisayar adı istemcide doğrulanmadı (`verify-full` T10 kapsamındadır).
   - `tls= t` yalnızca sunucuya gelen son atlamanın şifrelendiğini gösterir.
5. **`has_db_temporary = t`:** PUBLIC TEMPORARY yetkisinin artığıdır. Matris R10 gereği yalnızca kayda geçti.
   - `postgres`, `template1` ve `other_db` için `acl_connect = t` PUBLIC varsayılanıdır. Bu veritabanlarını yalnızca pg_hba kapatır.

## B. Yürütme yöntemi sınırları

6. **Tek süreçli çalıştırıcı:**
   - Runbook blokları elle, blok blok yapıştırılmadı. Tek `powershell.exe` sürecinde, aynen ve aynı sırayla çalıştırıldı.
   - Fark listesi: FINAL_EXECUTION_REPORT §3, D1–D8.
   - Doğrulanabilirlik: Blok başına SHA-256 `runner_provenance.txt` içindedir; çalıştırıcı ve onu üreten betik arşivin `runner\` klasöründedir.
   - Runbook bu yöntemi açıkça öngörmez. EK R1-6 yöntemi öneri olarak belgeler.
7. **§10.4 RunId onayı:**
   - `Read-Host` yerine onay dosyası kullanıldı.
   - Onayı veren, yürütmeyi yapan otomasyon operatörüdür (Claude Code). Kullanıcı görev tanımında silmeyi yetkilendirmişti.
   - Operatör, onaydan önce arşivi, aşama sonuçlarını, postmaster'ın kapalı olduğunu ve RunId eşleşmesini bağımsız olarak doğruladı.
   - Bu adımda **insan** tarafından verilmiş ayrı bir onay yoktur.
8. **Runbook V1 kusurları (EK R1-8, R1-9):** Runbook V1 dosyası **değiştirilmedi**.
   - V1 olduğu gibi kullanılırsa §2.5 her zaman başarısız olur.
   - §10.1 ve §10.4 negatif süreç kapıları her zaman anlamsız biçimde geçer.
   - Sonraki kullanımlarda EK R1 birlikte uygulanmalıdır.
9. **İşaretçi sırası (belge farkı):**
   - Runbook §6 beklenen çıktıda `HGS2_AUDIT_PREFLIGHT_OK` satırını `tasima=` satırından önce gösterir.
   - Gerçek çıktıda `tasima=` 20. satırda, `HGS2_AUDIT_PREFLIGHT_OK` 24. satırdadır.
   - Doğrulayıcı kurallarını etkilemez: PREFLIGHT, COMPLETE'ten (277. satır) önce gelir. Bu, runbook'taki örnek sıranın yanlış olduğunu gösteren bir belge farkıdır.
10. **Yerelleştirme:** İstemci araçlarının mesajları Türkçe yerel ayarla görüntülendi (`psql: hata (error)`, `SATIR`, `YER`, `AYRINTI`, `(6 satır)`).
    - Sunucu mesajları `lc_messages = C` (initdb `--locale=C`) olduğu için İngilizcedir.
    - Runbook'un regex kapıları yalnızca sunucu mesajlarına bakar. Bu nedenle etkilenmedi.
    - Konsol günlüğü CP857 kodlamasıyla kaydedildi.

## C. Eksik çalıştırmalar ve temizlik

11. `iso18-20261030T223605` ve `iso18-20261030T230745` için özgün §10.2 parola taraması **NOT RUN** durumundadır.
    - Yalnızca pgpass kaynaklı ikame tarama yapıldı (EK R1-2). Her iki çalıştırmada pgpass'ta yalnızca `postgres` satırı vardı.
    - Bu çalıştırmalar `postgres` dışında rol parolası üretmeden durmuştu.
12. `iso18-20261030T223605` kapanışındaki süreç sayımı EK R1-8 kusurunu taşıyordu.
    - Silme kararı bağımsız kanıtlara dayanır: `postmaster.pid` yok, `pg_ctl status` = 3, 55438 boş.
13. **Güvenli silme yok:** NTFS/SSD üzerinde `Remove-Item` içeriği üzerine yazmaz.
    - Silinen test parolaları ve test özel anahtarları kurtarılabilir olabilir.
    - Değerler yalnızca yok edilmiş test kümelerine ve 7 günlük test CA'larına aittir. Canlı sistemle ilişkileri yoktur.
14. **Arşivin `runner\` klasörü** çalıştırma bittikten sonra eklendi.
    - Bu klasör çalıştırmanın kendi `SHA256SUMS.txt` manifestinde değil, `asama4-v1-execution\FINAL_SHA256SUMS.txt` içindedir.
    - Çalıştırıcının SHA-256 değeri (`92deca08…f8a2`) çalıştırma sırasında kanıta yazılan değerle eşleşir.

## D. Kanıt kapsamı

15. **Arşivlenmiş kanıtı olmayan iddialar.** Aşağıdaki iddialar yalnızca yürütme oturumunun çıktısına dayanır; hiçbir arşiv dosyasında kaydı yoktur:
    - Eski çalıştırma kapanışından önce canlı servisin elle yapılan ilk okuması.
    - Çalıştırma sonrasında yapılan bağımsız son kontroller:
      - servis listesinde yalnızca `postgresql-x64-18` bulunduğu;
      - kullanıcı ortamında `PGPASSFILE` tanımlı olmadığı;
      - arşiv üzerinde yapılan sezgisel gizli bilgi taraması.
    - İndirme yapılmadığı; uygulamanın başlatılmadığı ve Maven'ın çalıştırılmadığı.
    - Canlı veri dizinine erişilmediği. Bu iddianın dayanağı yalnızca çalıştırıcı betiğin içeriğidir; dosya erişim günlüğü yoktur.
    - Bu iddiaların kanıtla desteklenen kısımları raporlarda ayrıca belirtilmiştir: kökün yokluğu ve port 55438'in boş olduğu `SUMMARY.txt` ile; başlangıç ve bitiş canlı servis değerleri `live-start.json` / `live-end.json` ile desteklenir.
16. **Kısmi kanıtı olanlar.**
    - TLS sertifikalarının 7 günlük olduğu yalnızca çalıştırıcıdaki `-days 7` komutundan anlaşılır; sertifikalar arşivlenmedi.
    - §10.2'deki `PRIVATE KEY` eşleşme sayısı yazdırılmaz; sonucu yalnızca kapının geçmesinden (`S10.2-secret-scan PASS`) anlaşılır.
    - Test kökü ACL'sinin çıktısı arşivlenmedi.
17. **SHA-256 kapsamı.** `FINAL_SHA256SUMS.txt`, `asama3-final\` klasöründen yalnızca iki dosyayı kapsar: `postgresql_readonly_audit_v2.sql` ve `tools\validate_audit_result.py`.
    - Aynı klasördeki diğer dosyalar ile kök klasördeki 2. aşama SQL dosyası bu teslimatın manifestinde yoktur.
    - Bu dosyalara yazma işlemi yapılmadı. Ancak değişmedikleri bu manifestle **doğrulanmış sayılmaz.**

## E. Geçiş

18. Bu yürütmenin başarısı **gerçek kümeye geçiş onayı değildir.** Plan §10'daki P1–P12 ön koşulları ve §11.2'deki K-1…K-9 kararları geçerlidir.
