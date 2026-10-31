# Mimari

## Bileşenler

### HGS2 uygulaması (`projects/hgs2/`)

* Spring Boot 4 (Java 21) REST API: `/api/auth`, `/api/users`, `/api/devices`, `/api/logs`, `/api/sensor`,
  `/api/terminal`; JPA ile PostgreSQL; `static/` altında yönetim arayüzü.
* Donanım: ESP32 terminal sketch'i (Wi-Fi üzerinden HTTP ile API'ye bağlanır) ve Arduino terminal sketch'i (OLED menü,
  parmak izi sensörü).
* İki çalışma profili:
  * **varsayılan:** `0.0.0.0:8080`, gerçek veritabanı `hibrit_giris_db`, `ddl-auto=update`.
  * **`perftest`:** `127.0.0.1:18080`, yalnızca `hgs2_perftest_db`, `ddl-auto=none`; `PerfTestSafetyGuard`
    (`BeanFactoryPostProcessor`, en yüksek öncelik) koşullar sağlanmazsa DataSource oluşturulmadan başlatmayı durdurur.

### Performance Lab (`projects/performance-lab/`)

`hgs2_lab` Python paketi ve `hgs2-lab` CLI. Ana modüller:

| Katman | Modüller |
|---|---|
| Yapılandırma ve hedef güvenliği | `config`, `scenarios`, `target_guard` (yalnızca loopback), `port_owner`, `target_process` |
| Yürütme ve ölçüm | `runner`, `execution`, `transport`, `http_transport`, `clock`, `telemetry` (F4) |
| HGS2 entegrasyonu | `hgs2_launch` (`hgs2 run`: JAR + `perftest` profili, Windows iş nesnesi), `readiness`, `ingestion`, `response_parser` |
| Sentetik deneyler | `synthetic`, `synthetic_server`, `synthetic_experiment`, `campaign`, `campaign_runner`, `dataset` |
| Analiz | `analysis`, `features`, `detection`, `robust_z` (F5), `result_analysis` |
| Test sonucu analizi | `junit_report`, `junit_analysis`, `records`, `classify`, `expectations`, `scenario_mapping` |
| Kayıt ve şema | `storage`, `reader`, `metadata`, `models`, `sanitize`, `_validate` |
| Arayüz | `cli`, `webui` (yalnızca yerel) |

Testler (`tests/`) `isolation_guard.py` ile korunur: test süreci yalnızca kendi açtığı loopback soketlerine
bağlanabilir; loopback dışı veya başka bir sürecin (ör. çalışan gerçek HGS2) portuna bağlanma girişimi testi
başarısız kılar.

### Lab Artifacts (`projects/lab-artifacts/`)

PostgreSQL salt okunur katalog denetimi (V2), en az yetki rol tasarımı, izole küme yürütme kılavuzu (V1 + ek R1) ve
bunların kanıtları; Performance Lab pytest kanıt çalıştırmaları. Çalıştırılabilir bir bileşen değildir.

## Etkileşim

```
hgs2-lab hgs2 run ──► java -jar HGS.jar --spring.profiles.active=perftest
        │                     │
        │                     ├─ PerfTestSafetyGuard: loopback, 18080, hgs2_perftest_db, ortam değişkeni kimlikleri,
        │                     │  hibrit_giris_db'ye CONNECT reddi (42501) ─► aksi hâlde başlamaz
        │                     ▼
        └──► HTTP (127.0.0.1:18080) ─► ölçüm, sonuç dosyaları (results/, depoya girmez) ─► analyze / classify
```

* Performance Lab HGS2'yi derlemez ve kaynak koduna dokunmaz; `--app-dir` ile verilen dizini ve JAR içeriğini denetler.
* Lab Artifacts'taki denetim, `perftest` rolünün gerçek veritabanına erişemediğini PostgreSQL katalogu üzerinden
  doğrulayan SQL'i ve bunun izole kümelerde nasıl test edildiğini belgeler.

## Depo düzeni ve kurallar

* Her proje kendi `.gitignore` / `.gitattributes` dosyasını taşır; kök dosyalar yalnızca depo geneli kuralları içerir.
* Kökte bilinçli olarak `* text=auto` yoktur (içe aktarılan HGS2 geçmişini yeniden normalleştirmemek için).
* `projects/lab-artifacts/**` bayt bayt saklanır (`-text -whitespace`).
* `projects/performance-lab/tests/golden/**` bayt bayt saklanır (`-text`, proje `.gitattributes`).
