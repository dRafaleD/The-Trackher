# Katkıda Bulunma

Değişiklikleri küçük ve doğrulanabilir tutun. Yeni bir OSINT kontrolü eklerken
yan etki üretmediğini, yalnızca açık kanıtla pozitif sonuç verdiğini ve hedef
platformun koşullarına uygun olduğunu gösteren birim testi de ekleyin. Parola
sıfırlama, OTP, sahte kayıt veya sahte oturum açma istekleri kabul edilmez.

Göndermeden önce şu kontrolleri çalıştırın:

```bash
python -m pip check
python -m compileall -q footprint osint utils gui.py main.py setup_context_menu.py
python -m unittest discover -s tests -v
```

Temizlik veya shredder değişiklikleri gerçek kullanıcı dizinlerinde denenmemeli;
testler geçici dizin ve mock kullanmalıdır. Yeni platform yolları Windows, macOS
ve Linux testleriyle birlikte gelmelidir.
