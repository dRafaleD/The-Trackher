# Trackher — 54 sitenin canlı referans kontrolü

Kontrol tamamlanması: 17.10.2026 00:11 (Türkiye saati).

54 sitede bilinen bir profil ve sentetik negatif kullanıcı adı (`thneg404q7x9z2`) kontrol edildi. İlk tur 108 profil kontrolünden oluştu. Snapchat, About.me, YouTube ve HackerNews için toplam 8 yeniden kontrol yapıldı. HTTP istek sayısı, yönlendirmeler ve algılama zincirleri nedeniyle kontrol sayısından farklı olabilir.

**Sonuç: 49 çift geçti, 1 erişim/ağ kısıtlı, 4 belirsiz; 0 yapılandırma hatası.**

## Kanıta dayalı düzeltmeler

- Snapchat: Türkçe sayfa başlığı için açık bir ikinci başlık son eki eklendi. Tam profil adresi, Open Graph profil adresi ve kullanıcı adını içeren başlık birlikte zorunludur. İngilizce kural korunur. Canlı yeniden kontrolde `found / not_found` elde edildi.
- About.me: `og:type=profile`, mevcut `aboutme_prod:page` tipine ek bir varyasyon olarak kabul edildi. Tam profil adresi ve boş olmayan profil adı hâlâ zorunludur. Canlı yeniden kontrolde `found / not_found` elde edildi.
- Bu düzeltmeler için üç otomatik test ve iki küçültülmüş HTML örneği eklendi. Toplam 324 test geçti. Algılama güvenilirlik etiketleri yükseltilmedi.

## Kalan belirsizlikler

- YouTube: olumlu kontrol ağ hatası verdi; negatif kontrol yokluk kanıtı sundu.
- Instagram ve Pinterest: bilinen profiller bulundu; sentetik negatiflerde kesin yokluk kanıtı çıkarılamadı.
- HackerNews: yeniden kontrolde olumlu profil bulundu; sentetik negatifte profil kanıtı uyuşmadı. İlk turda ağ hatası alınmıştı.
- CodeChef: olumlu profil bulundu; negatif adres yönlendirme nedeniyle doğrulanamadı.
- Erişim engeli veya yetersiz kanıt, hesabın yokluğu olarak sunulmadı. Bu küçük referans kümesindeki başarı tüm kullanıcı adları için başarı garantisi değildir.

## Site bazında son sonuç

| Site | Olumlu | Negatif | Çift | Belirsizlik nedeni |
|---|---|---|---|---|
| About.me | found | not_found | Çift geçti | — |
| AniList | found | not_found | Çift geçti | — |
| Asciinema | found | not_found | Çift geçti | — |
| Audiomack | found | not_found | Çift geçti | — |
| Behance | found | not_found | Çift geçti | — |
| Chess.com | found | not_found | Çift geçti | — |
| Codeberg | found | not_found | Çift geçti | — |
| CodeChef | found | unknown | Belirsiz | redirect_changed |
| CTAN | found | not_found | Çift geçti | — |
| Dev.to | found | not_found | Çift geçti | — |
| DeviantArt | found | not_found | Çift geçti | — |
| Disqus | found | not_found | Çift geçti | — |
| DockerHub | found | not_found | Çift geçti | — |
| DonanımHaber | found | not_found | Çift geçti | — |
| Dribbble | found | not_found | Çift geçti | — |
| Flipboard | found | not_found | Çift geçti | — |
| Freesound | found | not_found | Çift geçti | — |
| Geocaching | found | not_found | Çift geçti | — |
| Gitea | found | not_found | Çift geçti | — |
| GitHub | found | not_found | Çift geçti | — |
| GitLab | found | not_found | Çift geçti | — |
| Gradle | found | not_found | Çift geçti | — |
| Habr | found | not_found | Çift geçti | — |
| Hackaday | found | not_found | Çift geçti | — |
| HackerEarth | found | not_found | Çift geçti | — |
| HackerNews | found | unknown | Belirsiz | parser_mismatch |
| Hackster.io | found | not_found | Çift geçti | — |
| Hashnode | found | not_found | Çift geçti | — |
| Hearthis.at | found | not_found | Çift geçti | — |
| HubPages | found | not_found | Çift geçti | — |
| Instagram | found | unknown | Belirsiz | parser_mismatch |
| Instructables | found | not_found | Çift geçti | — |
| Issuu | found | not_found | Çift geçti | — |
| Jellyfin Weblate | found | not_found | Çift geçti | — |
| Keybase | found | not_found | Çift geçti | — |
| Laracasts | found | not_found | Çift geçti | — |
| Lichess | found | not_found | Çift geçti | — |
| LinuxFR.org | found | not_found | Çift geçti | — |
| LottieFiles | found | not_found | Çift geçti | — |
| MyAnimeList | found | not_found | Çift geçti | — |
| OpenGameArt | found | not_found | Çift geçti | — |
| OpenStreetMap | found | not_found | Çift geçti | — |
| Osu! | found | not_found | Çift geçti | — |
| Pastebin | found | not_found | Çift geçti | — |
| Pinterest | found | unknown | Belirsiz | parser_mismatch |
| Snapchat | found | not_found | Çift geçti | — |
| SoundCloud | found | not_found | Çift geçti | — |
| SourceHut | found | not_found | Çift geçti | — |
| Speaker Deck | found | not_found | Çift geçti | — |
| Spotify | found | not_found | Çift geçti | — |
| Steam | found | not_found | Çift geçti | — |
| TeknoSeyir | found | not_found | Çift geçti | — |
| TradingView | found | not_found | Çift geçti | — |
| YouTube | unknown | not_found | Erişim/ağ kısıtlı | network_error |

## Dosyalar ve paket

- `reports/site-validation-20261017/pairs.jsonl`: ilk 108 kontrolün zaman, kaynak, HTTP, yöntem ve alan kanıtları.
- `reports/site-validation-20261017/rechecks.jsonl`: sekiz yeniden kontrolün kanıtları.
- `reports/site-validation-20261017/health.json`: ilk tur; `final-health.json`: son durum.
- Uygulamanın yerel platform sağlığı özeti 54 sitenin son durumuyla güncellendi. Başarılı doğrulamaların zamanları kural parmak iziyle saklandı.
- Düzeltmeleri içeren yeni yerel Windows paketi: `dist/local-20261017/Trackher`. Önceki günün paketi korunur. Mevcut sürüm numarası 1.2.0rc8 kalır; commit/push veya resmi yayın yapılmadı.
- Python kaynak arşivinde test dosyaları bulunmasına rağmen HTML/JSON örneklerinin eksik olduğu görüldü. `MANIFEST.in` güncellenerek dört test örneği de kaynak arşivine eklendi.
- Kaynak arşivi ayrı bir geçici klasöre çıkarılarak testler yeniden çalıştırıldı: 324 test başarılı. Bu doğrulama, örnek dosyalarının gerçekten dağıtıma girdiğini de sınar.
- Yeni `.exe` içinde güncel kural kodu ve katalog doğrulandı; sürüm komutu, çevrimdışı platform sağlığı JSON raporu ve arayüz açılışı başarılıydı. Kaynak ve Windows paketi sürümleri bu tarihli klasörde eşleşir.
