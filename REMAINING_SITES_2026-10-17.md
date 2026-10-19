# Kalan siteler: yeni 30-site grubu — 17 Ekim 2026

Önceki beş siteden ayrı, 30 katalog sitesi incelendi. İlk kontrol 20 site,
referans düzeltmesi yedi site (altısı tekrar, Itch.io yeni), ek kontrol dokuz
site ve değişiklik sonrası yedi site içerir. Toplam 86 profil isteği yapıldı;
eşzamanlılık iki, site aralığı en az 1,2 saniye, HTTP bütçesi 10 saniye ve dış
kontrol bütçesi 25 saniyedir. İlk denemedeki marka adları yalnızca aday referanstı;
varlıkları bilinmeyen bir adayın 404 vermesi, site kontrolünün başarılı olduğu
anlamına gelmez. Daha uygun pozitif örnekler ayrıca sınandı.

## Sonuçlar ve değişiklikler

| Site | Önce | Son kontrol + / − | Yapılan işlem |
|---|---|---|---|
| Kaggle | headsortails profili unknown | found / not_found | og:username, profil türü ve tam profil adresi birlikte doğrulanır. Görünen adın kullanıcı adıyla aynı olması gerekmez. |
| BuyMeACoffee | supporthub profili unknown | found / not_found | Kök alan adına taşınmış adres, canonical, og:url, site adı ve sayfa türü doğrulanır. |
| Patreon | Genel metin eşlemesi | found / not_found | Eski, /c/ ve /cw/ yolları desteklenir; etkin yol, canonical, OG adresi ve profile:username birbiriyle uyuşmalıdır. |
| IFTTT | Genel metin eşlemesi | found / not_found | /p/ profil adresi, canonical, OG adresi, IFTTT site adı ve kullanıcıya bağlı başlık doğrulanır. |
| Substack | Genel metin eşlemesi | found / not_found | İstenen yayın alt alanı, canonical, OG adresi, türü ve Substack başlığı birlikte doğrulanır. |
| Giphy | Genel metin ve yönlendirme eşlemesi | found / unknown | Gerçek kanalın canonical/OG adresi ile kanal başlığı gerekir. /explore/ arama yönlendirmesi artık hesap yokluğu sayılmaz. |
| Trakt | Genel marka metniyle found | unknown / unknown | Yeni app.trakt.tv sayfası her kullanıcı için genel uygulama kabuğu döndürüyor. Bu kabuk artık hesap kanıtı sayılmıyor; hesap varlığı için yeterli veri yok. |

**İki gerçek unknown pozitif sonucu düzeltildi.** Beş site değişiklik sonrası
kontrol çiftini geçti; Giphy yalnızca pozitif kanalı doğruladı. Trakt için yanlış
pozitif engellendi, otomatik doğrulanmış hesap sonucu vaat edilmedi.

Ortak HTML ayrıştırıcı, template/noscript/script içeriklerini ve altbilgi,
yorum/akış ve makale içindeki yardımcı kimlik verilerini profil kanıtı olarak
kullanmıyor. Yorum veya öneri içindeki başka bir profil etiketi yeterli değildir.
Mevcut güvenilirlik etiketleri otomatik yükseltilmedi; TLS ve erişim korumaları
gevşetilmedi. Yeni API anahtarı ya da giriş gerektiren uç nokta kullanılmadı.

## Diğer incelenen siteler

NPM, Codepen, Ko-fi, Coroflot, 9GAG, Letterboxd, ProductHunt ve Smule kontrollerinde
tarayıcı koruması görüldü. Carbonmade ve Newgrounds erişim reddetti; AllTrails
koruma yanıtı verdi. Flickr zaman aşımı/502, Tumblr bağlantı-protokol hatası verdi.
Replit ve Codecademy pozitif adayları giriş sayfasına yönlendi. Imgur iki kullanıcı
için aynı genel uygulama kabuğunu döndürdü; kimlik kanıtı çıkarılmadı.

HackMD ve Itch.io örnekleri mevcut kuralla found/not_found verdi; algılamaları bu
turda değiştirilmedi. LiveJournal pozitif sayfası bulundu, negatif alt alanında
bağlantı hatası oluştu. Vimeo, Bandcamp, Carrd ve freeCodeCamp adaylarından geçerli
bir pozitif kontrol üretilemedi; bu siteler düzeltilmiş/sağlıklı ilan edilmedi.

## Kanıt ve doğrulama

- `reports/remaining-sites-20261017/initial.jsonl`, `refined.jsonl`,
  `additional.jsonl`, `after.jsonl`: durumlar, URL, HTTP kodu, boyut ve zaman.
- Tam HTML yanıtları yalnızca geçici klasörlerdedir. Regresyon örnekleri
  `tests/fixtures/remaining_sites_20261017.json` içinde gerekli meta/başlık
  alanlarına azaltılmıştır; sayfa oturum verileri ve çalışma zamanı tokenları
  örneklere taşınmamıştır.
- Dokuz yeni test; yanlış kimlik, eksik alan, sahte metin, template/script,
  erişim engeli, yönlendirme, Patreon rota uyuşması, yayın alt alanı ve Trakt
  kabuğunu kapsar. Toplam **418 test geçti**.
- Yerel Windows paketi ve Python dağıtımı yeniden oluşturulur. Önceki paketler
  korunur; commit, push veya resmî yayın yapılmadı.

Kaynaklar: [BuyMeACoffee açık sayfa](https://buymeacoffee.com/supporthub),
[GIPHY kanal şeması](https://developers.giphy.com/docs/api/schema/).
Bu kaynaklar hesap sahipliği veya kişinin gerçek kimliğini doğrulamaz.
