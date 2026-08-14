# Trackher

Trackher; kişisel dijital ayak izinizi incelemek ve yerel cihazınızdaki bazı
geçmiş, önbellek ve geçici dosyaları temizlemek için geliştirilmiş açık kaynaklı
bir Python aracıdır. Hem grafik arayüzle hem de terminalden kullanılabilir.

> Yalnızca size ait veya inceleme izni aldığınız hesaplarda ve cihazlarda
> kullanın. Ayrıntılar için [ETHICS.md](ETHICS.md) belgesini okuyun.

## Özellikler

- 197 platformda kanıta dayalı kullanıcı adı taraması
- 110 servislik e-posta kataloğu ve en fazla 2 yan etkisiz otomatik sorgu
- Eğitim, abonelik, anime, film, dizi ve forumları da içeren 251 alan adında
  e-posta arama bağlantıları
- Windows, macOS ve Linux için kabuk, tarayıcı ve kullanıcı önbelleği temizliği
- HTML ve JSON raporları
- Kuru çalıştırma, dışlama listesi, en iyi çaba esaslı dosya üzerine yazma
- Windows Görev Zamanlayıcı, macOS `launchd` ve Linux `cron` desteği

## Önemli Doğruluk Notu

E-posta kataloğundaki 108 eski kontrol parola sıfırlama, OTP veya oturum açma
bildirimi üretme riski taşıdığı için ağ isteği göndermeden atlanır. Bu servisler
`ATLANDI` olarak gösterilir. Araç bir hesabı yalnızca açık ve servis-özel
kanıt olduğunda `KAYITLI` sayar.

Sonuçların anlamı:

- `KAYITLI`: Kontrol edilen yanıtta hesap için güçlü kanıt bulundu.
- `BULUNAMADI`: Kontrol anında hesap kanıtı bulunmadı; kesin yokluk garantisi değildir.
- `DOĞRULANAMADI`: Site engeli, ağ sorunu, değişen uç nokta veya güvenlik nedeniyle
  karar verilemedi.
- `ATLANDI`: İstek yan etki üretebileceği için hedef platforma hiç gönderilmedi.

Gravatar kontrolü ek yapılandırma gerektirmez. [Have I Been Pwned](https://haveibeenpwned.com/)
sorgusu resmî API v3 üzerinden çalışır ve `HIBP_API_KEY` ortam değişkeni ister:

```powershell
$env:HIBP_API_KEY="kendi-api-anahtariniz"
```

```bash
export HIBP_API_KEY="kendi-api-anahtariniz"
```

Anahtar tanımlı değilse HIBP isteği gönderilmez. API anahtarını repoya, rapora
veya ekran görüntüsüne eklemeyin.

## Gereksinimler

- Python 3.10 veya üzeri
- İnternet bağlantısı: OSINT taramaları için
- Tk desteği: grafik arayüz için

Debian/Ubuntu üzerinde Tk eksikse `sudo apt install python3-tk` gerekebilir.
Terminal kullanımı Tk olmadan devam eder.

## Kurulum

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

`python main.py` grafik arayüzü açar. Argüman verildiğinde araç terminal modunda
çalışır.

## Terminal Kullanımı

```bash
# E-posta ve kullanıcı adı taraması
python main.py --email kullanici@example.com
python main.py --username kullanici_adi

# Genişletilmiş arama bağlantıları ve HTML raporu
python main.py --email kullanici@example.com --search-dork --report html

# Önce yalnızca nelerin temizleneceğini görün
python main.py --clean-all --dry-run

# Sonucu inceledikten sonra kalıcı temizliği açıkça onaylayın
python main.py --clean-all --yes

# Dışlama listesiyle simülasyon
python main.py --clean-all --dry-run --exclude exclusions.example.json

# En iyi çaba esaslı üzerine yazma
python main.py --shred /path/to/file --dry-run
python main.py --shred /path/to/file --yes

# Zamanlayıcı önizlemesi ve kurulumu
python main.py --schedule weekly --dry-run
python main.py --schedule weekly --yes
```

Etkileşimli terminalde `--yes` verilmezse kalıcı işlemler ayrıca sorulur.
Etkileşimsiz çalışmada kalıcı işlem için `--yes` zorunludur. Kullanıcı ana
dizini, sürücü kökü ve temel sistem dizinleri toplu silmeye karşı korunur.
Zamanlanmış görev, kurulum anındaki Python yorumlayıcısının ve proje yolunun
yerinde kalmasını bekler.

## Platform Desteği

| Özellik | Windows | macOS | Linux |
|---|:---:|:---:|:---:|
| GUI ve OSINT | Evet | Evet | Evet |
| Kabuk/tarayıcı/sistem temizliği | Evet | Evet | Evet |
| Zamanlanmış görev | Evet | Evet | Evet |
| Sağ tık menüsü | Evet | Hayır | Sınırlı/deneysel |
| Dosya üzerine yazma | En iyi çaba | En iyi çaba | En iyi çaba |

macOS ve Linux yolları birim testleriyle taklit edilir; GitHub Actions her üç
işletim sisteminde test çalıştırır. Grafik arayüz için masaüstü oturumu gerekir.

## Güvenlik ve Sınırlamalar

- Tarayıcı temizliği çerezleri silebilir ve açık oturumları kapatabilir. Tarayıcıyı
  önce kapatın ve her zaman `--dry-run` ile başlayın.
- SSD, ağ diski, sıkıştırılmış, günlüklemeli veya kopyala-yaz dosya sistemlerinde
  fiziksel verinin üzerine yazıldığı garanti edilemez. Tam disk şifreleme daha
  güçlü bir savunmadır.
- OSINT servisleri ve arama motorları değişebilir, hız sınırı uygulayabilir veya
  otomatik istekleri engelleyebilir. Sonuçları elle doğrulayın.
- Uygulama merkezi bir sunucuya veri göndermez; OSINT hedefleri yalnızca listelenen
  platformlara ve seçtiğiniz arama motoruna yapılan sorgularda kullanılır.

Güvenlik açığı bildirmek için [SECURITY.md](SECURITY.md) belgesine bakın.

## Test

```bash
python -m pip check
python -m compileall -q footprint osint utils gui.py main.py setup_context_menu.py
python -m unittest discover -s tests -v
```

Katkı süreci [CONTRIBUTING.md](CONTRIBUTING.md) içinde açıklanmıştır. Proje MIT
lisansı ile sunulur. Sürüm notları [CHANGELOG.md](CHANGELOG.md) dosyasındadır.
