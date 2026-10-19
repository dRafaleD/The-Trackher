# Trackher araştırma çalışma alanı

## Yeni özelliklerin kullanımı

1. Kaynak koddan çalışan Trackher arayüzünü yeniden açın. Bir kullanıcı adı, e-posta veya alan adı araması yapın.
2. Üstteki **Araştırma** düğmesine ya da aynı adlı sekmeye geçin. Tamamlanan veya durdurulan taramalar bu araştırmaya eklenir.
3. Araştırmanın adını, notlarını ve virgülle ayrılmış etiketlerini girin. **Kaydet** ile `.trackher.json` dosyası oluşturun. **Aç** ile bu dosyayı daha sonra yükleyebilirsiniz. **Rapor** düğmesi notları, kararları, değişiklikleri ve kaynak bulguları içeren HTML dosyası üretir.
4. **İlişki haritası** içindeki düğüme basarak kaynak bulguyu, çizgiye basarak benzerlikleri ve çelişkileri görün. Çizgi penceresinde **İlişkili / İlgisiz / Belirsiz** kararı ekleyebilirsiniz. Bu karar, hesapların bulunma durumunu değiştirmez.
5. Birden fazla tarama varsa üst listeden seçin. **Değişiklikler**, aynı hedefin önceki kaydıyla karşılaştırmayı gösterir. Biyografi değişiklikleri, eklenen/kaldırılan bağlantılar ve şu anda doğrulanamayan profiller ayrıdır. Eksik kapsam veya çıkarılamayan alan, silinmiş hesap olarak sunulmaz.

## Bekletme, durdurma ve devam etme

- **Beklet** yeni kontrollerin başlamasını bekletir. O sırada çalışan kontroller tamamlanabilir. **Devam et** bekleyen işleri serbest bırakır.
- **Durdur** çalışan ve bekleyen işleri iptal eder. Yarım kalanlar `unknown / cancelled` olarak korunur.
- **Tarama kontrolü** görünümü geçen süreyi, çalışan/bekleyen işleri ve engel nedenlerini listeler.
- Durdurulan kullanıcı adı/e-posta taramasını seçip **Kalanı sürdür** ile yalnızca yarım kalanları kontrol edin. Farklı kullanıcı adlarıyla keşfedilmiş hesaplar ayrı işler olarak korunur.
- **Başarısızları dene**, belirsiz, hatalı veya yapılandırılmamış kontrolleri tekrar çalıştırır. Önceden tamamlanmış sonuçların kaynak zamanı korunur; daralan kontrol kapsamı karşılaştırmada belirtilir.
- Uygulamayı kapatmadan önce durdurup araştırmayı kaydedin. Dosyayı tekrar açıp sürdürmek mümkündür. Kaydedilmemiş araştırma bellektedir; otomatik dosya kaydı veya izleme görevi kurulmaz. Yerel geçmiş seçeneği bu açık araştırma dosyasından ayrıdır. Durdurulan taramalar ve yalnızca bir alt kümeyi yeniden deneyen taramalar eski risk geçmişine yazılmaz; araştırma dosyasında korunur.
- Alan adı taramasını tekrar çalıştırmak için **Alan adı** düğmesini kullanın; dosyadan kısmi sürdürme kullanıcı adı ve e-posta kontrolleri içindir.

## Alan adı ve ihlal araştırması

**Alan adı** işlemi A/AAAA/MX/NS/RDAP bilgilerine ek olarak SPF, DMARC ve DNSSEC yanıtlarını inceler. SPF için kayıt varlığı, birden fazla politika ve herkese izin veren `all` işareti kontrol edilir; tüm SPF zinciri değerlendirilmez. DMARC politika değeri gösterilir. DNSSEC'te çözücünün AD doğrulama işareti kullanılır; bu işaretin yokluğu tek başına DNSSEC yokluğunu kanıtlamaz.

Sertifika kayıtlarından en fazla 200 alt alan adı adayı çıkarılır; bu adreslere istek gönderilmez. Kaynak yanıtı 20 saniyeyle sınırlandırılır. Tarihsel sertifika kaydı güncel DNS veya çalışan hizmet kanıtı değildir. Komut satırı:

```powershell
trackher --domain example.com --passive-subdomains --report html
```

HIBP bağlantısı, `HIBP_API_KEY` yapılandırılmışsa ihlal tarihi, eklenme tarihi, veri türleri ve doğrulanma bilgisini getirir. Önceki ihlal adları alanı korunur. API anahtarı yokken sonuç yapılandırılmamış kalır. Yeni hesap oluşturma, parola sıfırlama veya giriş akışı eklenmedi.

## Sınırlar ve doğrulama

- Araştırma dosyasında en fazla 100 tarama, tarama başına 2000 sonuç ve toplam 20 MB desteklenir. Kayıt atomik yapılır; yazma hatasında önceki dosya korunur.
- Harita ilk 200 profili değerlendirir; seçili düğümün en fazla 24 komşusunu gösterir. Diğer düğümler üstten seçilebilir. Ham sonuçlar dosyada korunur. HTML ilişki listesinde ilk 1000 bağlantı gösterilir; kaynak bulgular eksiksizdir.
- Eşleşme işaretleri ve çelişkiler aday ilişkilerdir; gerçek kişi sahipliğini kanıtlamaz. Analist kararı kaynak bulgunun yerine geçmez.
- Toplam 321 test geçti. Mevcut testlere kontrol iptali/bekletme, tam kullanıcı adıyla yeniden deneme, araştırma dosyası, atomik kayıt hatası, kapsam farkları, çelişkiler, HTML kaçışı, DNS politikaları, CNAME belirsizliği, CT kapsamı ve HIBP alanları için 20 test eklendi.
- Gerçek arayüz bileşenleriyle sonuç listesi, harita, ilişki penceresi ve dosyadan farklı kullanıcı adlı kontrolü sürdürme doğrulandı. 125% ölçeklemede 960 piksel ekran yüksekliğinde tablo 122 piksel, harita 250 piksel görünür alan aldı.
- Canlı `example.com` araştırması tamamlandı; SPF/DMARC/DNSSEC ve sertifika kaynağı başarılıydı, 5 alt alan adı adayı döndü. Komut satırı JSON raporu başarıyla üretildi. Canlı ücretli HIBP hesabı kullanılmadı; yanıt biçimi resmi dokümana göre sahte HTTP yanıtlarıyla test edildi.
- Kaynak kod güncellendi. Sonraki paketleme adımında güncel bağımsız Windows paketi `dist/local-20261016/Trackher` altında oluşturuldu. Sürüm numarası 1.2.0rc8 korunan yerel geliştirme paketidir; commit/push veya resmi sürüm yayını yapılmadı. Ayrıntılar: `PACKAGING_2026-10-16.md`.

Kaynaklar: [Google DNS JSON](https://developers.google.com/speed/public-dns/docs/doh/json), [HIBP API](https://haveibeenpwned.com/API/v3#AllBreachesForAnAccount), [crt.sh](https://crt.sh/).
