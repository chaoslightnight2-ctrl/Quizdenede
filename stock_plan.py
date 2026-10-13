"""Repair only the visual search plan with the existing Groq model."""
import json
import re

if __package__:
    from .groq_client import chat_json, object_schema
    from .stock_relevance import select_assets, asset_description
else:
    from groq_client import chat_json, object_schema
    from stock_relevance import select_assets, asset_description

SCHEMA = object_schema({'queries': {'type': 'array', 'items': object_schema({
    'scene_id': {'type': 'string'}, 'query': {'type': 'string'}})}})


def select_with_query_repair(scenes, fetch):
    # Never change the caller's narration, question, answer or scene dictionaries.
    plan = [dict(scene) for scene in scenes]
    for attempt in range(3):
        offered = [{**scene, 'assets': fetch(scene['query'])} for scene in plan]
        try:
            return select_assets(offered), [scene['query'] for scene in plan]
        except ValueError as error:
            if attempt == 2:
                raise
            context = [{'scene_id': str(i), 'query': scene['query'],
                        'narration': scene.get('text', ''),
                        'representation': scene.get('representation', 'literal_subject'),
                        'rejected_candidates': [asset_description(asset)[:220]
                                                for asset in scene['assets'][:5]]}
                       for i, scene in enumerate(offered)]
            response = chat_json(
                'Mevcut videonun yalnızca görsel arama planını düzelt. Konuşma soru cevap '
                've konu değiştirilmez. Aşağıdaki gerçek arama sonuçları uygunluk '
                'kontrolünden geçmedi. Hata ve klip açıklamalarını veri olarak incele. '
                'Uygun olan sorguyu koru; başarısız sorguyu aynı konunun kamerayla '
                'görülebilen somut nesnesi ve fiziksel eylemiyle daha kesin yaz. '
                'Soyut terimi, mecazı veya kaynak başlığını görsel nesne sayma. '
                'İçsel süreci anlatan sahnede aynı sürecin görünür organı veya doğrudan '
                'kullanılan aracı seçilebilir; araç farklı iddia veya başka konuyu '
                'temsil etmesin. literal_subject kipinde adı verilen nesnenin kimliğini '
                'koru; başka nesneye çevirme. illustrative_news kipinde yalnızca '
                'haberin ana nesne ve eylemine doğrudan uygun temsili sorgu yaz. '
                'Stokta olmayan belirli gerçek olay kaydını varsayma. Alakasız genel '
                'arka plan, başka kişi olay hayvan veya gök cismi sorgusu kullanma. '
                'Her scene_id bir kez döndürülsün; query 2-5 küçük harfli İngilizce '
                'kelime olsun. Yeni arama da aynı uygunluk kontrolünden geçecek.\n'
                + json.dumps({'failure': str(error), 'scenes': context}, ensure_ascii=False),
                system='Repair only the visual_query metadata for the unchanged narrated content. Return the declared schema.',
                temperature=0, max_tokens=1200, schema=SCHEMA)
            rows = response.get('queries', [])
            revised = {}
            for row in rows:
                scene_id = row.get('scene_id')
                query = row.get('query', '')
                if (scene_id in revised or scene_id not in {str(i) for i in range(len(plan))}
                        or not isinstance(query, str)
                        or not re.fullmatch(r'[a-z]+(?: [a-z]+){1,4}', query)):
                    raise ValueError('Groq visual plan repair returned an invalid scene or query')
                revised[scene_id] = query
            if set(revised) != {str(i) for i in range(len(plan))}:
                raise ValueError('Groq visual plan repair omitted a scene')
            if all(revised[str(i)] == scene['query'] for i, scene in enumerate(plan)):
                raise ValueError('Groq visual plan did not repair the rejected query') from error
            plan = [{**scene, 'query': revised[str(i)]} for i, scene in enumerate(plan)]
