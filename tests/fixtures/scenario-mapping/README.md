# N10 senaryo eşleme fikstürleri

Bu dosyalar `tests/test_scenario_mapping.py` ve `tests/test_scenario_mapping_pipeline.py` testleri için kullanılır. Hepsi elle yazılmış **sentetik** dosyalardır; gerçek HGS2 raporlarından, testlerinden veya iş kurallarından alınmadılar.

## `n10-report.xml` + `n10-mapping.json` + `n10-registry.json`

Rapor tek bir suite içerir (`com.example.lab.EslemeTests`, 17 test). Eşleme dosyası testleri `<classname>#<name>` anahtarıyla senaryolara bağlar. Registry'deki bütün beklentiler `synthetic` kapsamdadır.

| Test | Senaryo çözümlemesi | Beklenti durumu |
|---|---|---|
| `metaVeEslemeAyni` | Metadata ve eşleme aynı kimliği gösteriyor (`metadata_and_mapping`) | VERIFIED, PASS bekleniyor |
| `yalnizEsleme` | Yalnızca eşleme dosyasında (`mapping`) | VERIFIED, PASS bekleniyor |
| `eslemeBeklentiFail` | `mapping`; kaynak FAIL | VERIFIED, PASS bekleniyor (tutarsız) |
| `yalnizMetadata` | Yalnızca testcase özelliğinde (`metadata`) | VERIFIED |
| `metaEslemeCelisiyor` | Metadata ile eşleme farklı (`metadata_mapping_conflict`) | İki adayın da VERIFIED beklentisi var; hiçbiri seçilmemeli |
| `ikiliEsleme` | İki ACTIVE eşleme farklı senaryolara (`mapping_conflict`) | İki adayın da VERIFIED beklentisi var |
| `eslemesiYok` | Eşleme kaydı yok (`not_mapped`) | — |
| `emekliEsleme` | Yalnızca DEPRECATED eşleme (`deprecated_only`) | Hedef senaryonun VERIFIED beklentisi var; kullanılmamalı |
| `sinifsiz` | Raporda `classname` yok (`identifier_missing`); eşleme kaydı var ama suite adından türetilmemeli | — |
| `gecersizMetadata` | Geçersiz testcase özelliği (`metadata_invalid`); eşleme kaydı var ama kullanılmamalı | — |
| `atlanan` | `mapping`; kaynak SKIPPED | VERIFIED, PASS bekleniyor (başarı sayılmamalı) |
| `taslakBeklenti` | `mapping` | DRAFT |
| `incelenmisBeklenti` | `mapping` | REVIEWED |
| `cakisanBeklenti` | `mapping` | İki etkin beklenti (N7 `conflict`) |
| `httpBeklentisi` | `mapping` | VERIFIED; yalnızca HTTP durumu ve iş sonucu (JUnit'te gözlenemez) |
| `kayitsizSenaryo` | `mapping` | Registry'de yok (`not_found`) |
| `hassasMesaj` | `mapping`; kaynak FAIL | Mesaj ve izde sahte kart/öğrenci numarası, parola ve token |

Suite ve testcase düzeyinde sahte parola özellikleri de vardır; okunmamaları gerekir. `map-baska-rapor` eşlemesi bu raporda bulunmayan bir teste aittir.

## `ready-unlabeled.xml` + `ready-mapping.json`

`ready-unlabeled.xml`, N9'daki `readiness/ready.xml` ile aynı testleri içerir ama `hgs2_lab.scenario_id` özelliği taşımaz. `ready-mapping.json` bu testleri `readiness/ready-registry.json` içindeki senaryolara bağlar.

- Eşleme dosyası olmadan `readiness check --scope synthetic` sonucu BLOCKED'dır (kimlik yok).
- Eşleme dosyasıyla sonuç READY olur.
- `--scope real` her durumda BLOCKED kalır: gerçek kapsamda doğrulanmış beklenti yoktur.

Bu sonuçlar gerçek HGS2 hakkında bir şey söylemez.

Bütün "hassas" değerler (`KART-SENTETIK-111`, `OGR-SENTETIK-222`, `FAKE-…`) sahtedir.
