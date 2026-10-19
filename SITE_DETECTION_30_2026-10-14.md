# 30 site için özel profil algılama — 14 Ekim 2026

Katalogdaki genel veya yetersiz HTML algılamasını kullanan adaylar, herkese açık
bir referans profil ve rastgele negatif kontrol ile karşılaştırıldı. Kayıtlı bir
son kullanıcı taraması bulunmadığından seçim katalog ve canlı yanıtlar üzerinden
yapıldı. Bu çalışma 30 eski `unknown` sonucunun tamamının çözüldüğü iddiası değildir.

Toplam 72 farklı aday site incelendi; gerçek profil kanıtı alınabilen **30 siteye** özel kurallar eklendi. Seçilen grupta **7 referans profil** eski algılayıcıda `unknown` dönüyordu; diğer kurallar genel algılamayı daha kesin kanıtlarla değiştirdi.

Belirsizliği çözülen referanslar: MyAnimeList, Hearthis.at, Disqus, HackerEarth, Hackster.io, HubPages, Instructables.

## Canlı tekrar kontrolü

- 30 referans profil: `found`.
- 29 rastgele negatif kontrol: `not_found`.
- CodeChef negatif kontrolü: `unknown` / `redirect_changed`.
- Yakalanan tam yanıtların yerel tekrar değerlendirmesi aynı sonuçları verdi.

Bu sonuçlar bu ortamda, belirtilen tarihte ve bu kontrol çiftlerinde gözlendi.
Site yapıları ve erişim koşulları değişebilir; tüm kullanıcı adları için garanti değildir.

| Site | Herkese açık referans | Önce referans / negatif | Sonra canlı referans / negatif |
| --- | --- | --- | --- |
| SoundCloud | [soundcloud](https://soundcloud.com/soundcloud) | found / not_found | found / not_found |
| Dribbble | [simplebits](https://dribbble.com/simplebits) | found / not_found | found / not_found |
| Behance | [beeple](https://www.behance.net/beeple) | found / not_found | found / not_found |
| DeviantArt | [spyed](https://www.deviantart.com/spyed) | found / not_found | found / not_found |
| MyAnimeList | [Xinil](https://myanimelist.net/profile/Xinil) | unknown / unknown | found / not_found |
| About.me | [tony](https://about.me/tony) | found / not_found | found / not_found |
| CodeChef | [gennady.korotkevich](https://www.codechef.com/users/gennady.korotkevich) | found / not_found | found / unknown |
| Hashnode | [sandeep](https://hashnode.com/@sandeep) | found / not_found | found / not_found |
| SourceHut | [sircmpwn](https://sr.ht/~sircmpwn/) | found / not_found | found / not_found |
| TradingView | [TradingView](https://www.tradingview.com/u/TradingView/) | found / not_found | found / not_found |
| Hearthis.at | [hearthis-alh](https://hearthis.at/hearthis-alh/) | unknown / not_found | found / not_found |
| Flipboard | [Flipboard](https://flipboard.com/@flipboard) | found / not_found | found / not_found |
| Asciinema | [asciinema](https://asciinema.org/~asciinema) | found / not_found | found / not_found |
| Disqus | [disqus](https://disqus.com/by/disqus/) | unknown / not_found | found / not_found |
| Freesound | [freesound](https://freesound.org/people/freesound/) | found / not_found | found / not_found |
| Geocaching | [Signal](https://www.geocaching.com/p/default.aspx?u=Signal) | found / not_found | found / not_found |
| Hackaday | [svofski](https://hackaday.io/svofski) | found / not_found | found / not_found |
| HackerEarth | [tourist](https://www.hackerearth.com/@tourist/) | unknown / not_found | found / not_found |
| Hackster.io | [machinaut](https://www.hackster.io/machinaut) | unknown / not_found | found / not_found |
| HubPages | [hubpages](https://hubpages.com/@hubpages) | unknown / unknown | found / not_found |
| Instructables | [randofo](https://www.instructables.com/member/randofo) | unknown / not_found | found / not_found |
| Issuu | [issuu](https://issuu.com/issuu) | found / not_found | found / not_found |
| LottieFiles | [lottiefiles](https://lottiefiles.com/lottiefiles) | found / not_found | found / not_found |
| OpenGameArt | [bart](https://opengameart.org/users/bart) | found / not_found | found / not_found |
| OpenStreetMap | [woodpeck](https://www.openstreetmap.org/user/woodpeck) | found / not_found | found / not_found |
| Speaker Deck | [simon](https://speakerdeck.com/simon) | found / not_found | found / not_found |
| CTAN | [knuth](https://ctan.org/author/knuth) | found / not_found | found / not_found |
| Gradle | [gradle](https://plugins.gradle.org/u/gradle) | found / not_found | found / not_found |
| Habr | [deniskin](https://habr.com/ru/users/deniskin/) | found / not_found | found / not_found |
| LinuxFR.org | [patrick_g](https://linuxfr.org/users/patrick_g) | found / not_found | found / not_found |

## Algılama değişiklikleri

- Her site için en az iki bağımsız HTML öğesi gerekir: istenen profilin canonical
  veya Open Graph adresi, profil türü, kullanıcı adı alanı, profil başlığı veya
  siteye özgü profil bağlantıları birlikte değerlendirilir.
- SourceHut, Freesound, Gradle, Geocaching, CTAN ve LinuxFR için kendi DOM alanları
  kullanılır. Görünen ad ile kullanıcı adının farklı olabileceği sitelerde,
  adres ve profil öğeleriyle kimlik doğrulanır; başlıklar değişirse sonuç belirsiz kalabilir.
- Disqus adresi `/by/{username}/` olarak düzeltildi. HackerEarth ve Habr için
  gözlenen canonical host/adres biçimleri kullanıldı.
- Hashnode'un HTTP 200 eksik kullanıcı sayfası, tam eksik profil başlığı ve
  `og:site_name=Hashnode` birlikte mevcutsa `not_found` kabul edilir.
- CodeChef'in `/users/tourist` yanıtı başka bir kullanıcı adına yönlendi;
  bu bir kullanıcı adı eşleşmesi değildir. Güncel `gennady.korotkevich` referansı
  ayrı istekle doğrulandı. Eksik kullanıcı ana sayfaya yönlendiği için `unknown`
  tutuldu; JavaScript içindeki hata mesajı tek başına eksiklik kanıtı yapılmadı.
- Geocaching'de `u` sorgu parametresi de istenen kullanıcıyla eşleşmelidir.
- Yabancı host, başka profil adresi, desteklenmeyen URL şeması, script/yorum
  içindeki sahte kanıt, erişim engeli ve sunucu hataları doğrulama sayılmaz.
- Standart/derin tarama ayarları ve mevcut 15 sitelik sağlık kontrolü referans
  kümesi korundu; katalog güvenilirlik etiketleri topluca yükseltilmedi.

## Elenen adaylar

Aşağıdaki adaylara bu çalışmada yeni olumlu algılama kuralı eklenmedi. Bunlar
kullanıcı yokluğu olarak yorumlanmadı; erişim engeli veya zayıf yanıt için
`unknown` davranışı korunur. Tablodaki `not_found` yalnızca seçilen girdinin
eski algılayıcı sonucudur, o serviste algılamanın bütünüyle çalıştığı anlamına gelmez.

| Aday | Referans / negatif gözlemi | HTTP veya bağlantı durumu |
| --- | --- | --- |
| Anime-Planet | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Apple Developer Forums | unknown / unknown | 200 / 200 |
| ArchiveOfOurOwn | unknown / unknown | 403 / 403 |
| Bandcamp | not_found / not_found | 404 / 404 |
| Bugcrowd | unknown / not_found | 200 / 404 |
| BuyMeACoffee | not_found / not_found | 404 / 404 |
| COLOURlovers | unknown / unknown | 403 / 403 |
| Codecademy | unknown / not_found | 200 / 200 |
| Codepen | unknown / unknown | 403 / 403 |
| Coroflot | unknown / unknown | 403 / 403 |
| Exposure | unknown / unknown | 403 / 403 |
| Fandom | unknown / unknown | 403 / 403 |
| Flickr | unknown / unknown | 502 / 502 |
| GameFAQs | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| GameSpot | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| GiantBomb | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Giphy | not_found / not_found | 200 / 200 |
| HackMD | found / not_found | 200 / 404 |
| IFTTT | found / not_found | 200 / 404 |
| Instapaper | unknown / unknown | 200 / 200 |
| Itch.io | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Kaggle | not_found / not_found | 404 / 404 |
| Ko-fi | unknown / unknown | 403 / 403 |
| Kongregate | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Letterboxd | unknown / unknown | 403 / 403 |
| MyDramaList | unknown / unknown | 403 / 403 |
| NPM | unknown / unknown | 403 / 403 |
| Newgrounds | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| NintendoLife | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Osu! | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Pinkbike | unknown / unknown | 403 / 403 |
| ProductHunt | unknown / unknown | 403 / 403 |
| PureXbox | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| PushSquare | unknown / unknown | bağlantı hatası veya zaman aşımı / bağlantı hatası veya zaman aşımı |
| Replit | not_found / not_found | 404 / 404 |
| ReverbNation | not_found / not_found | 200 / 404 |
| Smule | unknown / unknown | 403 / 403 |
| Sporcle | unknown / unknown | 403 / 403 |
| Threadless | unknown / unknown | 403 / 403 |
| Trakt | unknown / unknown | 200 / 200 |
| Vimeo | not_found / not_found | 410 / 404 |
| freeCodeCamp | not_found / not_found | 404 / 404 |

## Doğrulama ve yerel dosyalar

- Çalışma öncesi test tabanı: 253 test geçti.
- Yeni testler; 30 gerçek yanıt biçimi, negatif kontroller, yanlış kimlik,
  her kanıt öğesinin ayrı kaldırılması, script/yorum içine gizlenmiş kanıt,
  202/401/403/406/429/5xx, 404/410 challenge, yabancı yönlendirme ve sorgu
  parametresi uyuşmazlığını kapsar.
- Önceden var olan yerel değişiklikler korundu. İş öncesi dört dosya yedeği
  arşiv içeriği kaynak dosyalarla birebir karşılaştırılarak doğrulandı.
- Tam HTTP yanıtları geçici çalışma klasöründe tutuldu; repoya yalnızca küçük
  HTML örnekleri eklendi. Örneklerde cookie, CSRF token veya script bulunmaz.
- Commit, push veya sürüm değişikliği yapılmadı.

Son doğrulama: **262 test geçti** (253 mevcut + 9 yeni test metodu); katalogdaki
303 site için örnek yanıt sözleşmeleri korundu. `git diff --check` geçti.
