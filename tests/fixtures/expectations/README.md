# Beklenti sözleşmesi fikstürleri (N7)

Bu dosyalar `tests/test_expectations.py` ve `tests/test_expectations_pipeline.py` tarafından kullanılır.

| Dosya | İçerik |
|---|---|
| `synthetic-registry.json` | Lab'in **sentetik** kapsamındaki beklentiler. Sözleşmenin bütün durumlarını içerir: VERIFIED, DRAFT, REVIEWED, kaynaksız DRAFT, aynı senaryo için iki etkin beklenti (çelişki), DEPRECATED + yeni sürüm, yalnızca DEPRECATED, taşıma (zaman aşımı) beklentisi, çürüten ve bilinmeyen kaynaklı kanıt. "Hassas" görünen değerler (`KART-SENTETIK-111`) sahtedir. |
| `hgs2-draft-example.json` | Gerçek HGS2 için **yalnızca taslak** bir örnek. |

`hgs2-draft-example.json` hakkında:

- Tek kanıtı, HGS2 `AuthController` kaynak kodunun daha önce salt okunur olarak yapılan incelemesine bir referanstır (`source_code_review`, `UNREVIEWED`).
- Kaynak koddan çıkarılan bir gözlem onaylanmış iş kuralı değildir. Gerçek sistemde doğrulama yapılmadı. Bu yüzden durum `DRAFT` olarak kalır; bu kanıtla `VERIFIED` yapılamaz (registry reddeder).
- HGS2 davranışı hakkında doğrulanmış bir beklenti tablosu değildir.
