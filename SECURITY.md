# Güvenlik Politikası

## Desteklenen Sürüm

Güvenlik düzeltmeleri ana dalın güncel sürümüne uygulanır.

## Açık Bildirme

Bir güvenlik açığı bulursanız depo için GitHub Private Vulnerability Reporting
özelliğini kullanın. Özellik etkin değilse, istismar ayrıntılarını herkese açık
bir issue içinde paylaşmayın; depo sahibiyle özel bir iletişim kanalı açılmasını
isteyen ayrıntısız bir issue oluşturun.

Bildirimde etkilenen işletim sistemini, Python sürümünü, yeniden üretme adımlarını
ve mümkünse zararsız bir kanıtı belirtin. Gerçek kişilere ait e-posta, kullanıcı
adı, token, çerez veya rapor dosyalarını eklemeyin.

## Kapsam

Özellikle şu konular güvenlik açığı olarak değerlendirilir:

- Dışlama listesini veya kritik dizin korumasını aşan silme davranışı
- Komut ya da yol enjeksiyonu
- Raporlarda HTML/JavaScript enjeksiyonu
- İstenmeyen parola sıfırlama, OTP veya güvenlik bildirimi üreten ağ isteği
- Hassas verinin log, rapor veya depoya sızması
