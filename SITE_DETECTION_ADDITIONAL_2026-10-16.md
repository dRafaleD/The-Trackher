# Ek site algılama incelemesi — 16 Ekim 2026

24 aday, bir herkese açık referans girdi ve rastgele negatif kontrolle incelendi.
10 siteye özel kurallar eklendi. Önceki değişiklikler, 303 site ve mevcut sağlık
kontrolü referans kümesi korundu; güvenilirlik etiketleri topluca yükseltilmedi.

## Doğrulanan sonuçlar

- İndirilen tam HTTP yanıtları yeni algılayıcıyla tekrar değerlendirildi:
  10 referans `found`; 8 negatif `not_found`; 2 negatif `unknown`.
- Sonraki canlı tekrar: 9 referans `found`; YouTube referansı `unknown` / `network_error`.
  YouTube için yapılan tek ek tekrar da `ConnectError` verdi. İlk başarılı HTTP 200
  yanıtı yeni kuralla doğrulanır; son canlı bağlantıların başarılı olduğu iddia edilmez.
- Negatiflerin canlı tekrarında 8 `not_found`; Instagram ve Pinterest için 2 `unknown`.

| Site | İlk yakalamadaki herkese açık referans | Önce referans / negatif | Yeni tam-yanıt tekrarı | Son canlı referans / negatif |
| --- | --- | --- | --- | --- |
| Instagram | [instagram](https://www.instagram.com/instagram/) | found / unknown | found / unknown | found / unknown |
| Pinterest | [pinterest](https://www.pinterest.com/pinterest/) | found / not_found | found / unknown | found / unknown |
| Snapchat | [teamsnapchat](https://www.snapchat.com/@teamsnapchat) | found / not_found | found / not_found | found / not_found |
| YouTube | [youtube](https://www.youtube.com/@youtube) | found / not_found | found / not_found | unknown / not_found |
| Spotify | [spotify](https://open.spotify.com/user/spotify) | found / not_found | found / not_found | found / not_found |
| Osu! | [peppy](https://osu.ppy.sh/users/2) | not_found / not_found | found / not_found | found / not_found |
| Audiomack | [audiomack](https://audiomack.com/audiomack) | found / not_found | found / not_found | found / not_found |
| Jellyfin Weblate | [joshuaboniface](https://translate.jellyfin.org/user/joshuaboniface/) | found / not_found | found / not_found | found / not_found |
| Laracasts | [jeffreyway](https://laracasts.com/@jeffreyway) | found / not_found | found / not_found | found / not_found |
| TeknoSeyir | [gamsizm](https://teknoseyir.com/u/gamsizm) | found / not_found | found / not_found | found / not_found |

## Siteye özel kurallar

- Instagram: İstenen Open Graph profil URL'si, profil türü ve kullanıcı adını
  içeren başlık birlikte gerekir. Genel Instagram sayfası belirsiz kalır.
- Pinterest: Canonical URL, profil türü ve kullanıcı adına bağlı profil başlığı
  birlikte gerekir. Boş HTTP 200 yanıtı yokluk kanıtı değildir.
- Snapchat: Gözlenen `/@{username}` adresi kullanılır; canonical URL, Open Graph
  URL'si ve kullanıcı adını içeren başlık birlikte doğrulanır.
- YouTube: İstenen handle'ın mobil alternatif bağlantısı, profil türü ve site adı
  gerekir. Canonical URL geçerli bir `UC` kanal kimliği taşımalı; Open Graph URL'si
  aynı kimliğe birebir eşleşmelidir. İlk yanıt 2.122.312 karakter olduğu için sadece
  YouTube biçiminde 3.000.000 karakterlik üst sınır kullanılır. Diğer biçimlerdeki
  2.000.000 karakter sınırı korunur. Scriptler çalıştırılmaz ve profil kanıtı sayılmaz.
- Spotify: İstenen kullanıcı için canonical ve Open Graph adresleriyle profil türü
  birlikte eşleşir.
- Audiomack: Canonical adres, `profile:username` ve profil türü gerekir. HTTP 200
  eksik kullanıcı sayfası ancak `NotFoundPage-title` içindeki tam `Page Not Found`
  başlığı ve site ana adresi birlikte mevcutsa yokluk kanıtıdır.
- osu!: Kullanıcı adından `/users/<sayısal kimlik>` adresine yönlendirme desteklenir.
  İstenen kullanıcı adı, site adı, dönen adresin kimliği ve iki ayrı URL metadata
  alanı birlikte doğrulanır. Başka bir kullanıcıya veya genel sayfaya yönlendirme
  kabul edilmez. Bu, referans profil için önceki yanlış negatif sonucu düzeltir.
- Jellyfin Weblate: Kullanıcı sayfası başlığı, tam kullanıcı bağlantısı ve Weblate
  site adı birlikte gerekir.
- Laracasts: Profil türü, tam kullanıcı URL'si ve kullanıcıya özel başlık eşleşir.
- TeknoSeyir: İstenen canonical ve Open Graph URL'leri, `span.username` içindeki
  tam `@kullanıcıadı` ile eşleşir. Genel HTTP 200 sayfada rastgele “sayfa bulunamadı”
  yazması tek başına yokluk kanıtı sayılmaz; eski test bu daha katı sözleşmeye uyarlandı.

## Yeni olumlu kural eklenmeyen adaylar

Referans girdilerinin her serviste mutlaka var olan hesaplar olduğu varsayılmadı.
İki girdinin aynı cevabı alması olumlu algılama kanıtı sayılmadı.

| Site | Referans / negatif | HTTP veya bağlantı durumu |
| --- | --- | --- |
| TikTok | unknown / unknown | 200 / 200 |
| Vimeo | not_found / not_found | 404 / 404 |
| VSCO | unknown / unknown | 403 / 403 |
| NintendoLife | unknown / unknown | 403 / 403 |
| PushSquare | unknown / unknown | 403 / 403 |
| PureXbox | unknown / unknown | 403 / 403 |
| Newgrounds | unknown / unknown | 403 / 403 |
| Flightradar24 | unknown / unknown | 403 / 403 |
| MyMiniFactory | unknown / unknown | 403 / 403 |
| Aparat | unknown / unknown | 200 / 200 |
| ReverbNation | unknown / not_found | ReadTimeout / 404 |
| Nairaland | unknown / unknown | 403 / 403 |
| ModDB | unknown / unknown | 403 / 403 |
| Redbubble | unknown / unknown | 403 / 403 |

## Testler ve kapsam

Son test turunda **283 test geçti**; `git diff --check` temiz.

Yeni testler tam kimlik uyuşmazlığını, her kanıt öğesinin ayrı çıkarılmasını,
script/yorum içine saklanmış sahte HTML'yi, challenge ve hata yanıtlarını, yabancı
host ve profil yollarını, YouTube/osu! kimlik uyuşmazlıklarını ve yanıt boyutu
sınırlarını kapsar. Tam yanıtlar geçici çalışma klasöründe; repoya eklenen küçük
HTML örneklerinde cookie, token veya script bulunmaz.

Giriş, CAPTCHA veya TLS engeli aşılmadı. Sonuçlar bu tarih ve ortamdaki kontrol
çiftlerine aittir; her kullanıcı adı için başarı garantisi değildir. GUI koduna
bu çalışmada dokunulmadı. Commit, push, sürüm değişikliği veya `.exe` paketleme yapılmadı.
