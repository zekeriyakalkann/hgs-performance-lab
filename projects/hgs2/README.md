# HGS2 — Hibrit Giriş Sistemi

Parmak izi / kart tabanlı giriş terminalleri için Spring Boot REST API'si, yönetim web arayüzü ve ESP32 / Arduino
donanım kodları. Performance Lab bu uygulamayı yalnızca `perftest` profiliyle, izole bir test veritabanına karşı
çalıştırır.

> **Kaynak ve sahiplik.** Uygulama kodu ServetAlav001 ve ekibi tarafından geliştirilmiştir (özgün depo:
> `github.com/ServetAlav001/hgs2`, `main` dalı, uç commit `ad255a4`). `perftest` profili ve güvenlik denetimi
> (`Config/PerfTestSafetyGuard.java`, `application-perftest.properties`, `PerfTestProfileRequired*`) Performance Lab
> çalışması kapsamında eklenmiştir.

## Dizin yapısı

Özgün deponun dizin düzeni, geçmişle uyumlu kalması için değiştirilmemiştir.

```
projects/hgs2/
├── hgs2-main/
│   └── HGS-main/
│       ├── HGS/                         Spring Boot uygulaması (Maven, pom.xml)
│       │   ├── src/main/java/com/HibritGirisSistemi/HGS/
│       │   │   ├── Config/              PerfTestSafetyGuard (yalnızca perftest profilinde yüklenir)
│       │   │   ├── Controller/          /api/auth, /api/users, /api/devices, /api/logs, /api/sensor, /api/terminal
│       │   │   ├── Entity/ Repository/ Service/
│       │   ├── src/main/resources/
│       │   │   ├── application.properties           varsayılan profil (yerel PostgreSQL, 0.0.0.0:8080)
│       │   │   ├── application-perftest.properties  izole performans testi profili
│       │   │   └── static/                          yönetim arayüzü (HTML/CSS/JS)
│       │   └── src/test/                PerfTestProfileRequired: profilsiz test bağlamlarını durdurur
│       └── donanım kodları/
│           ├── esp32                    ESP32 terminal sketch'i (Wi-Fi + HTTP)
│           └── ardunio                  Arduino terminal sketch'i (OLED menü, parmak izi)
├── .vscode/ , hgs2-main/.vscode/        özgün depodaki editör ayarları
├── fix_python.ps1, test.txt             özgün depodan gelen yerel yardımcı dosyalar
└── README.md                            bu dosya
```

## Gereksinimler

* Java 21, Maven Wrapper (`mvnw` / `mvnw.cmd`)
* Spring Boot 4.0.x (`spring-boot-starter-webmvc`, `-data-jpa`, `-actuator`)
* PostgreSQL

## Yapılandırma ve kimlik bilgileri

Depoda **hiçbir parola yoktur**. Özgün depoda açık yazılmış olan değerler, içe aktarma sırasında tüm geçmişte
maskelenmiştir (bkz. [`docs/security/SECURITY.md`](../../docs/security/SECURITY.md)):

| Dosya | Anahtar | Depodaki değer | Nasıl verilir |
|---|---|---|---|
| `application.properties` | `spring.datasource.password` | `${HGS_DB_PASSWORD}` | `HGS_DB_PASSWORD` ortam değişkeni |
| `donanım kodları/esp32` | `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_IP` | `YOUR_WIFI_SSID`, `YOUR_WIFI_PASSWORD`, `YOUR_SERVER_IP` | Karta yüklemeden önce yerel kopyada doldurun; doldurulmuş hâlini commit etmeyin |

Varsayılan profil gerçek veritabanına (`hibrit_giris_db`, `ddl-auto=update`) bağlanır; performans testleri için
kullanılmamalıdır.

### `perftest` profili

`--spring.profiles.active=perftest` ile etkinleşir. `PerfTestSafetyGuard`, aşağıdakilerden biri sağlanmazsa uygulamayı
veritabanı bağlantısı ve HTTP portu açılmadan durdurur:

* `server.address=127.0.0.1`, `server.port=18080`
* veritabanı adresi yalnızca loopback ve yalnızca `hgs2_perftest_db`
* kullanıcı adı / parola yalnızca `HGS_PERFTEST_DB_USERNAME` / `HGS_PERFTEST_DB_PASSWORD` ortam değişkenlerinden;
  `postgres` kullanılamaz
* `ddl-auto` yalnızca `none` / `validate`
* test kullanıcısının `hibrit_giris_db`'ye bağlanma denemesi PostgreSQL yetki hatasıyla (SQLState 42501) reddedilir

Test sınıfları `PerfTestProfileRequired` (`src/test/resources/META-INF/spring.factories`) tarafından da korunur:
etkin profili tam olarak `perftest` olmayan her Spring test bağlamı, veri kaynağı oluşturulmadan durdurulur.

## Derleme ve çalıştırma

```powershell
cd projects/hgs2/hgs2-main/HGS-main/HGS
.\mvnw.cmd -DskipTests package
```

Performance Lab üzerinden izole çalıştırma (ön koşullar ve ayrıntılar:
[`projects/performance-lab/README.md`](../performance-lab/README.md), "Gerçek HGS2'yi perftest profiliyle başlatma"):

```powershell
hgs2-lab hgs2 run --config DOSYA --java JAVA_EXE --jar JAR `
    --app-dir <mutlak yol>\projects\hgs2\hgs2-main\HGS-main\HGS [--scenarios DOSYA]
```

> Testler (`mvnw test`) `perftest` profili ve izole test veritabanı gerektirir; ortam değişkenleri yoksa test bağlamı
> bilinçli olarak başlamaz.

## Git geçmişi

Özgün `main` dalının 5 commit'i yazar, tarih ve mesajlarıyla korunarak `projects/hgs2/` altına aktarılmıştır
(birleştirme commit'i: "Merge HGS2 application history into projects/hgs2"). Kimlik bilgisi maskelemesi nedeniyle
commit kimlikleri özgün depodakilerden farklıdır; eşleme tablosu [`docs/UNIFIED_REPOSITORY_REPORT.md`](../../docs/UNIFIED_REPOSITORY_REPORT.md)
içindedir. Özgün depodaki ilişkisiz `master` dalı (ESP entegrasyon güncellemeleri, `ffe0849..9bbe2cd`) aktarılmamıştır.

```powershell
git log --oneline -- projects/hgs2
```
