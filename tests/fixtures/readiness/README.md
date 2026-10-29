# N9 hazırlık fikstürleri

Bu dosyalar `tests/test_readiness.py` testleri için kullanılır. Hepsi sentetiktir.

| Dosya | Amaç |
|---|---|
| `ready.xml` | Bütün testlerinde açık senaryo kimliği (`hgs2_lab.scenario_id`) bulunan rapor |
| `ready-registry.json` | Bu kimliklerin hepsi için sentetik kapsamda VERIFIED beklenti |

`ready.xml` + `ready-registry.json` + `--scope synthetic` birleşimi READY verir; bu, denetimin "her şey tamam" yolunu sınamak içindir. Aynı dosyalarla `--scope real` BLOCKED verir, çünkü gerçek kapsamda doğrulanmış beklenti yoktur. Her iki sonuç da gerçek HGS2 hakkında bir şey söylemez.
