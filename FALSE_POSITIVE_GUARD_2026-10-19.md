# Yanlış pozitif koruması — 19 Ekim 2026

## Canlı inceleme

Kullanıcının isteği üzerine uygulamanın `check_single_username` motoru, rastgele üretilen iki ayrı kullanıcı adıyla 303 platformun tamamında çalıştırıldı. Platform başına 8 saniyelik ağ, 18 saniyelik toplam kontrol sınırı ve aynı kaynağa istekler arasında bekleme kullanıldı. Bu sonuçlar hesabın kesin olarak bulunmadığını veya erişilemeyen sitelerin sağlıklı olduğunu kanıtlamaz.

| Deneme | Kullanıcı adı | Bulundu | Bulunamadı | Doğrulanamadı |
| --- | --- | ---: | ---: | ---: |
| Değişiklik öncesi | `thfe41454b4a` | 0 | 182 | 121 |
| Değişiklik sonrası | `th959ca2b98a` | 0 | 181 | 122 |

Bu iki canlı denemede bildirilen yanlış pozitif tekrar üretilemedi. İki sorgunun farklı adlar ve zamanlarda yapılması nedeniyle sonuç farkları iyileşme ölçütü değildir. Ham sonuç özetleri `reports/false-positives-20261019/baseline.jsonl` ve `after.jsonl` dosyalarında saklanır.

## Kaynakta bulunan zayıflık ve düzeltme

Eski genel HTML kuralları, kullanıcı adının sayfa gövdesinde geçmesini veya tek bir canonical/başlık/kanal şablonu metnini profil varlığı sayabiliyordu. Bunlar arama, kayıt ve genel uygulama sayfalarında da bulunabilir. Bu karar yolu kaldırıldı. API başarısızlığından sonra açılan genel HTML sayfası da yalnızca adı geri yazarak sonucu bulunduya yükseltemez.

Pozitif sonuç için mevcut yapılandırılmış profil veya özel API/kimlik algılayıcısı gerekir. Yeterli kanıtı olmayan eski HTML siteleri artık **doğrulanamadı** kalır. Bu, zayıf kurallarla önceki bulunan sonuçlarının bazılarının azalmasına neden olur; bunlar otomatik olarak bulunamadı sayılmaz. Siteye özel kanıt eklenerek kapsam genişletilebilir.

Facebook, VK, DonanımHaber, Pastebin ve Bitchute'un eski tek ham metin işaretleri de pozitif karar veremez. Negatif sayfa ve HTTP hata sınıflandırmaları korunur. Bu çalışma tüm siteye özel kuralların hatasız olduğu iddiasını taşımaz.

Kongregate ve Wattpad, canlıdan gözlemlenen canonical adresi ve profil kimlik alanlarıyla yapılandırılmış kontrole taşındı; kullanıcı adının metinde görünmesine dayanan kararları kaldırıldı. Kongregate'in güncel `/en/accounts/` adresi kullanılıyor.

Sağlık önbelleği ve kanıt inceleme parmak izlerine kanıt politikası sürümü eklendi. Eski motorun olumlu sağlık kaydı yeni motorun doğrulaması sayılmaz; kayıt dosyaları silinmez. Açık GUI'deki mevcut sonuçlar değişmez; yeni paketle tekrar tarama gerekir.

## Kontroller

- 303 platformda iki canlı tarama: 606 sonuç, iki sorguda da sıfır bulundu.
- Sekiz referans sitenin pozitif ve negatif kontrolü: Kongregate, Wattpad, Genius Artists, Odysee, GitHub, Mixcloud ve Open Collective çiftleri geçti. RubyGems pozitif kontrolü zaman aşımı nedeniyle doğrulanamadı; negatif kontrol bulunamadı. Kayıt: `reference-recheck.jsonl`.
- Katalog genelinde yansıtılmış kullanıcı adı sayfaları, eski ham işaretler, yorum/script içindeki işaretler, zayıf API HTML dönüşü, eksik/yanlış yapılandırılmış profil alanları ve önbellek politika değişimi regresyon testleri eklendi.

Yerel değişikliktir; commit, push veya yayın yapılmadı.
