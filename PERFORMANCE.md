# Gerçek izleyici verisiyle geliştirme

`audience-feedback.yml` günlük 23:40 Türkiye saatinde ve elle çalışır. Video yüklemez, Groq çağırmaz. Üretimden önce de ölçümler yenilenir. Rapor Actions cache ve artifact içinde tutulur, herkese açık Git geçmişine yazılmaz.

YouTube Analytics API için aynı kanal sahibinin `https://www.googleapis.com/auth/yt-analytics.readonly` izni gerekir. Ayrı `YOUTUBE_ANALYTICS_REFRESH_TOKEN` Actions secret kullanın. Yoksa mevcut yükleme tokenı ile salt okunur erişim denenir; izin yetersizse rapor `unavailable` olur. Yükleme tokenını veya yükleme akışını değiştirmeyin. Her kanal ayrı yetkilendirilir.

API gerçek engagedViews, averageViewDuration, averageViewPercentage ve ilk altı uygun videonun tutma eğrisini toplar. Tutma eğrisindeki en büyük ardışık düşüş bir ayrılma işaretidir; kesin bir neden değildir. İzlemeyi seçme oranı engagedViews/views oranından hesaplanmaz.

Studio verisi için UTF-8 CSV sütunları: `video_id,views,engagedViews,averageViewDuration,averageViewPercentage,stayed_to_watch_pct`. Son sütun Studio'daki gerçek izlemeyi seçme yüzdesidir, süre saniyedir. Eksik hücreleri boş bırakın. CSV'yi kanalın ilgili video ID'leriyle eşleştirip `python collect_performance.py --studio-csv DOSYA.csv` çalıştırın. Türkçe Studio dışa aktarma sütun adlarını bu isimlere eşleyin; tahmin edilmiş değer girmeyin.

Yalnızca en az 72 saat önce yayımlanmış ve 100 engagedViews almış videolar öğrenmeye katılır. En az altı video ve kategori/giriş başına üç video gerekir. İzleme yüzdesi ve varsa gerçek izlemeyi seçme oranı kanal medyanıyla karşılaştırılır. Konu bonusu ±8 ile sınırlıdır; girişlerde beşte bir keşif korunur. Tekrarlanan başlangıç/son düşüşleri anlatım talimatını kısaltır. Küçük örneklem viral olma garantisi değildir. Yedi günden eski veya erişilemeyen rapor seçimde kullanılmaz; uydurma ölçüm üretilmez.

Yeni videolara audience_bucket ve hook_style kaydedilir. Eski videoların giriş tarzı tahmin edilmez. Quiz'in question_first yapısı sabittir; öğrenme soru konu alanlarını etkiler.
