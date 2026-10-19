# Doğrulanamayan sitelerin yeniden incelemesi — 17 Ekim 2026

Son referans kontrolünde belirsiz kalan Instagram, Pinterest, HackerNews, YouTube ve CodeChef incelendi. Kontroller bilinen herkese açık profiller ve `thneg404q7x9z2` negatif kontrolüyle yapıldı. Ham sayfa yanıtları geçici klasörde tutuldu; regresyon örneklerine yalnızca gerekli kimlik/hata alanları aktarıldı.

## Son durum

| Site | İlk kontrolde + / − | Düzeltme sonrası + / − | Değerlendirme |
|---|---|---|---|
| Instagram | found / unknown | found / not_found | Kontrol çifti geçti |
| Pinterest | found / unknown | found / not_found | Kontrol çifti geçti |
| HackerNews | found / unknown | found / not_found | Kontrol çifti geçti |
| YouTube | found / not_found | unknown / unknown | Ağ erişimi kararsız; kural yokluk üretmiyor |
| CodeChef | found / unknown | found / unknown | Ana sayfaya yönlendirme kesin yokluk kanıtı sayılmadı |

**Üç sitenin kontrol çifti geçti.** YouTube ilk kontrolde geçmesine rağmen yeniden kontrolde her iki istekte de bağlantı hatası verdi. Bu yüzden kalıcı düzelmiş olarak sunulmadı. CodeChef için kesin yokluk kuralı eklenmedi.

## Uygulanan kurallar

### Instagram

HTTP 200 ile gelen genel sayfa başlığı artık tek başına belirleyici değildir. Yalnızca `application/json` ve `data-sjs` işaretli sunucu verisindeki etkin `initialRouteInfo.route` incelenir. Tek bir etkin rota, istenen profil yolu, `PolarisErrorRoute`, `httpErrorPage`, hem rootView hem hostableView için profil türü, gerçek boolean 404 işareti ve boş yaş/giriş kısıtlamaları birlikte gerekir. Genel hata bileşenleri, ön yüklenmiş metinler, farklı kullanıcı rotası ve giriş/yaş kısıtlamaları yokluk kanıtı sayılmaz.

### Pinterest

İki belirli JSON veri bloğu birlikte denetlenir: `__PWS_DATA__` istek bağlamı ve `__PWS_INITIAL_PROPS__` kullanıcı kaynağı. Güncel adres, profil yolu, halka açık profil işleyicisi ve tam kullanıcı adına bağlı `unauth_profile` kaynak anahtarı eşleşmelidir. `fetching=false`, boş veri, HTTP 404, hata kodu 30, `User not found.` mesajı ve `v3_get_user_handler` uç nokta adı birlikte aranır. Rastgele bir scriptteki aynı cümle veya başka kullanıcının hatası yeterli değildir.

### HackerNews

API `null` yanıtı hâlâ belirsizdir. [Resmi API dokümanı](https://github.com/HackerNews/API#users), yalnızca herkese açık etkinliği olan kullanıcıları kapsadığını ve kimliklerin büyük/küçük harfe duyarlı olduğunu belirtir. API kanıtı eksik veya ağ erişimi başarısızsa açık HTML profil sayfası ek olarak kontrol edilir. Kanonik adres, tam profil başlığı ve `hnuser` bağlantısı birlikte eşleşirse profil bulunur. Doğru adreste HTTP 200/404 ile gelen tam `No such user.` yanıtı yokluk kanıtıdır. Login sayfası, JavaScript içindeki metin, farklı harf büyüklüğü ve yönlendirme yeterli değildir. API kimlik eşlemesi bu site için büyük/küçük harfe duyarlı yapıldı. 401/403 ve 429 yanıtlarında ek kontrol başlatılmaz.

### YouTube ve CodeChef

YouTube bu turda hem başarılı profil yanıtı hem bağlantı hataları üretti. TLS doğrulaması veya erişim korumaları gevşetilmedi. Mevcut profil kimliği doğrulaması korunur; ağ hatası `unknown` kalır.

CodeChef negatif kullanıcı isteğini HTTP 302 ile ana sayfasına yönlendiriyor. Ana sayfadaki genel içerik hesabın yokluğunu kanıtlamadığından `unknown / redirect_changed` korunur.

## Doğrulama ve teslim

- 18 yeni test: kullanıcıya bağlı sunucu verisi, yanlış/çelişkili kayıtlar, giriş ve yaş kısıtlamaları, yorum/noscript/template içerikleri, parser sınırları, HackerNews null durumu, harf duyarlılığı, kimlik alanları ve ek istek sınırları.
- Toplam 358 test başarılı. Diğer sitelerin tek istek davranışı korunur; HackerNews için en fazla iki algılama aşaması vardır.
- Python kaynak arşivi ayrı klasöre çıkarılıp aynı 358 test yeniden çalıştırıldı; tamamı başarılıydı. Yeni modül ve örnek dosyaları dağıtım arşivinde doğrulandı.
- Site güvenilirlik etiketleri yükseltilmedi. Başarılı referans kontrolü tüm kullanıcılar için başarı garantisi veya gerçek kişi sahipliği kanıtı değildir.
- Yeni kaynak: `osint/embedded_profiles.py`. JSON verileri ayrıştırılır; sayfa JavaScript kodu çalıştırılmaz. Gövde, veri bloğu sayısı ve JSON dolaşımı sınırlıdır.
- Kanıt dosyaları: `reports/unresolved-sites-20261017/checks.jsonl`, `rechecks.jsonl`, `hackernews-final.jsonl`, `health.json`. Yerel 54 sitelik özet, yalnızca bu beş sitenin son sonuçlarıyla birleştirildi; diğer siteler bu turda yeniden taranmış sayılmaz.
- Güncel yerel Windows paketi `dist/local-20261017-sites` altında hazırlandı. Paket içindeki modül/katalog eşleşmesi, üç sitenin çevrimdışı şema kontrolleri, sürüm komutu ve arayüz açılışı doğrulandı. Önceki paketler korunur. Mevcut sürüm numarası 1.2.0rc8 kalır; commit/push veya resmi yayın yapılmadı.
