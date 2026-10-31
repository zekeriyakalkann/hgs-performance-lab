# N9 veri alım fikstürü

`fixture-batch.json` dosyası `tests/test_ingestion.py` tarafından kullanılan **sentetik** bir alım paketidir (`dataset_kind: fixture`). Gerçek bir hata örneği değildir.

Paketteki girdiler sözleşmenin bütün kurallarını sınar:

| Girdi | Sınanan kural |
|---|---|
| İncelenmiş etiket | Etiket kabul edilir |
| İncelenmemiş etiket | Etiket `proposed_label` olarak tutulur, doğrulanmış sayılmaz |
| Yalnızca zorunlu alanlar | Eksik isteğe bağlı alanlarla kabul edilir |
| Kaynak kimliği eksik | Reddedilir |
| Bilinmeyen sonuç (`UNKNOWN`) | Kabul edilir |
| Sentetik hassas değer | Değer maskelenir |
| Yinelenen kaynak kimliği | Tekrar olarak işaretlenir |
| Kayıt şeması 1 biçimindeki `expected_result` | Kabul edilir |
| Pakete aykırı veri türü (`real`) | Reddedilir; sentetik ve gerçek kayıtlar karışamaz |
| Beklentiyle eşleşebilecek Lab kaydı | Beklentiyle eşleştirilir |

"Hassas" görünen bütün değerler sahtedir.
