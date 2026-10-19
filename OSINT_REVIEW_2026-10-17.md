# OSINT modülleri ve belirsiz site kontrolleri — ikinci inceleme

## Düzeltilen sorunlar

- Başlığı değişen haberin kaynak kimliği değişiyor, taramalar arası fark ve
  analist notu bağlantısı kopabiliyordu. Kimlik artık sağlayıcı/kaynak adresine
  bağlıdır; eski yerel sürümden gelen notlar da önceki taramadan bulunur.
  Başlık değiştiğinde not korunur ve kanıtın değiştiği gösterilir.
- Arşiv karşılaştırması sürerken durdurulan tarama, önceden toplanan arşiv
  dizinini kaybedebiliyordu. Dizin sonuçları artık karşılaştırmadan önce ekrana
  aktarılır; durdurma ve süre aşımı durumunda korunur.
- Aynı arşiv kaydının dizin ve sayfa inceleme sonuçları birleştirilirken gerçek
  sayfa başlığı ve bağlantıları grafikte/zaman çizelgesinde gözden kaçabiliyordu.
  Ek kanıtlar mevcut düğümde birleştirilir, tarihli olay başlığı tamamlanır.
- Gizli HTML alanları yanlış içerik/bağlantı değişikliği üretebiliyordu.
  `hidden`, `aria-hidden`, satır içi display/visibility ve kapalı etiketler
  ayrıştırmada ele alınır. Bu bir tarayıcı/CSS görünürlük hesaplaması değildir.
- Haber sorgularındaki kontrol karakterleri normalleştirmeden önce reddedilir.
  Kurum ana sayfası zaman aşımı, genel bağlantı hatasından ayrılır.

## Canlı modül kontrolleri

- `python.org`: 30 yayımlanmış dış referans alındı.
- `Python Software Foundation`: haber RSS kaynağı bu turda iki aday kayıt verdi;
  özet ile birlikte üç sonuç satırı. Kaynakların kurumla ilgisi otomatik olarak
  kesinleştirilmez. Önceki turdaki bağlantı hatası kalıcı sonuç sayılmadı.
- `example.com` arşiv dizini ve `python.org` sertifika araması süre aşımına düştü.
  Bu iki sağlayıcının canlı veri üretimi bu turda da doğrulanamadı.

## Site kontrolleri

Alt ajan beş sitenin pozitif/negatif kontrol çiftlerini yeniden inceledi:
Instagram, Pinterest ve HackerNews geçti. CodeChef pozitif profil bulundu,
negatif kontrol ana sayfaya yönlendiği için belirsiz kaldı. YouTube iki istekte
de bağlantı hatası verdi. Algılama kuralı değiştirmek için yeni yeterli kanıt
bulunmadı; hata/yönlendirme hesap yokluğu sayılmadı.

Önceki raporlarla birlikte referanslı 54 sitenin kaydı 52 sağlıklı, YouTube
degraded ve CodeChef unknown şeklindedir. Bu turda yalnızca beş site canlı
kontrol edildi; kalan 249 katalog sitesi için doğrulanmış referans çifti yok.
Detaylar: [SITE_RECHECK_2026-10-17.md](SITE_RECHECK_2026-10-17.md).

## Doğrulama ve teslim

409 otomatik test; kaynak dağıtımında aynı testler, derleme/gizli bilgi
kontrolleri ve paket açılışı ile doğrulanır. Windows paketi yerel yeni klasörde
oluşturulur; önceki paket korunur. Gerçek kullanıcı senaryolarında manuel
görsel GUI testi yapılmış değildir. Commit/push/yayın yoktur.
