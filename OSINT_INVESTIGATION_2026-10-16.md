# Trackher OSINT geliştirmeleri — 16 Ekim 2026

## Kullanım

Kaynak koddan çalışan Trackher arayüzünü yeniden açın. Kullanıcı adı aramasından önce **Bağlantılardan keşfet** seçeneğini açarak bulunan doğrulanmış profillerin açıkça paylaştığı diğer desteklenen profil bağlantılarını kontrol edebilirsiniz. Keşif bir adımla ve en fazla 10 adayla sınırlıdır; kişisel sitelerde sınırsız gezinme yapmaz.

Sonuç listesinden bir satır seçip **Kanıt** düğmesine basın. Kaynak adresi, kontrol zamanı, HTTP durumu, algılama yöntemi, açıklama ve çıkarılabilen profil alanları görünür. Biyografi, avatar adresi, ad ve bağlantılar yalnızca kaynağın sunduğu ölçüde eklenir.

Bir alan adı yazıp **Alan adı** düğmesine basarak A, AAAA, MX, NS ve RDAP kayıtlarını inceleyin. E-posta yazıldığında bu işlem adresin alan adını inceler; posta kutusunun varlığını kanıtlamaz.

**Kuralları doğrula**, referans profili tanımlanmış 54 site için olumlu ve olumsuz kontrol çiftlerini çalıştırır. Sonuçlar 24 saat önbellekte tutulur; kural değişikliği önbelleği geçersiz kılar. Son başarılı referans doğrulamasının tarihi gösterilir. Bu kontrol isteğe bağlıdır; arka planda zamanlanmış görev kurulmaz.

## Eklenen davranışlar

- Profil alanlarının kaynağı ve kontrol zamanı saklanır; e-posta sonuçları ortak kanıt biçiminde raporlanır.
- Profil eşleştirmesinde açık profil bağlantıları ve karşılıklı bağlantılar açıklanabilir işaretler olarak kullanılır. Aynı kullanıcı adı tek başına kimlik eşleşmesi sayılmaz.
- MD5 ve SHA-256 avatar özetleri ayrı değerlendirilir. Ortak sosyal platform alan adları kişisel site eşleşmesi sayılmaz.
- JSON ve HTML raporları kanıtları ve alan adı araştırmasını içerir.
- Bulundu, bulunamadı, olası ve doğrulanamadı durumları korunur. Bir profilin varlığı aynı kişiye ait olduğunu tek başına kanıtlamaz.
- Arayüzün üst alanı sıkıştırılarak mevcut ekran ölçeklemesinde sonuç tablosuna yer ayrıldı; kategori renkleri korundu.

## Doğrulama ve sınırlar

- 301 otomatik test başarılı; bağlantı keşfi sınırları, iptal/zaman aşımı, kanıt kaynakları, rapor kaçışları, alan adı kaynakları ve kural önbelleği test edildi.
- Canlı kontrol: GitHub `octocat` profilinde profil alanları ve kaynak kanıtı alındı. `example.com` alan adı araştırmasında DNS ve RDAP sonuçları tamamlandı.
- Arayüz bileşenleriyle kanıt penceresi ve sonuç aktarımı sınandı. Mevcut 125% ölçekleme ve 960 piksel ekran yüksekliğinde sonuç tablosunun görünür alanı 127 piksel ölçüldü.
- 54 sitenin tamamında yeni bir canlı doğrulama turu çalıştırılmadı. Site erişimi, hız sınırları ve içerik değişiklikleri doğrulanamadı sonucu üretebilir.
- Bu çalışma yereldir. Sonraki adımda güncel `.exe`, `dist/local-20261016/Trackher` altında paketlendi; eski `dist/Trackher` paketi değiştirilmedi. Commit/push yapılmadı. Paketleme ayrıntıları: `PACKAGING_2026-10-16.md`.

Alan adı araştırması DNS Google ve [IANA RDAP bootstrap](https://data.iana.org/rdap/dns.json) üzerinden bulunan kayıt otoritesini kullanır. RDAP yanıt biçimi: [RFC 9083](https://www.rfc-editor.org/rfc/rfc9083.html).
