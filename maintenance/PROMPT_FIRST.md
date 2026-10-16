# Tek üretim isteğiyle metin akışı

Metin üretimi gerçek kaynak + kanal promptu + zorunlu JSON şeması ile tek Groq üretim isteğinde yapılır.
Ayrı editör, bağımsız çözücü, valid/evidence kararı ve yayın onayı özeti kullanılmaz.
Kaynak eşleşmesi, kapsam, sayı, Türkçe anlatım ve başlık uyumu ilk promptta tarif edilir.
Model kendi hazırlığını aynı yanıt içinde yapar; bu hazırlık çıktı alanı veya ikinci çağrı değildir.

Başarılı yanıttan sonra metin TTS ve video için biçimlenir. İçerik anlamı veya kelime hedefi
nedeniyle ret ve yeniden üretim yapılmaz. Süre hedefi promptta verilir; ses süresi yeni metin
istemek için kullanılmaz. Boş zorunlu alan, kullanılamayan JSON, YouTube API sınırı ve bozuk
medya gibi teknik hatalar işlemi durdurabilir. Bunlar yeni içerik çağrısı başlatmaz.
Tekrar yüklemeyi engelleyen geçmiş ve kayıtlı video kimlikleri korunur.

Normalde video başına bir üretim çağrısı vardır. Ağ, sunucu veya sağlayıcı JSON hatalarında
istemci en fazla üç HTTP denemesi yapabilir; tüm denemeler mevcut kota bütçesine dahildir.
HTTP 429 ve kayıtlı bekleme süresi durdurma davranışı korunur. Haber ve quiz günlük bütçesi
video sayısının üç katıdır. İlginç Gerçekler günlük bütçesi de video sayısının üç katıdır.
Prompt doğruluğu iyileştirmeye yöneliktir; tek başına olgusal doğruluk garantisi değildir.
