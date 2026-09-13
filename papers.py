"""Чтение и запись документов: txt, markdown, rtf, docx, odt, pdf.

Текст правится в редакторе как разметка, поэтому от формата нужно одно:
достать абзацы и положить их обратно. Для docx и odt это делается прямо в их
разметке, чтобы у файла сохранилось всё остальное — стили, колонтитулы,
картинки. Если абзацев стало больше или меньше, лишние удаляются, новые
клонируются из соседнего.
"""
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT = {".txt", ".md", ".markdown", ".text", ""}
READ_ONLY = {".pdf"}
KNOWN = TEXT | {".rtf", ".docx", ".odt", ".pdf"}

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ODT_NS = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
          "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0"}


def suffixes(read=True):
    return sorted(KNOWN if read else KNOWN - READ_ONLY)


def read(path):
    """Текст документа. Что не разобрали — читаем как обычный текст."""
    path = Path(path)
    kind = path.suffix.lower()
    if kind == ".docx":
        return _docx_read(path)
    if kind == ".odt":
        return _odt_read(path)
    if kind == ".rtf":
        return _rtf_read(path)
    if kind == ".pdf":
        return _pdf_read(path)
    return path.read_text(encoding="utf-8", errors="replace")


def write(path, text):
    """Записать текст, сохранив всё остальное в исходном файле."""
    path = Path(path)
    kind = path.suffix.lower()
    if kind == ".docx":
        return _docx_write(path, text)
    if kind == ".odt":
        return _odt_write(path, text)
    if kind == ".rtf":
        return path.write_text(_rtf_make(text), encoding="utf-8")
    path.write_text(text, encoding="utf-8")


# ── docx

def _docx_paragraphs(root):
    body = root.find(f"{{{W}}}body")
    return [p for p in body.iter(f"{{{W}}}p")] if body is not None else []


def _docx_text(p):
    return "".join(t.text or "" for t in p.iter(f"{{{W}}}t"))


def _docx_read(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return "\n\n".join(_docx_text(p) for p in _docx_paragraphs(root))


def _docx_set(p, text):
    """Положить текст в абзац, оставив его оформление."""
    runs = list(p.iter(f"{{{W}}}r"))
    if not runs:
        run = ET.SubElement(p, f"{{{W}}}r")
        node = ET.SubElement(run, f"{{{W}}}t")
        runs = [run]
    else:
        node = runs[0].find(f"{{{W}}}t")
        if node is None:
            node = ET.SubElement(runs[0], f"{{{W}}}t")
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for extra in runs[1:]:
        p.remove(extra)


def _paragraphs(text):
    """Абзацы: их разделяет пустая строка, перенос внутри абзаца — пробел."""
    return [re.sub(r"\s*\n\s*", " ", part).strip()
            for part in re.split(r"\n\s*\n", text.strip())] or [""]


# Пустые заготовки: сохранить в docx или odt можно и новый документ, а не
# только открытый. Раньше запись лезла в исходный файл за его же частями и
# падала на «такого файла нет».
BLANK_DOCX = {
    "[Content_Types].xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>',
    "_rels/.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>',
    "word/_rels/document.xml.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    "word/document.xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t></w:t></w:r></w:p>'
        '</w:body></w:document>',
}

BLANK_ODT = {
    "mimetype": "application/vnd.oasis.opendocument.text",
    "META-INF/manifest.xml":
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
        '</manifest:manifest>',
    "styles.xml":
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:version="1.2"/>',
    "content.xml":
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'office:version="1.2"><office:body><office:text>'
        '<text:p></text:p></office:text></office:body></office:document-content>',
}


def _blank(path, parts):
    """Положить на место пустую заготовку нужного вида."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in parts.items():
            z.writestr(name, body,
                       zipfile.ZIP_STORED if name == "mimetype"
                       else zipfile.ZIP_DEFLATED)


def _docx_write(path, text):
    paragraphs = _paragraphs(text)
    if not path.exists():
        _blank(path, BLANK_DOCX)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    ET.register_namespace("w", W)
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{{{W}}}body")
    old = _docx_paragraphs(root)
    sample = old[-1] if old else None
    for n, line in enumerate(paragraphs):
        if n < len(old):
            _docx_set(old[n], line)
        else:
            fresh = ET.fromstring(ET.tostring(sample)) if sample is not None \
                else ET.SubElement(body, f"{{{W}}}p")
            _docx_set(fresh, line)
            body.insert(list(body).index(old[-1]) + 1 + (n - len(old))
                        if old else len(list(body)), fresh)
    for extra in old[len(paragraphs):]:
        for parent in body.iter():
            if extra in list(parent):
                parent.remove(extra)
                break
    parts["word/document.xml"] = ET.tostring(root, encoding="utf-8",
                                             xml_declaration=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            # mimetype в odt обязан лежать без сжатия, иначе строгие читалки
            # файл не признают.
            z.writestr(name, parts[name],
                       zipfile.ZIP_STORED if name == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    shutil.move(tmp, path)


# ── odt

def _odt_read(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    out = []
    for p in root.iter():
        if p.tag in (f'{{{ODT_NS["text"]}}}p', f'{{{ODT_NS["text"]}}}h'):
            out.append("".join(p.itertext()))
    return "\n\n".join(out)


def _odt_write(path, text):
    lines = _paragraphs(text)
    if not path.exists():
        _blank(path, BLANK_ODT)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    for prefix, uri in ODT_NS.items():
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(parts["content.xml"])
    tags = (f'{{{ODT_NS["text"]}}}p', f'{{{ODT_NS["text"]}}}h')
    holders = [(parent, node) for parent in root.iter()
               for node in list(parent) if node.tag in tags]
    for n, (parent, node) in enumerate(holders):
        if n < len(lines):
            for child in list(node):
                node.remove(child)
            node.text = lines[n]
        else:
            parent.remove(node)
    if holders and len(lines) > len(holders):
        parent, sample = holders[-1]
        at = list(parent).index(sample)
        for n, line in enumerate(lines[len(holders):], 1):
            fresh = ET.fromstring(ET.tostring(sample))
            for child in list(fresh):
                fresh.remove(child)
            fresh.text = line
            parent.insert(at + n, fresh)
    parts["content.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            # mimetype в odt обязан лежать без сжатия, иначе строгие читалки
            # файл не признают.
            z.writestr(name, parts[name],
                       zipfile.ZIP_STORED if name == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    shutil.move(tmp, path)


# ── rtf

RTF_ESC = re.compile(r"\\'([0-9a-fA-F]{2})")
RTF_UNI = re.compile(r"\\u(-?\d+)\s?\??")
RTF_WORD = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?")


# Служебные группы RTF: таблицы шрифтов и цветов, сведения о файле. Их
# содержимое не текст, но выглядит как текст — «Helvetica-Light;» в начале
# каждого открытого документа.
RTF_SKIP = re.compile(r"\\(?:\*|fonttbl|colortbl|stylesheet|info|pntext|"
                      r"listtable|listoverridetable|generator|themedata|"
                      r"datastore|xmlnstbl|rsidtbl)")


def _rtf_body(raw):
    """Убрать служебные группы, считая фигурные скобки."""
    out, at, depth, skip = [], 0, 0, []
    while at < len(raw):
        ch = raw[at]
        if ch == "\\" and at + 1 < len(raw):
            if raw[at + 1] in "\r\n":
                # «\» перед переносом строки — это конец абзаца.
                if not skip:
                    out.append("\\par ")
                at += 2
                continue
            if not skip:
                out.append(raw[at:at + 2])
            at += 2
            continue
        if ch == "{":
            depth += 1
            if not skip and RTF_SKIP.match(raw, at + 1):
                skip.append(depth)
        elif ch == "}":
            if skip and skip[-1] == depth:
                skip.pop()
            depth -= 1
        elif ch in "\r\n":
            pass                 # в RTF перенос строки — только оформление
        elif not skip:
            out.append(ch)
        at += 1
    return "".join(out)


def _rtf_read(path):
    body = _rtf_body(path.read_text(encoding="cp1251", errors="replace"))
    body = RTF_UNI.sub(lambda m: chr(int(m.group(1)) % 65536), body)
    body = RTF_ESC.sub(lambda m: bytes([int(m.group(1), 16)]).decode("cp1251",
                                                                    "replace"), body)
    body = RTF_WORD.sub(lambda m: "\n" if m.group(1) in ("par", "line") else "", body)
    # Одиночная косая черта экранирует скобку или саму себя.
    body = (body.replace("\\\\", "\x00").replace("\\{", "{")
                .replace("\\}", "}").replace("\x00", "\\"))
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _rtf_make(text):
    out = []
    for ch in text:
        if ch == "\n":
            out.append("\\par\n")
        elif ord(ch) < 128:
            out.append("\\\\" if ch == "\\" else
                       "\\{" if ch == "{" else "\\}" if ch == "}" else ch)
        else:
            out.append(f"\\u{ord(ch)}?")
    return "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Helvetica;}}\\f0\\fs24 " \
           + "".join(out) + "}"


# ── pdf: только чтение, через системный разбор

def _pdf_read(path):
    from Foundation import NSURL
    from Quartz import PDFDocument
    doc = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(str(path)))
    if doc is None:
        raise ValueError("не удалось открыть PDF")
    return (doc.string() or "").strip()
