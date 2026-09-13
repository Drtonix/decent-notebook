"""Прогон замен: модель переписывает найденные места, абзац проверяется снова.

Поиск меряет прогон.py; здесь — то, что видно при «Исправить всё»: сколько
мест модель смогла переписать сама, сколько раз пришлось брать заготовку и
остался ли абзац чистым после замены.

    ./.venv/bin/python проверка/замены.py репозиторий-модели
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check  # noqa: E402
import law  # noqa: E402
from прогон import cases  # noqa: E402


def main():
    checker = check.Checker(sys.argv[1])
    checker.check("разогрев")         # загрузка и разогрев — на потоке модели
    fallbacks = set(law.SAFE.values()) | {"Ценю крепкую семью и созидательный труд"}
    total = own = clean_after = 0
    spent = 0.0
    samples = []
    for text, want in cases():
        if not want:
            continue
        start = time.time()
        found = checker.check(text, text)
        fixed = text
        for f in found:
            quote = f.get("quote") or text[f["start"]:f["end"]]
            said = checker.rewrite(quote, f["law"], text)
            total += 1
            if said not in fallbacks and not law.BY_ID[f["law"]].get("place") == "top":
                own += 1
            if quote in fixed:
                fixed = fixed.replace(quote, said, 1)
            if len(samples) < 12:
                samples.append((quote[:70], said[:90]))
        if found and not checker.check(fixed, fixed):
            clean_after += 1
        spent += time.time() - start
    print(f"мест: {total}, переписано моделью: {own}, "
          f"абзацев чистых после замены: {clean_after} из 88, "
          f"{spent:.0f} с всего")
    for q, s in samples:
        print(f"  «{q}» → «{s}»")


if __name__ == "__main__":
    main()
