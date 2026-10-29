# N8 toplu JUnit analizi fikstürleri

Bu dosyalar `tests/test_junit_analysis.py` tarafından kullanılır. Hepsi elle yazılmış **sentetik** dosyalardır; gerçek HGS2 raporlarından alınmadılar.

Açık senaryo kimliği, testcase düzeyindeki `<properties>` içinde `hgs2_lab.scenario_id` adlı özellikle verilir. Değer `value` özniteliğinde ya da öğe metninde olabilir.

## `batch-a.xml`

İki suite içerir. İkincisi boştur. Testler:

| Test | Kapsadığı durum |
|---|---|
| `kartPasifCihaz` | PASS + VERIFIED beklenti |
| `kartGecerli` | FAIL + VERIFIED beklenti (beklenen PASS) |
| `kartZamanAsimi` | ERROR + DRAFT beklenti; kimlik öğe metninde |
| `kartAtlandi` | SKIPPED; beklentisi yok |
| `numaraOkut` | Senaryo kimliği yok |
| `numaraTaslak` | DRAFT beklenti |
| `eskiSurum` | Yalnızca DEPRECATED beklenti |
| `cakisanBeklenti` | Aynı senaryo için iki etkin beklenti |
| `hassasMesaj` | Mesajda ve izde sentetik hassas değer, testcase'te hassas adlı başka bir özellik; beklentisi yok |
| `gecersizKimlik` | Geçersiz kimlik değeri |
| `celisenKimlik` | Aynı testte iki farklı kimlik |
| `httpBeklentisi` | HTTP durumu ve iş sonucu beklentisi; bu alanlar JUnit'te gözlenemez |

Suite düzeyinde de sahte bir parola özelliği vardır; okunmaması gerekir.

## `batch-b.xml`

Tek suite içerir. `com.example.lab.KartTests#kartPasifCihaz`, `batch-a.xml` içinde de bulunur ve olası tekrar testi için kullanılır.

## Beklentiler

Beklentiler `tests/fixtures/expectations/junit-registry.json` dosyasındadır (kapsam `synthetic`).

Bütün "hassas" değerler (`KART-SENTETIK-111`, `FAKE-…`) sahtedir.
