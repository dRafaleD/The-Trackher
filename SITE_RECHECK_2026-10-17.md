# Doğrulanamayan siteler: sınırlı yeniden kontrol — 17 Ekim 2026

Kontrol aralığı: 17 Ekim 2026 00:59–01:00 Türkiye saati (16 Ekim 21:59–22:00 UTC).
Katalogdaki bilinen herkese açık referanslar ile `thneg404q7x9z2` negatif kontrolü kullanıldı. Beş sitede on profil kontrolü yapıldı; eşzamanlılık 1, HTTP zaman aşımı 12 saniye, her kontrol için dış süre sınırı 25 saniyeydi. Siteye ait mevcut istek aralıkları korundu. TLS doğrulaması değiştirilmedi, erişim korumaları aşılmadı.

## Canlı sonuçlar

| Site | Pozitif referans | Pozitif | Negatif | Kanıt / sınırlama |
|---|---|---|---|---|
| YouTube | `youtube` | unknown | unknown | İki istekte de `ConnectError / network_error`; HTTP yanıtı alınmadı. Profilin varlığı/yokluğu çıkarılmadı. |
| CodeChef | `gennady.korotkevich` | found | unknown | Pozitif HTTP 200, profil kimlik alanları eşleşti. Negatif istek ana sayfada HTTP 200 ile sonlandı; `redirect_changed` korundu. |
| Instagram | `instagram` | found | not_found | Her iki yanıt HTTP 200. Negatif sonuç istenen profile bağlı etkin rota 404 verisiyle doğrulandı. |
| Pinterest | `pinterest` | found | not_found | Her iki yanıt HTTP 200. Negatif sonuç istenen kullanıcıya bağlı UserResource kod 30 kaydıyla doğrulandı. |
| HackerNews | `pg` | found | not_found | Açık HTML profili kanonik adres, başlık ve kullanıcı bağlantısıyla eşleşti. Negatif HTTP 200 yanıtı tam `No such user.` kanıtını verdi. |

CodeChef için ayrıca yönlendirmeyi izlemeyen bir kamuya açık profil isteği yapıldı. Bu istek HTTP 403, `Attention Required! | Cloudflare` başlığı verdi; açık bir hesap-yokluk sinyali içermedi. Farklı yanıtlar erişimin değişken olduğunu gösterir; yeni bir yokluk kuralı için yeterli değildir.

**Algılama kodu veya katalog değiştirilmedi.** YouTube erişim hatası ve CodeChef ana sayfa yönlendirmesi kesin yokluk kanıtı olarak yorumlanmadı. Diğer üç sitenin önceki düzeltmeleri kontrol çiftinde yeniden geçti; bu, tüm profiller için garanti değildir.

## Daha geniş mevcut kapsam

- Katalog 303 site içeriyor; bunların 54'ünde pozitif referans tanımlı.
- `reports/site-validation-20261017/final-health.json` içindeki 54 kayıt, daha yeni `reports/unresolved-sites-20261017/health.json` beş-site sonuçlarıyla birleştirildiğinde **52 HEALTHY, 1 DEGRADED (YouTube), 1 UNKNOWN (CodeChef)** bulunuyor. Bunların yalnızca beşi bu turda canlı kontrol edildi.
- Yerel sağlık önbelleğinde site başına en yeni kayıtlar da aynı iki gerçek katalog sitesini çözümsüz gösteriyor. Ayrıca Ağustos tarihli `Example` test kaydı bulunuyor; gerçek site dağılımına dahil edilmedi. Eski kural parmak izlerine ait başarısız kayıtlar güncel site hatası olarak sayılmadı.
- Kalan 249 sitenin referanslı canlı kontrolü bu raporda yoktur; bunlar sağlıklı ilan edilmez. Bu gruptaki YazBel Forum, mevcut katalogda TLS sertifikasının alan adıyla eşleşmemesi nedeniyle kapalıdır. TLS gevşetilmedi.
- Mevcut güncel kanıtlarda başka bir referanslı sitede yeniden kontrol gerektiren başarısız çift görülmedi. Referanssız 249 site için önce siteye uygun pozitif/negatif örnek gerekir; bu turda geniş tarama yapılmadı.

## Doğrulama

Mevcut testlerde CodeChef ana sayfa yönlendirmesi, site kimliği, challenge yanıtları, YouTube kanal kimliği ve gövde sınırı, Instagram/Pinterest yapılandırılmış yokluk verisi ve HackerNews HTML ek kontrolü zaten kapsanıyor. Aynı davranışları tekrar eden yeni testler eklenmedi.

`python -m unittest discover -s tests -p 'test_*profiles*.py' -q`: **53 test başarılı**.

Canlı kontrolün kısa kanıt çıktısı geçici dosyada saklandı: `%TEMP%\trackher-site-recheck-20261017.json`. Ham kullanıcı sayfaları veya çerezler rapora eklenmedi. Sağlık önbelleği, paketler ve eski raporlar değiştirilmedi; commit/push yapılmadı.
