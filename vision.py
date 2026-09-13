"""Распознавание текста на картинке средствами самой macOS.

Ничего не качается и никуда не уходит: Vision разбирает изображение на месте.
Русский, украинский и английский включены сразу — текст на картинке бывает
любым, а выбирать язык руками человеку незачем.
"""
from pathlib import Path

LANGS = ["ru-RU", "en-US", "uk-UA"]


def read_image(path):
    """Строки текста с картинки, сверху вниз."""
    import Vision
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(Path(path)))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(0)          # 0 — точно, 1 — быстро
    request.setUsesLanguageCorrection_(True)
    known, _err = request.supportedRecognitionLanguagesAndReturnError_(None)
    known = {str(x) for x in (known or [])}
    request.setRecognitionLanguages_([x for x in LANGS if x in known] or ["en-US"])
    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(str(err.localizedDescription()) if err else "не вышло")

    rows = []
    for found in request.results() or []:
        best = found.topCandidates_(1)
        if not best:
            continue
        box = found.boundingBox()
        rows.append((round(1 - box.origin.y, 3), box.origin.x, best[0].string()))
    rows.sort()
    return _join([r[2] for r in rows])


def _join(rows):
    """Склеить строки в абзацы: перенос посреди предложения — не новый абзац."""
    out = []
    for row in rows:
        row = row.strip()
        if not row:
            continue
        if out and not out[-1].endswith((".", "!", "?", ":", ";")) \
                and row[:1].islower():
            out[-1] += " " + row
        else:
            out.append(row)
    return "\n\n".join(out)
