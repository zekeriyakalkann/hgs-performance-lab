# Güvenlik

## Temel kurallar

* Depoya parola, token, özel anahtar, `.env` dosyası, gerçek kullanıcı verisi veya veritabanı dökümü girmez.
  Kök `.gitignore`: `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `.netrc`, `.pgpass`, `pgpass.conf`.
  Performance Lab ayrıca `configs/**/*.json` dosyalarını dışlar (yalnızca `*.example.json` izlenir) ve `results/`
  çıktısını depoya almaz.
* Kimlik bilgileri yalnızca ortam değişkenlerinden okunur:
  * HGS2 varsayılan profil: `HGS_DB_PASSWORD`
  * HGS2 `perftest` profili: `HGS_PERFTEST_DB_USERNAME`, `HGS_PERFTEST_DB_PASSWORD`
* Performance Lab yalnızca loopback hedeflere istek gönderir; testler loopback dışı bağlantıları engeller.
* Gerçek (production) PostgreSQL'e bağlanan, servis başlatan/durduran veya SQL çalıştıran bir otomasyon depoda yoktur;
  denetim SQL'i yalnızca izole test kümelerinde çalıştırılmıştır.

## HGS2 geçmişindeki kimlik bilgileri (birleştirme sırasında maskelendi)

Özgün HGS2 deposunda (`github.com/ServetAlav001/hgs2`) aşağıdaki değerler açık metin olarak commit edilmişti.
İçe aktarma öncesinde **tüm commit'lerde** maskelendi; bu depoda hiçbir sürümde bulunmazlar:

| Dosya | Anahtar | Maskelenmiş değer |
|---|---|---|
| `application.properties` | `spring.datasource.password` (`postgres` süper kullanıcısı) | `${HGS_DB_PASSWORD}` |
| ESP32 sketch'i | `WIFI_SSID` | `"YOUR_WIFI_SSID"` |
| ESP32 sketch'i | `WIFI_PASSWORD` | `"YOUR_WIFI_PASSWORD"` |
| ESP32 sketch'i | `SERVER_IP` (yerel ağ adresi) | `"YOUR_SERVER_IP"` |

**Gerekli eylem (depo dışında):** Bu değerler özgün açık depoda hâlâ görünür durumdadır. PostgreSQL `postgres`
parolası ve Wi-Fi parolası değiştirilmelidir. Ayrıca varsayılan profilde `postgres` süper kullanıcısı yerine yetkisi
sınırlı ayrı bir uygulama rolü kullanılması önerilir.

## Lab Artifacts güvenlik incelemesi

* Gizli bilgi taraması (özel anahtar, GitHub/AWS token, tam SCRAM doğrulayıcısı, kimlik bilgili bağlantı dizesi,
  HGS2'den gelen gerçek değerler): eşleşme yok. Tek bağlantı dizesi eşleşmesi, `test_sanitize.py`'deki bilinçli sahte
  `postgresql://fake:FAKE-SECRET-123@db.example.invalid` değeridir.
* Belgelerdeki parolalar sahte test değerleridir (`SENTETIK-PAROLA…`, `S3-perftest-…`, `S4-audit-…`).
* `certs-public/` yalnızca açık sertifikalar içerir (özel anahtar yok).
* Dışlanan içerik ve gerekçeleri: [`projects/lab-artifacts/README.md`](../../projects/lab-artifacts/README.md).
* Kanıtlarda yerel makine adı ve Windows kullanıcı dizini yolları bulunur; gizli değildir ve SHA-256 mühürlerini
  bozmamak için değiştirilmemiştir.

## Bildirim

Bir güvenlik sorunu fark ederseniz herkese açık bir issue açmak yerine depo sahibiyle doğrudan iletişime geçin.
