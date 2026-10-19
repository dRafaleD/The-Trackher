# Trackher yerel Windows paketi — 16 Ekim 2026

Yeni OSINT araştırma özellikleri bağımsız Windows uygulamasına ve Python kurulum paketlerine dahil edildi. Bu çalışma resmi yeni sürüm yayını değildir; mevcut `1.2.0rc8` sürüm numarası korundu. Eski `dist/Trackher` ve eski Python paketleri değiştirilmedi.

## Açılış

Proje klasöründeki `dist/local-20261016/Trackher/Trackher-GUI.cmd` dosyasına çift tıklayın.

Başka klasöre taşımak için `dist/local-20261016/Trackher-Windows-x64-local-20261016.zip` arşivini tamamen çıkarın. `.exe` ve `_internal` klasörü birlikte kalmalıdır. Arayüzde **Araştırma** sekmesi not, etiket, harita, karşılaştırma ve dosyadan sürdürme akışlarını içerir.

Komut satırı için paket klasöründe:

```powershell
.\Trackher.exe --help
.\Trackher.exe --domain example.com --passive-subdomains --report html
```

## Kontroller

- 321 test başarılı; kaynakta belirgin anahtar/şifre taraması 0 bulgu verdi.
- Python wheel ve kaynak arşivi oluşturuldu. Yeni modüller, görseller ve 303 sitelik güncel katalog her iki arşivde doğrulandı. Wheel ayrı bir geçici klasöre kuruldu; proje klasöründen bağımsız modül yüklemesi başarılıydı.
- Windows x64 `.exe` içinde yeni GUI/keşif/araştırma modülleri ve güncel katalog doğrulandı. CustomTkinter tema dosyaları da paketlendi.
- Paketlenmiş `.exe` için `--version`, `--help` ve canlı `example.com` alan adı araştırması başarılıydı; yeni güvenlik kontrollerini içeren JSON raporu üretildi.
- Paketlenmiş arayüzün açılışında süreç 5 saniye açık kaldı ve hata çıktısı vermedi. Ayrıntılı harita ve dosyadan devam etme akışları kaynak arayüzde önceki adımda test edildi; paket üzerinde tüm etkileşimlerin tekrarlandığı iddia edilmiyor.
- Windows ZIP arşivinin bütün dosyaları CRC kontrolünden geçti; içindeki katalog kaynak dosyayla aynıydı. Arşiv ve Python paketleri için SHA-256 değerleri `dist/local-20261016/SHA256SUMS.txt` içindedir.
- Paket içindeki `build-info.json`, kaynak dosya özetlerini, araç sürümlerini ve doğrulama kapsamını içerir.
- GitHub test/paketleme ayarlarında eski `gui.py` derleme hedefi mevcut `gui` klasörüne düzeltildi. Bu değişiklik yerelde doğrulandı; uzak CI çalıştırılmadı.

Python paketleri: `dist/local-20261016/python/`. Python 3.14.5 ve PyInstaller 6.22.1 kullanılan yerel derlemenin kesin bilgileri `build-info.json` içindedir. Commit, push, etiket, GitHub yayını veya otomatik izleme görevi oluşturulmadı.
