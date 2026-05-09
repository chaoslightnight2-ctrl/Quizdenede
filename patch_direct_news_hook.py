from pathlib import Path

p = Path("main.py")
s = p.read_text(encoding="utf-8")

old_generic = "Dünya gündeminde dikkat çeken bir gelişme var. {item['title']}. "
new_generic = "{item['title']}. "
s = s.replace(old_generic, new_generic)

old_prompt_line = "- İlk cümle dikkat çekici olsun."
new_prompt_line = "- İlk cümle haberin kendi konusuyla ilgili çok güçlü, merak uyandıran bir hook/clickbait başlık gibi olsun. 'Dünya gündeminde', 'dikkat çeken gelişme', 'son dakika' gibi jenerik kalıplarla başlama."
s = s.replace(old_prompt_line, new_prompt_line)

old_prompt_line_2 = "- Haberin dünya/uluslararası önemini kısa ve anlaşılır anlat."
new_prompt_line_2 = "- İlk cümleden sonra haberi net ve kısa şekilde anlat; sonra dünya/uluslararası önemini kısa ve anlaşılır açıkla."
s = s.replace(old_prompt_line_2, new_prompt_line_2)

old_fallback = "Bu başlık uluslararası gündemde daha da konuşulabilir. Gelişmeler için takipte kal."
new_fallback = "Bu gelişmenin etkileri büyüyebilir. Devamı için takipte kal."
s = s.replace(old_fallback, new_fallback)

p.write_text(s, encoding="utf-8")
print("Direct news hook prompt applied")
