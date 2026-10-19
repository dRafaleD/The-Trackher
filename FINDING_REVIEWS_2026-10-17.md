# Bulgu inceleme ve araştırma notları

## Kullanım

1. Bir tarama çalıştırın veya kayıtlı araştırma dosyanızı açın.
2. **Araştırma → Bulgu inceleme** sekmesine geçin. Üst listeden incelemek istediğiniz taramayı seçin.
3. Bir bulguya çift tıklayın. **Not** alanına değerlendirmenizi, virgülle ayrılmış etiketleri, önceliği ve inceleme durumunu girin. **Kaynak kanıtı** sekmesinde orijinal sonucu görebilirsiniz.
4. **Uygula** notu açık araştırmaya ekler. **Kaydet**, notları ve taramaları `.trackher.json` dosyasına yazar.
5. Birden fazla satırı Ctrl/Shift ile seçip **Seçileni işaretle** menüsünden toplu inceleme durumu atayabilirsiniz. Her bulgunun mevcut notu, etiketi ve önceliği korunur.

## Filtreler ve takip

- Site, hedef/kullanıcı adı, not, etiket ve açıklamalarda arama yapılır. `İZLEME`, `izleme`, `ISIK` ve `ışık` gibi Türkçe harf varyasyonları aranabilir.
- İnceleme durumları: **Bekliyor**, **İncelendi**, **İlgisiz**, **Kararsız**. Öncelikler: **Yüksek**, **Normal**, **Düşük**.
- **Kanıt değişti**, seçilen taramanın kanıtı notun verildiği sürümden farklıysa görünür. Eski karar ve not kaybolmaz. Kaynak alanları, algılama sonucu veya kural değiştiğinde yeniden inceleme gerekir; yalnızca kontrol zamanının değişmesi yeterli değildir.
- Notlar aynı hedef, platform ve kullanıcı adı için taramalar arasında korunur. Farklı hedeflerin ve bağlantıyla keşfedilmiş farklı kullanıcı adlarının notları karışmaz.
- **İncelendi** işareti bir analist notudur; hesabın gerçek kişi sahipliğini kanıtlamaz. Makinenin `found / not_found / unknown` sonucu ve kaynak kanıtı değiştirilmez.

## Dosyalar ve dışa aktarma

- **Görünenleri CSV**, yalnızca ekranda filtrelenmiş bulguları; tarama sonucu, inceleme durumu, önceki karar, öncelik, not, etiket, kaynak ve inceleme zamanı ile dışa aktarır.
- Excel gibi programların hücreleri formül olarak çalıştırmasını önlemek için riskli CSV hücrelerinin başına apostrof eklenir. Bu işlem araştırmadaki orijinal notu değiştirmez.
- HTML araştırma raporu da notları, etiketleri ve kanıt değişikliği bilgisini içerir. Notlardaki HTML kodu metin olarak kaçışlanır.
- Eski sürüm-1 araştırma dosyaları açılabilir; yeni inceleme alanı isteğe bağlıdır. Bulgu başına en fazla 20000 karakter not, en fazla 30 etiket ve etiket başına 80 karakter desteklenir. Mevcut 20 MB toplam dosya sınırı korunur.
- Kaydedilmemiş değişikliklerle başka araştırma açarken, yeni araştırma oluştururken veya uygulamayı kapatırken **Kaydet / Kaydetmeden devam et / İptal** seçenekleri sunulur. Dosya seçiminden vazgeçilirse araştırma açık kalır. Tarama sırasında kaydederek çıkmak seçilirse önce tarama durdurulur ve sonuçların aktarılması beklenir.
- Otomatik kaydetme veya yükleme kurulmadı. Açık bir bulgu düzenleme penceresinde önce **Uygula** ya da **Vazgeç** seçin.

## Doğrulama

- Yeni işlevler için 16 otomatik test eklendi: dosya uyumluluğu, hedefler arası ayrım, durumların korunması, değişen kanıt, filtreler, Türkçe arama, HTML/CSV güvenli çıktısı ve kaydetmeden çıkış davranışları.
- Toplam 340 test geçti. Python kaynak arşivi ayrı klasöre çıkarılıp aynı 340 test yeniden çalıştırıldı; tamamı başarılıydı.
- Gerçek arayüz bileşenlerinde not düzenleme, toplu durum atama, filtreleme, dosyadan geri yükleme, CSV çıktısı, değişen kanıt ve kaydederek/iptal ederek çıkış sınandı.
- Mevcut 125% ölçekleme ve 960 piksel ekran yüksekliğinde yeni inceleme tablosunun yüksekliği 220 piksel, OSINT sonuç tablosunun yüksekliği 122 piksel ölçüldü.
- Windows paketindeki inceleme modülleri, güncel katalog, sürüm/yardım komutları ve arayüz açılışı doğrulandı. Paket üzerinde tüm etkileşimlerin tekrarlandığı iddia edilmiyor; ayrıntılı inceleme akışları kaynak arayüz bileşenlerinde test edildi.
- Değişiklikler yereldir; commit/push veya resmi sürüm yayını yapılmadı. Yeni yerel paket `dist/local-20261017-reviews` klasöründe hazırlandı; önceki paketler korunur. `Trackher/Trackher-GUI.cmd` dosyasıyla arayüz açılır. Uygulamanın mevcut sürüm numarası 1.2.0rc8 olarak korundu.
