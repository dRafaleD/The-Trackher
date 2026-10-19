# Trackher terminal açılışı ve ana menü

AsphDex `cli/terminal-screen.js` ve Banshee `src/splash.rs` /
`src/splash_boot.rs` tasarımları salt okunur incelendi. Bu projelerin dosyaları
değiştirilmedi. Trackher için radar amblemi, yeşil marka vurgusu, sakin gri
metin ve kategori renkleriyle ayrı bir tasarım oluşturuldu.

## Kullanım

- `trackher` veya `trackher --menu`: kısa kozmetik açılış ve etkileşimli menü.
- 1–7: kullanıcı adı, e-posta, alan adı, web geçmişi, marka, kurum ve haber.
- 8: çevrimdışı platform şeması kontrolü. Canlı kontroller mevcut CLI ile açılır.
- 9: mevcut GUI. `?`: yardım. `0` / `q`: çıkış.
- `trackher --no-animation`: animasyonsuz menü.
- `trackher --no-color`: renksiz ve animasyonsuz menü.
- `TRACKHER_NO_ANIMATION` / `NO_COLOR`: ortam değişkeniyle aynı tercihler.

Neofetch düzeni yerleşiktir: solda Trackher radar amblemi; sağda araç, sistem,
Python sürümü, gerçek katalog sayıları ve araştırma modu. Harici neofetch veya
fastfetch kurulumu gerekmez; bu ortamda bu komutlar kurulu bulunmadı.

Menü girdileri kabuk komutuna dönüştürülmez; sabit argüman listeleriyle mevcut
CLI işlevlerine iletilir. Eski komutlar ve silme/onay kuralları korunur. Menü
silme işlemi başlatmaz; temizlik komutlarına `--help` üzerinden erişilir.

Animasyon yalnızca gerçek giriş/çıkış terminalinde, renk desteği ve yeterli
alan varsa çalışır. 1,25 saniyelik tarama/decode dalgası yalnızca görseldir;
tarama veya motor testi yapıldığı anlamına gelmez. Dar pencerede düzen sadeleşir.
Yönlendirilmiş çıktı beklemez/animasyon oynatmaz. Rich bağlamı kesintide imleci
geri getirir; ham terminal modu açılmaz.

## Doğrulama

426 test; menü argümanları, hatalı seçim, EOF, işlem hatası, küçük pencere,
animasyon tercihleri, renk tercihi, non-TTY davranışı ve kesintide imleç dönüşü
kapsanır. Kaynakta gerçek Windows PTY üzerinde animasyon, yardım, menüye dönüş
ve çıkış denendi. Önizleme gerçek render satırlarından üretildi; işletim sistemi
ekran görüntüsü değildir: `reports/terminal-20261017/trackher-terminal-home.png`.

Yerel yeni Windows paketi önceki paketlerden ayrı oluşturulur. Terminal için
`Trackher-Terminal.cmd`, GUI için `Trackher-GUI.cmd` kullanılır. Commit/push veya
yayın yapılmadı.
