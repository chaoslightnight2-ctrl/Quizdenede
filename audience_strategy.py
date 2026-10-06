"""Audience priorities and measured feedback, never substitute narration."""
import re
import unicodedata

TOPICS = {
    'economy_life': 'ekonomi fiyat kira ucret maas vergi emekli market konut housing rent cost inflation wage economy energy fuel',
    'health_education': 'saglik egitim okul ogrenci hastane asi health education school student hospital vaccine',
    'transport_cities': 'ulasim trafik tren metro ucus yolcu transport traffic train flight passenger travel',
    'technology_science': 'bilim teknoloji yapay zeka telefon internet uzay science technology ai internet space astronomy invention',
    'daily_life': 'gunluk hayat esya yemek uyku hava everyday daily life object food sleep weather',
    'human_behavior': 'psikoloji davranis hafiza algi dikkat psychology behavior memory perception attention',
    'nature': 'doga hayvan deniz iklim animal nature ocean climate biology',
    'culture': 'kultur tarih dil culture history language',
}

def normalize(text):
    text = unicodedata.normalize('NFKD', str(text).casefold()).replace('ı', 'i')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()

def category(text):
    value = normalize(text)
    scores = {key: sum(bool(re.search(r'\b' + re.escape(word) + r'\w*', value)) for word in hints.split())
              for key, hints in TOPICS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else 'other'

def audience_score(item, channel):
    text = ' '.join(str(item.get(k, '')) for k in ('title', 'summary', 'query', 'topic'))
    bucket = category(text)
    value = normalize(text)
    domestic = bool(re.search(r'\b(turkiye|turkey|turkish|istanbul|ankara|izmir|antalya|bursa)\b', value))
    if channel == 'Türkiye’den Haber':
        score = 24 if domestic else 0
        score += 16 if bucket in ('economy_life', 'health_education', 'transport_cities') else 6
    elif channel == 'Global Haber':
        score = 20 if domestic else 0
        score += 14 if bucket in ('economy_life', 'health_education', 'transport_cities', 'technology_science', 'nature') else 0
    else:
        score = 12 if bucket in ('technology_science', 'daily_life', 'human_behavior', 'nature') else 0
    return score

def brief(channel):
    if channel == 'Türkiye’den Haber':
        return ('Türkiye’de yaşayan izleyicinin günlük hayatına açıkça temas eden haberleri önceliklendir '
                'fiyatlar ücretler konut ulaşım eğitim sağlık kamu hizmetleri ve tüketici teknolojisi '
                'Yabancı bir haberi Türkiye’ye etkiliyormuş gibi yeniden kurma Böyle bir bağ yalnızca kaynakta açıkça varsa anlat')
    if channel == 'Global Haber':
        return ('Türkçe konuşan geniş kitle için önemli dünya gelişmelerini seç ekonomi enerji seyahat teknoloji bilim sağlık '
                've çevre Önce olayın somut değişikliğini anlat Türkiye ile bağlantı ancak kaynakta açıkça varsa kurulabilir '
                'Yerel yabancı magazin veya tanınmayan kişi haberini sırf yeni olduğu için önceliklendirme')
    if channel == 'Zekanı Test Et':
        return ('Geniş kitlenin anlayacağı tanıdık nesneler temel bilim doğa günlük yaşam ve genel kültürden '
                'tek cevaplı kısa sorular seç Özel uzmanlık nadir kişi adları dar yerel yapılar veya bilinmeyen programlar '
                'üzerine soru kurmak yerine aynı gerçek kaynak havuzundan erişilebilir bir olgu seç')
    return ('Günlük hayat insan davranışı bilim ve teknoloji ekseninde tanıdık bir olayın anlaşılır açıklamasını seç '
            'Sırf tuhaf adı olan bina kişi veya yer seçme Merakı kaynaktaki somut olguyla karşıla')

STORY_RULES = ('İlk cümlede konunun somut merakını veya değişikliğini doğrudan söyle Genel giriş ve kanal tanıtımı yapma '
               'Ortada tek ana olguyu açıkla Son bilgi cümlesi başlık ve ilk cümlede verilen merakın karşılığını versin '
               'Bilinmeyen sonucu sonradan uydurma Kelime doldurma aynı bilgiyi yeniden söyleme '
               'Abonelik çağrısı yalnızca tek kısa kanal adı ve abone ol cümlesi olsun '
               'Başlık kısa anlaşılır ve videoda gerçekten karşılanan bir vaat taşısın '
               'Açıklama yalnızca bu konuya özel olsun Genel viral keşfet trend kelimelerini metadata dolgusu olarak kullanma')
