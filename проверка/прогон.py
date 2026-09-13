"""Прогон набора случаев: что находится, что теряется, что лишнее.

Запускать после каждой правки проверки. Ошибки в этом деле парные: почти
любое ужесточение выбрасывает вместе с мусором и настоящую находку, а любое
послабление тащит за собой ложные. Видно это только на двух наборах сразу.

    ./.venv/bin/python проверка/прогон.py [быстро]
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check  # noqa: E402
import law  # noqa: E402

MODELS = {"точно": "mlx-community/Qwen3-30B-A3B-4bit",
          "быстро": "mlx-community/Qwen3-8B-4bit"}


def cases():
    # Свой набор, если он есть, проверяется вместо общего.
    файл = HERE / "свои-случаи.txt"
    if not файл.exists():
        файл = HERE / "случаи.txt"
    for line in файл.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        text, want = (x.strip() for x in line.rsplit("|", 1))
        yield text, ([] if want == "чисто"
                     else [x.strip() for x in want.split(";")])


def name(law_id):
    item = law.BY_ID[law_id]
    return f'{item["act"]} {item["article"]}'


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "точно"
    checker = check.Checker(MODELS[mode])
    checker.load()
    checker._ask("разогрев")

    miss, extra, spent = [], [], 0.0
    good = bad = 0
    for text, want in cases():
        start = time.time()
        found = {name(f["law"]) for f in checker.check(text, text)}
        spent += time.time() - start
        if want:
            good += 1
            if not found & set(want):
                miss.append((text, want, sorted(found)))
        else:
            bad += 1
            if found:
                extra.append((text, sorted(found)))

    print(f"нарушающих: {good - len(miss)} из {good}")
    print(f"чистых:     {bad - len(extra)} из {bad}")
    print(f"время:      {spent / (good + bad):.2f} с на абзац\n")
    for text, want, found in miss:
        print(f"  пропущено: {text[:60]}")
        print(f"             ждали {want}, нашлось {found or '—'}")
    for text, found in extra:
        print(f"  лишнее:    {text[:60]}")
        print(f"             нашлось {found}")
    return 1 if miss or extra else 0


if __name__ == "__main__":
    sys.exit(main())
