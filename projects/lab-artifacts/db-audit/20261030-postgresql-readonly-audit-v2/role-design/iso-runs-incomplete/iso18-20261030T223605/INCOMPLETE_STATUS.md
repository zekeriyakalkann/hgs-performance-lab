# INCOMPLETE_STATUS — `iso18-20261030T223605`

**Sınıflandırma: V1 TAMAMLANMADI**. Başarılı bir çalıştırma olarak kullanılamaz ve teslim edilmez.

| Alan | Değer |
|---|---|
| RunId | `iso18-20261030T223605` (kaynak: görev tanımı) |
| Test kökü (silindi) | `%LOCALAPPDATA%\hgs2-iso\iso18-20261030T223605` |
| Son kaydedilen aşama | `S2.4-conf PASS` (2026-10-30T22:40:12+03:00) |
| Tamamlanmama nedeni | Aşama 2.4'ten sonra PowerShell oturumu kayboldu. Runbook §0.7 ve §12.3 gereği çalıştırma devam ettirilmez |
| Çalıştırılmayan aşamalar | S2.5 (küme hiç başlatılmadı), S3–S11 |
| Kapanış tarihi | 2026-10-30, yaklaşık 23:0x (+03:00); ayrı bir PowerShell süreciyle yapıldı (`review\closeout_script_v1.ps1`) |

## Kayıtlı aşamalar (`evidence\stage-results.txt`, değiştirilmeden kopyalandı)

```text
2026-10-30T22:38:30.9162481+03:00 S1-live-snapshot RECORDED
2026-10-30T22:39:14.7592928+03:00 S2.2-initdb PASS
2026-10-30T22:39:43.8987534+03:00 S2.3-certs PASS
2026-10-30T22:40:12.8206678+03:00 S2.4-conf PASS
```

## Kapanışta yapılanlar (runbook §12.3 ve EK R1)

Ayrıntılar `review\closeout-results.txt` dosyasındadır.

1. **Eski küme başlatılmadı.**
   - `pg_ctl status` çıkışı 3 (sunucu çalışmıyor).
   - `postmaster.pid` yok.
   - Port 55438 dinlenmiyor.
   - Durdurulacak bir süreç olmadığı için `stop` komutu çalıştırılmadı.
2. **Eski parolalar yeniden üretilmedi.** Eski RunId üzerinde hiçbir psql, SQL veya test komutu çalıştırılmadı.
3. **Canlı servis karşılaştırması:** Değerler `live-start.json` ile birebir aynı:
   - `State=Running`
   - `Pid=4708`
   - `Created=2026-10-30T16:29:54.8155590+03:00`
   - PathName aynı
   - 5432 dinleyicileri: `::1:5432 pid=6164; 127.0.0.1:5432 pid=6164`
4. **Gizli bilgi taraması** (EK R1-2). Özgün §10.2 taraması **NOT RUN** kaldı, çünkü `$TestSecrets` kayboldu. Yerine ikame taramalar yapıldı:
   - pgpass kaynaklı parola taraması (`postgres`): **0** eşleşme. Parola yalnızca süreç belleğinde kullanıldı, hiçbir yere yazılmadı.
   - `PRIVATE KEY`: **0**.
   - pgpass satır biçimi: **0**.
5. **Arşiv:**
   - `evidence\` (5 dosya) kopyalandı. Kaynak ve hedefin SHA-256 kümeleri eşit.
   - `review\` altına HGS2 `postgresql.conf` bloğu ve ad/boyut envanteri eklendi.
   - `cfg\pgpass.conf` ve `certs\*.key` **kopyalanmadı**.
6. **Silme** (§10.4 kapıları ve EK R1-4):
   - 7 kapı + `postmaster.pid` yok + RunId'nin görev tanımındaki değerle birebir eşleşmesi → **PASS**.
   - Önce `cfg\pgpass.conf`, ardından test kökü silindi. Kök artık yok.
   - Not (EK R1-8): Bu betikteki süreç komut satırı karşılaştırması `/` ve `\` ayırıcı kusurunu taşıyordu. Silme kararı yine de bağımsız kanıtlara dayanıyordu: `postmaster.pid` yok, `pg_ctl status` = 3 ve 55438 boştu.
7. **Bitiş:** Canlı servis ve 5432 dinleyicileri değişmedi.

## Sınırlar

- `Remove-Item` NTFS/SSD üzerinde güvenli silme (üzerine yazma) garanti etmez. Silinen parola yalnızca yok edilmiş test kümesine aitti; özel anahtarlar 7 günlük test CA'sına aitti.
- Bu çalıştırmanın yerine `iso18-20261030T231228` çalıştırması geçmiştir.
  - Arada yapılan `iso18-20261030T230745` çalıştırması da TAMAMLANMADI olarak arşivlendi.
  - Ayrıntılar: `asama4-v1-execution\FINAL_EXECUTION_REPORT.md`.
