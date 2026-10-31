# INCOMPLETE_STATUS — `iso18-20261030T230745`

**Sınıflandırma: FAIL (Aşama 2.5) / V1 TAMAMLANMADI**. Başarılı bir çalıştırma olarak kullanılamaz ve teslim edilmez.

| Alan | Değer |
|---|---|
| RunId | `iso18-20261030T230745` (Aşama 1 çıktısında yazdırılan değer) |
| Test kökü (silindi) | `%LOCALAPPDATA%\hgs2-iso\iso18-20261030T230745` |
| Son PASS | `S2.4-conf PASS` |
| Durma | `RUNNER-STOP FAIL GUARD: test postmaster bulunamadi` (Aşama 2.5) |
| Çalıştırma biçimi | Tek PowerShell 5.1 süreci (EK R1-6). Çalıştırıcı R1, SHA-256 `3d214f5645820e1375ed027b3d302b0a80465bab28f618ae88e173a626ec824a` |

## Kayıtlı aşamalar (`evidence\stage-results.txt`)

```text
2026-10-30T23:07:47.0397104+03:00 S1-live-snapshot RECORDED
2026-10-30T23:07:54.5238116+03:00 S2.2-initdb PASS
2026-10-30T23:07:55.4968778+03:00 S2.3-certs PASS
2026-10-30T23:07:55.9269792+03:00 S2.4-conf PASS
2026-10-30T23:07:57.0721252+03:00 RUNNER-STOP FAIL GUARD: test postmaster bulunamadi
```

## Kök neden (EK R1-8)

- Test kümesi başarıyla başladı.
  - `log\postgres.log`: `listening on IPv4 address "127.0.0.1", port 55438`, `listening on IPv6 address "::1", port 55438`, `database system is ready to accept connections`.
- Runbook §2.5'teki kapı ise `$_.CommandLine -like "*$Data*"` ile `\` ayırıcılı yolu arar.
- `pg_ctl` yolu `/` ile kanonikleştirir. `postmaster.opts` içeriği:
  `C:/Program Files/PostgreSQL/18/bin/postgres.exe "-D" "C:/Users/Ceng Zeki/AppData/Local/hgs2-iso/iso18-20261030T230745/data"`.
- Bu nedenle kapı hiçbir zaman eşleşmez. Hata bir **runbook uygulama kusurudur**; izolasyon veya güvenlik ihlali değildir.
- Aynı kusur §10.1 ve §10.4'teki negatif kapıları **anlamsız biçimde geçirir**. Düzeltme EK R1-8'dedir.

## Hata sonrası davranış

- Çalıştırıcı DUR'du.
- Yalnızca test kümesi durduruldu: `pg_ctl -D <test data> -m fast -w stop`, çıkış 0. Günlükte `received fast shutdown request` ve `database system is shut down` satırları var.
- Canlı servis değişmedi (konsol günlüğünün sonu: `State Running`, `Pid 4708`, aynı `Created`; 5432 aynı).
- Aşama 3 ve sonrası **çalıştırılmadı**. Hiçbir rol, veritabanı veya denetim işlemi yapılmadı.

## Kapanış (`review\closeout_script_v2.ps1`, sonuçlar `review\closeout-results.txt`)

1. Durum:
   - `pg_ctl status` = 3;
   - `postmaster.pid` yok;
   - test postmaster süreci 0;
   - port 55438 boş.
2. Canlı servis, bu çalıştırmanın `live-start.json` dosyasıyla birebir aynı.
3. Gizli bilgi taraması:
   - Özgün §10.2 taraması **NOT RUN** kaldı, çünkü süreç sonlandığında `$TestSecrets` kayboldu.
   - pgpass kaynaklı parola taraması (`postgres`; konsol günlüğü ve transcript dahil): **0**.
   - `-----BEGIN`: **0**.
   - pgpass satır biçimi: **0**.
   - `PRIVATE KEY`: İlk denemede **2** eşleşme bulundu ve arşivleme durdu.
     - İki eşleşme de `evidence\00-inputs\runner_v1_single_session.ps1` içindeki tarama deseni satırlarıydı (EK R1-9).
     - Bu dosya, SHA-256'si çalıştırıcıyla eşleştiği için yalnızca anahtar taramasından dar bir istisnayla hariç tutuldu.
     - Yeniden tarama: **0**.
4. Arşiv:
   - `evidence\` (9 dosya) kopyalandı; SHA-256 kümeleri eşit.
   - Ek olarak `log\postgres.log` kopyalandı.
   - `review\` altına konsol günlüğü, transcript, HGS2 conf bloğu ve envanter eklendi.
   - `cfg\` ve `certs\` **kopyalanmadı**.
5. Silme:
   - 7 kapı + `postmaster.pid` + RunId onayı → **PASS**. Bu çalıştırmada süreç sayımı düzeltilmiş karşılaştırmayla yapıldı.
   - Önce pgpass, ardından test kökü silindi.
6. Bitiş: Canlı servis değişmedi.

## Sonraki çalıştırma

- Düzeltilmiş çalıştırıcı R2 ile yeni RunId `iso18-20261030T231228` başlatıldı.
- Sonuç: **SONUC: V1 TAMAMLANDI**.
- Arşiv: `role-design\iso-runs\iso18-20261030T231228\`.
