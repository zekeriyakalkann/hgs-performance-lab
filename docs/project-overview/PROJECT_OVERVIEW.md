# Proje özeti

## Amaç

HGS2 (Hibrit Giriş Sistemi) API'si için akademik bir performans testi ve analiz çalışması: gerçek sisteme ve gerçek
veritabanına zarar vermeden, izole bir ortamda tekrarlanabilir ölçüm yapmak; sonuçları istatistiksel olarak analiz
etmek ve gecikme anomalilerini tespit etmek.

## Kapsam ve durum

| Alan | Durum |
|---|---|
| Performance Lab çalıştırma akışı, sonuç şeması (v2), `analyze` | Uygulandı, birim + yerel entegrasyon testleri |
| Sentetik deneyler, kampanyalar, veri seti | Uygulandı (yalnızca yerel sentetik sunucu) |
| Sistem telemetrisi (F4), Robust Z-score dedektörü (F5) | Uygulandı; yalnızca sentetik veriyle değerlendirildi |
| JUnit/Surefire sınıflandırma, senaryo eşleştirme | Uygulandı; gerçek HGS2 hata örnekleriyle doğrulanmadı |
| `hgs2 run` (HGS2'yi `perftest` profiliyle başlatma) | Uygulandı; gerçek HGS2/Java/PostgreSQL ile henüz çalıştırılmadı |
| HGS2 `perftest` profili ve `PerfTestSafetyGuard` | Uygulandı |
| PostgreSQL salt okunur denetimi ve rol tasarımı | İzole kümede V1 yürütmesi tamamlandı; gerçek kümeye geçiş onayı değildir |

Ayrıntılı durum ve bilinen sınırlamalar:

* [`projects/performance-lab/README.md`](../../projects/performance-lab/README.md), "Henüz uygulanmamış özellikler ve
  bilinen sınırlamalar"
* [`projects/lab-artifacts/db-audit/20261030-postgresql-readonly-audit-v2/asama4-v1-execution/KNOWN_LIMITATIONS.md`](../../projects/lab-artifacts/db-audit/20261030-postgresql-readonly-audit-v2/asama4-v1-execution/KNOWN_LIMITATIONS.md)

## Zaman çizelgesi

| Tarih | Olay |
|---|---|
| 2026-05-14 | HGS2 uygulaması (özgün depo, `main`) |
| 2026-10-23 | Performance Lab ilk sürüm; sonuç şeması v2; uçtan uca yürütme hattı |
| 2026-10-24 | F1–F3 deney altyapısı; telemetri (F4) ve Robust Z-score (F5) |
| 2026-10-29 | N6–N12 iyileştirmeleri, yerel web arayüzü, pytest kanıtları |
| 2026-10-30 | `hgs2 run`; PostgreSQL salt okunur denetimi V2 ve izole küme V1 yürütmesi |
| 2026-10-31 | Üç bileşen bu depoda birleştirildi |

## Katkıda bulunanlar

* HGS2 uygulaması: ServetAlav001 ve ekibi
* Performance Lab, `perftest` profili, denetim çalışması: Zekeriya Kalkan
