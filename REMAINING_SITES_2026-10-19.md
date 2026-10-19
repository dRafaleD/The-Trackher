# Kalan siteler: 19 Ekim 2026

30 farklı site, aday kullanıcı adı ve rastgele negatif kontrol ile incelendi (60 istek kontrolü). Değişen beş site tekrar sınandı (10 kontrol). Bunlar bütün kataloğun sağlıklı olduğunu göstermez; aday adlarının tamamının gerçekten var olduğu varsayılmadı.

## Düzeltilen algılamalar

| Site | Önce | Sonra ve kanıt |
| --- | --- | --- |
| Genius Artists | `taylor-swift` doğrulanamadı | Bulundu; canonical, Open Graph adresi, site adı, sanatçı başlığı ve profil h1 alanı birlikte doğrulandı. Negatif kontrol 404. |
| Odysee | Video olmayan URL metni tek başına bulundu sayılıyordu | Anonim, salt okunur `resolve` ile kanal türü, istenen ad, normalize ad, claim kimliği ve kalıcı adres eşleşiyor. `Odysee` bulundu; negatif kontrolün sorguya bağlı NOT_FOUND yanıtı yokluğu doğruluyor. |
| Genius Users | `genius` sanatçı sayfasına yönlenip kullanıcı bulundu sayılıyordu | Profil türü değiştiğinden doğrulanamadı. Doğrudan negatif profil 404. |
| Society6 | `society6` ürün koleksiyonu sayfasında kullanıcı bulundu sayılıyordu | Koleksiyon yönlendirmesi doğrulanamadı. Doğrudan negatif profil 404. |
| ReverbNation | `reverbnation` giriş sayfasına yönlenip bulunamadı sayılıyordu | Giriş sayfası profil yokluğu kanıtı sayılmıyor; doğrulanamadı. Negatif profil 404. |

Odysee uç noktası sabittir: `https://api.na-backend.odysee.com/api/v1/proxy?m=resolve`. Yalnız `resolve` metodu kullanılır; giriş, cüzdan veya yazma işlemi yoktur. Bir megabaytı aşan, hatalı, farklı kimliğe ait, çelişkili veya başarısız yanıtlar doğrulanamadı kalır. Kaynak: [Odysee resmi frontend API sözleşmesi](https://github.com/OdyseeTeam/odysee-frontend/blob/master/llms.txt).

Yönlendirme değişikliği yalnız bu üç HTML sitesi için etkinleştirildi; diğer sitelerin yönlendirme davranışı korunur.

## İncelenen diğer siteler

| Sonuç | Siteler |
| --- | --- |
| Aday bulundu, negatif kontrol bulunamadı; mevcut kurallar çalıştı | Kongregate, Wattpad, Open Collective, RubyGems, Speedrun.com, Mixcloud, Dailymotion |
| İki kontrol de erişim engeli; doğrulanamadı | MyDramaList, Anime-Planet, BoardGameGeek, ModDB, VSCO, Etsy, Fandom, Rumble, Threadless, Redbubble, Flightradar24, Pinkbike, BookCrossing |
| İki kontrol de bağlantı hatası; doğrulanamadı | TMDB |
| İki yanıtta da yeterli profil kimliği yok; doğrulanamadı | 500px, Instapaper, Aparat |
| İki kontrol de bulunamadı; pozitif adayın varlığı doğrulanmadı | WordPress (`en`) |

Engeller aşılmaya çalışılmadı ve tahmini eşleşmeler bulundu yapılmadı.

## Doğrulama ve kayıtlar

- `reports/remaining-sites-20261019/initial.jsonl`: ilk 20 site, 40 sonuç.
- `reports/remaining-sites-20261019/additional.jsonl`: sonraki 10 site, 20 sonuç.
- `reports/remaining-sites-20261019/recheck.jsonl`: değişen beş site, 10 sonuç.
- JSONL kayıtları sınıflandırma, HTTP durumu ve yerel geçici ham yanıt dosyası yolunu içerir. Ham sayfalar paketlenmez.
- Regresyon testleri: eksik/yanlış kimlik alanları, script içine gizlenmiş HTML, farklı claim türü/kimliği, yanlış sorgunun yanıtı, çelişkili yokluk kanıtı, API hataları, eski oEmbed metni ve farklı profil türüne yönlendirme.

Değişiklikler yereldir; commit, push veya yayın yapılmadı.
