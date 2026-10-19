# Trackher: açık kaynak araştırma modülleri

## Tamamlanan kapsam

1. Web sitesi geçmişi: CDX arşiv dizini; aynı sayfanın örneklem içindeki iki
   görüntüsünde başlık, metin özeti ve bağlantı değişiklikleri.
2. Marka araştırması: sertifika dizininde marka etiketi veya tireyle ayrılan
   marka sözcüğü içeren alan adı adayları. Otomatik taklit/sahiplik kararı yok.
3. Kurumsal ayak izi: ana sayfada yayımlanan dış bağlantılar ve katalog profilleri.
4. Bahsedilme: tarihli haber dizini adayları, kaynakları ve tekrar grupları.
5. Ortak çalışma alanı: bulgu notları, kaynak kartları, ilişki haritası, taramalar
   arası karşılaştırma, kaynaklı zaman çizelgesi ve HTML/JSON raporları.

GUI: **OSINT** sekmesinde hedefi yazın, araştırma türünü seçin ve **Kaynakları
araştır** düğmesine basın. İlk üç modül alan adı, son modül kurum/marka ifadesi
kullanır. Satırı seçerek **Kanıt** ve **Kaynağı aç** seçeneklerini kullanın.
Araştırma dosyasını kaydetmek için **Araştırma → Kaydet** yolunu kullanın.

## Sınırlar

- Her modül 25 saniyelik bütçe kullanır; dış kontrol için 35 saniyelik son sınır
  ve durdurma/bekletme desteği vardır. Paralel arşiv görüntüleri en fazla ikidir.
- Dizinler en fazla 30 kayıt, kurum ana sayfası en fazla 30 dış bağlantı sağlar.
  Arşiv yanıtı/görüntüsü 1 MB, kurum/sertifika yanıtı 2 MB ile sınırlıdır.
- Kurum sayfasında DNS genel IP adresine doğrulanıp bağlantı o adrese sabitlenir;
  TLS doğrulaması özgün alan adına yapılır. Yalnızca aynı kök/www HTTPS çifti
  arasında en fazla iki yönlendirme izlenir. Bağlantıların hedefleri taranmaz.
- Marka modülü tüm yazım hatalarını ve homoglifleri kapsamaz. Haber kaynağı
  Google News RSS ile sınırlıdır; blog/forum kapsamı vaat edilmez.
- Arşiv örneklemi sitenin tüm geçmişi değildir. Erişilemeyen bir görüntüden
  bağlantı veya sayfa silindiği sonucu çıkarılmaz.
- Yeni zamanlanmış görev, sürekli takip, harici dosya yükleme veya yeni bağımlılık
  eklenmedi. Çalışmalar yerel; commit, push veya yayın yapılmadı.

## Sağlayıcılar

- [Internet Archive CDX belgesi](https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md)
- [Wayback Machine](https://web.archive.org/)
- [crt.sh](https://crt.sh/)
- [Google News](https://news.google.com/): RSS deneysel kaynaktır; kararlı bir
  resmî API sözleşmesi olarak değerlendirilmez.

## Canlı doğrulama

Bu ortamda `python.org` ve `www.python.org` ana sayfalarından 30 yayımlanmış dış
bağlantı çıkarıldı; son kaynak `https://www.python.org/` olarak korundu.
CDX ve crt.sh kontrollerinde zaman aşımı/sağlayıcı hataları, Google News RSS
kontrolünde bağlantı hatası görüldü. Bu kaynakların canlı başarılı sonuç üretimi
bu çalışmada doğrulanamadı; belirsiz durum korunur. Ayrıştırma ve karşılaştırma
başarıları kontrollü HTTP yanıtlarıyla sınanır.

GUI bileşenleri sentetik aday bulguyla başlatıldı; zaman çizelgesi ve ilişki
haritası oluşturuldu. Bu kontrol manuel görsel kullanılabilirlik testi değildir.

Otomatik doğrulama: 403 test geçti. Python derleme kontrolü ve yerel gizli bilgi
taraması geçti. Kaynak dağıtımı ve bağımsız Windows paketi ayrıca oluşturulur;
paket içindeki `build-info.json` tam kaynak SHA-256 listesini içerir.
