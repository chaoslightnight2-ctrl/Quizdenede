# Gerçek izleyici verisiyle geliştirme

`audience-feedback.yml` elle başlatılan okuma izni denemesidir. Okuma izni tamamlanana kadar ayrı bir günlük deneme kurulmaz. Video yüklemez, Groq çağırmaz. Üretimden önce de ölçümler yenilenir. Rapor Actions cache ve artifact içinde tutulur, herkese açık Git geçmişine yazılmaz.

YouTube Analytics API için aynı kanal sahibinin `https://www.googleapis.com/auth/yt-analytics.readonly` ve `https://www.googleapis.com/auth/youtube.readonly` izinleri gerekir. Ayrı `YOUTUBE_ANALYTICS_REFRESH_TOKEN` Actions secret kullanın. Yoksa mevcut yükleme tokenı ile salt okunur erişim denenir; izin yetersizse rapor `unavailable` olur. Yükleme tokenını veya yükleme akışını değiştirmeyin. Her kanal ayrı yetkilendirilir.

API gerçek engagedViews, averageViewDuration, averageViewPercentage ve ilk altı uygun videonun tutma eğrisini toplar. Tutma eğrisindeki en büyük ardışık düşüş bir ayrılma işaretidir; kesin bir neden değildir. İzlemeyi seçme oranı engagedViews/views oranından hesaplanmaz.

Studio Gelişmiş Mod'da aktif izlenme, ortalama görüntüleme süresi, ortalama görüntüleme yüzdesi ve izlemeye devam edenler ölçümlerini seçip mevcut görünümü CSV olarak dışa aktarın. ZIP içindeki `Tablo verileri.csv` dosyasını doğrudan `python collect_performance.py --studio-csv "Tablo verileri.csv"` ile okuyabilirsiniz. Türkçe ve İngilizce Studio sütunları desteklenir; `0:00:13` gibi süreler saniyeye çevrilir. Toplam satırı ve kanalın yükleme geçmişinde bulunmayan video ID'leri alınmaz. Boş veya raporlanmamış hücreler eksik kalır, sıfır uydurulmaz. Raporun tarih aralığını karşılaştırmada dikkate alın; bu elle indirilen rapor API bağlantısının yerine otomatik güncellenmez.

Önceki UTF-8 CSV biçimi de desteklenir: `video_id,views,engagedViews,averageViewDuration,averageViewPercentage,stayed_to_watch_pct`. Bu biçimde süre saniyedir. Son sütun Studio'daki gerçek izlemeye devam edenler yüzdesidir; tahmin edilmiş değer girmeyin.

Yalnızca en az 72 saat önce yayımlanmış ve 100 engagedViews almış videolar öğrenmeye katılır. En az altı video ve kategori/giriş başına üç video gerekir. İzleme yüzdesi ve varsa gerçek izlemeyi seçme oranı kanal medyanıyla karşılaştırılır. Konu bonusu ±8 ile sınırlıdır; girişlerde beşte bir keşif korunur. Tekrarlanan başlangıç/son düşüşleri anlatım talimatını kısaltır. Küçük örneklem viral olma garantisi değildir. Yedi günden eski veya erişilemeyen rapor seçimde kullanılmaz; uydurma ölçüm üretilmez.

Yeni videolara audience_bucket ve hook_style kaydedilir. Eski videoların giriş tarzı tahmin edilmez. Eski yükleme kaydında yalnızca YouTube bağlantısı varsa ID o bağlantıdan okunur; video yayın tarihi bulunmuyorsa ölçümü gösterilir ama öğrenmeye katılmaz. Haber kaynağının yayın tarihi video yayın tarihi sayılmaz. Quiz'in question_first yapısı sabittir; öğrenme soru konu alanlarını etkiler.

Analytics için API'nin açık olduğu kendi Google uygulamanızla her kanal ayrı yetkilendirilebilir. Bu uygulama yükleme uygulamasından farklıysa istemci ayarları `YOUTUBE_ANALYTICS_CLIENT_SECRETS_JSON`, aynı istemciye ait okuma tokenı `YOUTUBE_ANALYTICS_REFRESH_TOKEN` secret alanına kaydedilir. İkisi birlikte kullanılır; yükleme istemcisi/tokenı değiştirilmez. Kayıttan önce kanal ID'si ve gerçek Analytics erişimi doğrulanır.
