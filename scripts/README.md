# scripts/

Depo düzeyi yardımcı betikler. Hiçbiri ağ, veritabanı veya HGS2 sürecine erişmez.

| Betik | Ne yapar |
|---|---|
| `verify_lab_artifacts.py` | `projects/lab-artifacts` altındaki tüm SHA-256 manifestlerini salt okunur doğrular. Çıkış kodu 0: uyuşmazlık yok. Depoda bulunmayan (bilinçli dışlanmış) dosyalar ayrı sayılır. |

```powershell
python scripts/verify_lab_artifacts.py
```
