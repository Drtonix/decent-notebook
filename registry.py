"""Реестры Минюста: иноагенты, нежелательные и запрещённые организации.

Упоминать их закон не запрещает — он требует указания рядом с упоминанием, и
формулировка у каждого реестра своя. Поэтому реестры хранятся списком имён, а
находка несёт готовый текст указания.

Списки живут в папке приложения и обновляются кнопкой: состав меняется каждую
неделю, и вшивать его в программу бессмысленно.
"""
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

try:
    # Доверяем связке ключей macOS, а не собственному списку Python: за
    # корпоративным или системным прокси соединение подписано его сертификатом,
    # и обычная проверка обрывается на «unable to get local issuer certificate».
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
# Росфинмониторинг подписан «Russian Trusted Root CA» — этого корня нет ни в
# macOS, ни в Python. Держим его рядом с программой и доверяем только ему и
# только для этого адреса: отключать проверку ради одного сайта нельзя.
RU_CA = HERE / "certs" / "russian-trusted-ca.pem"

STORE = Path.home() / "Library" / "Application Support" / "decent-notepad"
FILE = STORE / "registries.json"
# Приложение раньше называлось иначе; списки уже скачаны — переносим, а не
# заставляем качать заново.
WAS = Path.home() / "Library" / "Application Support" / "SFWedit" / "registries.json"

API = "https://reestrs.minjust.gov.ru/rest/registry/{id}/values"
PAGE = 500

SOURCES = [
    {"key": "foreign", "law": "fz-255",
     "id": "39b95df9-9a68-6b6d-e1e3-e6388507067e",
     "name": "field_2_s", "kind": "field_7_s",
     "title": {"ru": "Иностранные агенты", "en": "Foreign agents"},
     "where": "top",
     "mark": {
         "ru": "НАСТОЯЩИЙ МАТЕРИАЛ (ИНФОРМАЦИЯ) КАСАЕТСЯ ДЕЯТЕЛЬНОСТИ "
               "ИНОСТРАННОГО АГЕНТА {name}",
         "en": "THIS MATERIAL CONCERNS THE ACTIVITY OF FOREIGN AGENT {name}"}},
    {"key": "undesirable", "law": "fz-272",
     "id": "c2d1692e-a9f6-5a79-13ee-5da5b42980df",
     "name": "field_5_s", "kind": None,
     "title": {"ru": "Нежелательные организации", "en": "Undesirable organisations"},
     "where": "after",
     "mark": {
         "ru": "деятельность организации признана нежелательной на территории "
               "Российской Федерации",
         "en": "the organisation is designated undesirable in the Russian Federation"}},
    {"key": "banned", "law": "fz-114",
     "id": "59961ebb-9f0e-d885-7ebc-b90399923b03",
     "name": "field_2_s", "kind": None,
     "title": {"ru": "Запрещённые организации", "en": "Banned organisations"},
     "where": "after",
     "mark": {
         "ru": "организация запрещена на территории Российской Федерации",
         "en": "the organisation is banned in the Russian Federation"}},
    {"key": "terror", "law": "fz-114", "law_person": "fz-115",
     "kind": None, "cert": True,
     "url": "https://www.fedsfm.ru/documents/terrorists-catalog-portal-act",
     "title": {"ru": "Террористические и экстремистские",
               "en": "Terrorist and extremist"},
     "where": "after",
     "mark": {
         "ru": "организация признана террористической и запрещена на территории "
               "Российской Федерации",
         "en": "the organisation is designated terrorist and banned in Russia"},
     "mark_person": {
         "ru": "{name} включён в перечень лиц, причастных к экстремистской "
               "деятельности или терроризму",
         "en": "{name} is on the list of persons involved in extremism or terrorism"}},
]
BY_KEY = {s["key"]: s for s in SOURCES}

# Перечень Росфинмониторинга — не выгрузка, а страница: организации идут
# сплошной нумерацией, а следом физические лица, у которых стоит дата рождения.
# Людей не берём: их упоминание закон не ограничивает.
ROW = re.compile(r"^\d+\.\s+(.+?)\s*[,;]\s*[,;]?\s*$")
BORN = re.compile(r"\d{2}\.\d{2}\.\d{4}\s*г\.р\.")
PERSON_ROW = re.compile(r"^\d+\.\s+([^,;]+?)\s*\*?\s*,\s*\d{2}\.\d{2}\.\d{4}")

# Что выкидываем из названия организации: правовая форма к делу не относится,
# а по слову «Межрегиональная» совпадёт половина текстов.
FORMS = re.compile(
    r"^(?:межрегиональн\w+|международн\w+|общероссийск\w+|региональн\w+|"
    r"общественн\w+|религиозн\w+|некоммерческ\w+|автономн\w+|"
    r"неправительственн\w+|организация|объединение|движение|фонд|"
    r"организации|группа|партия|ассоциация|центр)\s+", re.I)
QUOTED = re.compile(r"[«\"]([^»\"]{3,80})[»\"]")
PARENS = re.compile(r"\(([^)]{3,120})\)")
ACRO = re.compile(r"\b[А-ЯЁA-Z]{3,10}\b")


def _fetch(source, log=lambda _s: None):
    rows, offset = [], 0
    while True:
        body = json.dumps({"offset": offset, "limit": PAGE,
                           "facets": {}, "sort": []}).encode()
        req = urllib.request.Request(
            API.format(id=source["id"]), data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        got = data.get("values") or []
        rows += got
        offset += len(got)
        log(f"{source['title']['ru']}: {offset} из {data.get('size', '?')}")
        if not got or offset >= data.get("size", 0):
            return rows


def _fetch_page(source, log=lambda _s: None):
    req = urllib.request.Request(source["url"],
                                 headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context(cafile=str(RU_CA)) if source.get("cert") else None
    with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
        page = r.read().decode("utf-8", "replace")
    page = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", page)
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if BORN.search(line):
            m = PERSON_ROW.match(line)
            if m:
                out.append({source_name: m.group(1).replace("*", "").strip(),
                            "person": True})
            continue
        m = ROW.match(line)
        if m:
            out.append({source_name: m.group(1).replace("*", "").strip()})
    log(f"{source['title']['ru']}: {len(out)}")
    return out


source_name = "name"


def update(log=lambda _s: None):
    """Скачивает все три реестра и складывает рядом с настройками."""
    out = {"updated": time.time(), "lists": {}}
    for source in SOURCES:
        names = []
        rows = (_fetch_page(source, log) if source.get("url")
                else _fetch(source, log))
        for row in rows:
            name = (row.get(source.get("name", "name")) or "").strip()
            if not name:
                continue
            kind = (row.get(source["kind"]) or "") if source.get("kind") else ""
            names.append({"name": name,
                          "person": bool(row.get("person"))
                                    or kind.startswith("Физическ")})
        out["lists"][source["key"]] = names
    STORE.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    _cache.clear()
    return out


_cache = {}


def load():
    if "data" not in _cache:
        if not FILE.exists() and WAS.exists():
            STORE.mkdir(parents=True, exist_ok=True)
            WAS.replace(FILE)
        try:
            _cache["data"] = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache["data"] = {"updated": 0, "lists": {}}
        _cache["rx"], _cache["people"] = _compile(_cache["data"])
    return _cache["data"]


def updated():
    return load().get("updated", 0)


def counts():
    return {k: len(v) for k, v in load().get("lists", {}).items()}


# Слова, по которым организацию не опознать: правовая форма, город, номера.
NOISE = re.compile(
    r"\b(?:местн\w+|региональн\w+|межрегиональн\w+|международн\w+|общероссийск\w+|"
    r"общественн\w+|религиозн\w+|некоммерческ\w+|автономн\w+|неправительственн\w+|"
    r"организаци\w+|объединени\w+|движени\w+|группа|партия|ассоциаци\w+|"
    r"учреждени\w+|г|город\w*|области|край|республик\w+|ОГРН\s*\d+|"
    r"и\s+входящие[^,]*)\b\.?", re.I)


def _significant(name):
    """Что остаётся от названия, когда убрать форму, город и номера."""
    core = NOISE.sub(" ", name)
    core = re.sub(r"[(),.]|«|»|\"", " ", core)
    return [w for w in core.split() if len(w) > 2]


def _stem(word):
    """Слово с отрезанным окончанием: в тексте «Ковалёва» и «Фонда», а в
    реестре «Ковалёв» и «Фонд» — по точному написанию не совпадёт ничего.

    У прилагательных меняется не только хвост: «Новая» и «Новую» сходятся
    только на «Нов», поэтому от пяти букв режем две.
    """
    cut = 2 if len(word) >= 5 else 1 if len(word) > 3 else 0
    body = re.escape(word[:len(word) - cut] if cut else word)
    return body + (r"\w{0,4}" if cut else r"\w{0,2}")


# Латиница в псевдониме пишется по-русски как придётся: «Sample MC» ищут как
# «Сэмпл МС». Переводим побуквенно, а окончание добирает _stem.
PAIRS = (("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"),
         ("ts", "ц"), ("yu", "ю"), ("ya", "я"), ("yo", "ё"), ("ye", "е"),
         ("ee", "и"), ("oo", "у"), ("ou", "у"), ("ai", "ай"), ("ei", "ей"),
         ("oi", "ой"), ("ui", "уй"), ("iy", "ий"), ("ay", "ай"), ("ey", "ей"),
         ("oy", "ой"), ("j", "дж"))
ONE = dict(zip("abcdefghiklmnopqrstuvwxyz",
               ("а", "б", "к", "д", "е", "ф", "г", "х", "и", "к", "л", "м",
                "н", "о", "п", "к", "р", "с", "т", "у", "в", "в", "кс", "й",
                "з")))
# Сокращение из заглавных читают по буквам: MC — это «МС», а не «мк».
CAPS = {"A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
        "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У", "N": "Н", "S": "С",
        "D": "Д", "F": "Ф", "G": "Г", "I": "И", "L": "Л", "R": "Р", "U": "У",
        "V": "В", "Z": "З", "J": "Дж", "Q": "К", "W": "В"}


def _russify(word):
    """Как это слово напишут кириллицей."""
    if word.isupper() and len(word) <= 4:
        return "".join(CAPS.get(c, c) for c in word)
    low, out = word.lower(), ""
    at = 0
    while at < len(low):
        for a, b in PAIRS:
            if low.startswith(a, at):
                out += b
                at += len(a)
                break
        else:
            out += ONE.get(low[at], low[at])
            at += 1
    return out


def _alias_pattern(alias):
    """Псевдоним в кавычках: и как написан, и как его пишут по-русски."""
    words = [w for w in re.split(r"[\s\-]+", alias) if len(w) > 1]
    if not words or sum(len(w) for w in words) < 5:
        return None
    if len(words) == 1 and len(words[0]) < 7:
        return None
    out = []
    for word in words:
        forms = {word}
        # Псевдоним из одного слова по-русски не пишем: «Drugoi» превращался
        # в «друг» и помечал «уважайте друг друга». Два слова подряд —
        # совпадение уже не случайное.
        if word.isascii() and len(words) > 1:
            forms.add(_russify(word))
        if len(words) == 1:
            # Одно слово режем осторожнее: «Кроткий» с обычным срезом давал
            # «Крот\w{0,4}» и ловил слово «круто».
            out.append("(?:" + "|".join(re.escape(f[:-1]) + r"\w{0,2}"
                                        for f in sorted(forms)) + ")")
        else:
            out.append("(?:" + "|".join(_stem(f) for f in sorted(forms)) + ")")
    return r"\s+".join(out)


def _person_pattern(full):
    """Фамилия рядом с именем в любом порядке, имя допускается инициалом.

    По одной фамилии искать нельзя: в реестре есть и Петров, и Иванов, и текст
    про однофамильца получил бы чужую метку.
    """
    parts = [p for p in re.split(r"\s+", full) if len(p) > 1]
    if len(parts) < 2:
        return None
    last, first = _stem(parts[0]), _stem(parts[1][:4])
    near = r"[^\w]{1,3}"
    return rf"\b(?:{last}{near}{first}|{first}{near}{last})\b"


def _proper(word):
    """Одно слово ищем только с большой буквы: «Талибан» — организация, а
    «власть» и «себя» — обычные слова, которые иначе совпали бы с названиями
    из одного слова и с сокращениями.

    Срез здесь осторожнее обычного: «ИНТЕРРА» с обычным давала «ИНТЕР\\w{0,4}»
    и ловила слово «Интересно».
    """
    forms = {word.upper(), word.capitalize()}
    return "(?-i:" + "|".join(re.escape(f[:-1]) + r"\w{0,2}"
                              for f in sorted(forms)) + ")"


# Сокращения, которые в обычном тексте значат совсем другое. Среди
# запрещённых организаций попадаются названия, чьи первые буквы складываются
# в «СССР» или «США», и по ним подсвечивался бы любой исторический текст.
COMMON = {"СССР", "США", "ООН", "ВОЗ", "МВД", "ФСБ", "СМИ", "РФ", "ЕС", "НАТО",
          "ГОСТ", "ВУЗ", "ЖКХ", "МЧС", "РЖД", "ЦБ", "ТАСС", "МГУ", "СПБ",
          "ФБР", "ЦРУ", "ВВС", "ВОВ", "СНГ", "ПДД", "ГИБДД", "ЗАГС",
          # Названия в реестре часто набраны заглавными целиком, и обычные
          # слова из них попадали в сокращения: по «THE» помечалось «THE NEWS»
          # как нежелательная организация.
          "THE", "AND", "FOR", "NEW", "OUR", "ALL", "WWW", "COM", "ORG", "NET",
          "INC", "LLC", "LTD", "GMBH", "USA", "UK", "EU", "NGO", "FOUNDATION",
          "CENTER", "CENTRE", "INTERNATIONAL", "NATIONAL", "PUBLIC", "HUMAN",
          "RIGHTS", "FUND", "GROUP", "PROJECT", "NEWS", "MEDIA", "PRESS",
          "INSTITUTE", "UNION", "COUNCIL", "ASSOCIATION", "SOCIETY",
          "И", "ИЛИ", "ОРГАНИЗАЦИЯ", "ДВИЖЕНИЕ", "ФОНД", "ЦЕНТР", "СОЮЗ",
          # ЛГБТ помечается своей статьёй, а как сокращение попадало в
          # случайные региональные организации.
          "ЛГБТ", "LGBT"}


def _acronym(words):
    """Сокращение по первым буквам: люди пишут «ФБК», а не «Фонд борьбы с
    коррупцией». Берём только от трёх слов и ищем строго заглавными, иначе
    трёхбуквенное сочетание совпадёт со случайным словом."""
    if len(words) < 3:
        return None
    short = "".join(w[0] for w in words[:5]).upper()
    if len(short) < 3 or short in COMMON:
        return None
    return rf"\b{re.escape(short)}\b"


# Слова, по которым организация не узнаётся: они стоят в половине названий и
# совпадают с обычной речью. «Фонд поддержки», «Институт развития», «права
# человека» помечали новости, устав клуба и цитату из Конституции.
GENERIC = (
    "фонд", "институт", "центр", "движени", "союз", "парти", "организаци",
    "комитет", "ассоциаци", "объединени", "обществ", "группа", "совет",
    "корпораци", "агентств", "альянс", "коалиц", "форум", "клуб", "школ",
    "академ", "университет", "сеть", "служб", "прав", "человек", "гражданск",
    "народн", "национальн", "международн", "российск", "общероссийск",
    "поддержк", "развити", "свобод", "информац", "инициатив", "проект",
    "программ", "помощ", "защит", "здоров", "образован", "будущ", "семь",
    "молодёж", "молодеж", "культур", "истор", "памят", "мир", "дом", "новост",
    "медиа", "пресс", "газет", "журнал", "исследован", "иссл", "наук",
)


# Страны, города и стороны света: они стоят в названиях сотнями, и по ним
# подсветился бы любой текст. Слово из названия само по себе ищется, только
# если оно не из этого списка и не из GENERIC.
PLACES = (
    "росси", "российск", "русск", "украин", "америк", "европ", "азиатск",
    "москв", "петербург", "крым", "кавказ", "сибир", "беларус", "белорус",
    "казахст", "грузи", "армени", "азербайдж", "молдов", "латви", "литв",
    "эстон", "польш", "герман", "франц", "англи", "британ", "турец", "турци",
    "китай", "япон", "корейск", "ислам", "христиан", "православн", "иудейск",
    "северн", "южн", "западн", "восточн", "центральн", "мирово", "всемирн",
    # Города: у местных отделений они стоят в кавычках как название.
    "калининград", "новосибирск", "екатеринбург", "челябинск", "самар",
    "казан", "ростов", "воронеж", "волгоград", "краснодар", "саратов",
    "тюмен", "тольятти", "ижевск", "барнаул", "ульяновск", "иркутск",
    "хабаровск", "ярославл", "владивосток", "махачкал", "томск", "оренбург",
    "кемеров", "рязан", "астрахан", "пенз", "липецк", "тул", "киров",
    "чебоксар", "калуг", "брянск", "курск", "иванов", "магнитогорск", "тверь",
    "ставропол", "белгород", "сочи", "архангельск", "владимир", "чит",
    "грозн", "смоленск", "саранск", "якутск", "орёл", "орел", "ухт", "серов",
    "череповец", "вологд", "мурманск", "тамбов", "стерлитамак", "костром",
    "петрозаводск", "нижневартовск", "новороссийск", "йошкар", "таганрог",
    "комсомольск", "сыктывкар", "нальчик", "шахт", "дзержинск", "братск",
    "энгельс", "ангарск", "благовещенск", "псков", "бийск", "прокопьевск",
    "рыбинск", "балаков", "северодвинск", "армавир", "абакан", "норильск",
)


def _telling(words):
    """Есть ли среди слов такое, по которому название вообще узнаётся."""
    return any(not w.lower().startswith(GENERIC) for w in words)


def _org_pattern(full):
    """Название целиком без правовой формы, плюс заметный псевдоним.

    Кавычки без разбора брать нельзя: в списке запрещённых сотни местных
    организаций, у которых в кавычках стоит название города — «Орел», «Ухта»,
    «Серов». По ним подсветился бы любой текст про эти города.
    """
    out = []
    words = _significant(full)
    quoted = [a.strip() for a in QUOTED.findall(full)]
    core = _significant(quoted[0]) if quoted else words
    # Название из двух общих слов — «Права человека», «Фонд поддержки» — ищем
    # только целиком; из трёх и больше оно уже своё.
    if len(core) >= 2 and (len(core) > 2 or _telling(core)):
        out.append(r"\s+(?:\w{1,3}\s+)?".join(_stem(w) for w in core[:6]))
        acro = _acronym(core)
        if acro:
            out.append(f"(?-i:{acro})")
    # В скобках у террористических организаций стоят их же названия и
    # сокращения — «ИСЛАМСКОЕ ГОСУДАРСТВО (ИГИЛ; ДАИШ)». Люди пишут именно их.
    aliases = [(a, True) for a in quoted]
    for chunk in PARENS.findall(full):
        # Если в скобках стоит название в кавычках, запятые внутри него — часть
        # названия, а не разделитель псевдонимов: «Евразийская коалиция по
        # здоровью, правам, ...» распадалась на «правам», и по нему помечалось
        # слово «Правила» в любом тексте.
        inner = [x.strip() for x in QUOTED.findall(chunk)]
        aliases += [(x, bool(inner)) for x in
                    (inner or [y.strip() for y in re.split(r"[;,]", chunk) if y.strip()])]
    for alias, named in aliases:
        parts = _significant(alias)
        if len(parts) >= 2 and (len(parts) > 2 or _telling(parts)):
            out.append(r"\s+".join(_stem(w) for w in parts[:6]))
            # Первые два слова — то, как называют в тексте: «Хизб ут-Тахрир»
            # вместо «Хизб ут-Тахрир аль-Ислами».
            if len(parts) > 2 and len(parts[0]) >= 4 and _telling(parts[:2]):
                out.append(r"\s+".join(_stem(w) for w in parts[:2]))
            # Сокращение по первым буквам полного названия: «Исламское
            # государство Ирака и Леванта» — это и есть ИГИЛ.
            acro = _acronym(parts)
            if acro:
                out.append(f"(?-i:{acro})")
        elif (named and parts and len(parts[0]) >= 6 and parts[0][:1].isupper()
              and _telling(parts[:1])
              and not parts[0].lower().startswith(PLACES)):
            out.append(_proper(parts[0]))
        if (named and len(parts) == 2 and not _telling(parts[:1])
                and len(parts[1]) >= 6 and parts[1][:1].isupper()
                and _telling(parts[1:])
                and _key(parts[1]) not in _cache.get("surnames", ())
                and not parts[1].lower().startswith(PLACES)):
            # «Проект Заря», «Фонд Память»: первое слово родовое, второе и
            # есть имя — им организацию и называют.
            out.append(_proper(parts[1]))
        for short in ACRO.findall(alias):
            # В скобках у нежелательных организаций стоит страна — «(США)»,
            # и по ней подсветился бы любой текст про Америку.
            if len(short) >= 3 and short not in COMMON:
                out.append(rf"(?-i:\b{re.escape(short)}\b)")
    # Название из одного заметного слова — «ТАЛИБАН», «ХАМАС»: короче шести
    # букв не берём, иначе совпадёт обычное слово. Города тоже не берём: у
    # местных отделений в кавычках стоит название города, и по «Калининграду»
    # помечался текст про музей.
    if (len(core) == 1 and len(core[0]) >= 6 and _telling(core)
            and not core[0].lower().startswith(PLACES)):
        out.append(_proper(core[0]))
    if not out and len(full.strip()) >= 8:
        out.append(re.escape(full.strip()).replace(r"\ ", r"\s+"))
    return "|".join(dict.fromkeys(out)) or None


# Падежные окончания. «ов»/«ев» не трогаем: это часть фамилии, без них
# «Иванов» и «Иванова» разъезжаются в разные стороны.
ENDING = re.compile(r"(?:ого|его|ому|ему|ыми|ими|ая|яя|ое|ее|ый|ий|ой|ую|юю|"
                    r"ые|ие|ей|ям|ах|ях|ом|ем|им|ым|а|я|у|ю|е|и|ы|о|ь|й)$")


def _key(word):
    """Ключ слова без окончания: «Ковалёвский», «Ковалёвского» и «ковалёвским»
    сходятся в «ковалёвск», «Алексей» и «Алексея» — в «алекс».

    В конце обрезаем до четырёх букв: «Юрий» давал «юр», а «Юрию» — «юри»,
    и пара «Юрию Ковалю» не находила «Коваль Юрий Александрович».
    """
    # У коротких имён правило окончаний срезает слишком много: «Юрий» давало
    # «юр», а «Юрию» — «юри», и пара «Юрию Ковалю» не находила «Коваль Юрий
    # Александрович». Если после среза осталось меньше трёх букв, отрезаем
    # только последнюю.
    low = word.lower().replace("ё", "е")
    w = ENDING.sub("", low, count=1)
    if len(w) < 3 and len(low) > 3:
        w = low[:-1]
    while len(w) > 4 and w[-1] in "аеиоуыэюяйь":
        w = w[:-1]
    return w


WORD = re.compile(r"[А-Яа-яЁёA-Za-z][\w-]{2,}")


# Уменьшительные имена: в перечне «Коваль Юрий Александрович», а пишут «Юра
# Коваль». Список закрытый и общеизвестный — выводить их правилами бесполезно,
# они нерегулярны.
NICK = {
    "александр": ("саша", "саня", "шура"), "алексей": ("лёша", "леша", "алёша"),
    "анатолий": ("толя",), "андрей": ("андрюша",), "антон": ("тоша",),
    "борис": ("боря",), "вадим": ("вадик",), "валентин": ("валя",),
    "василий": ("вася",), "виктор": ("витя",), "владимир": ("вова", "володя"),
    "владислав": ("влад",), "вячеслав": ("слава",), "геннадий": ("гена",),
    "георгий": ("жора", "гоша"), "григорий": ("гриша",), "даниил": ("даня",),
    "дмитрий": ("дима", "митя"), "евгений": ("женя",), "иван": ("ваня",),
    "илья": ("илюша",), "кирилл": ("киря",), "константин": ("костя",),
    "лев": ("лёва",), "леонид": ("лёня",), "максим": ("макс",),
    "михаил": ("миша",), "николай": ("коля",), "олег": ("олежа",),
    "павел": ("паша",), "пётр": ("петя",), "петр": ("петя",),
    "роман": ("рома",), "руслан": ("русик",), "сергей": ("серёжа", "серёга"),
    "станислав": ("стас",), "степан": ("стёпа",), "тимофей": ("тима",),
    "фёдор": ("федя",), "федор": ("федя",), "эдуард": ("эдик",),
    "юрий": ("юра",), "яков": ("яша",),
    "анастасия": ("настя",), "анна": ("аня",), "валентина": ("валя",),
    "галина": ("галя",), "дарья": ("даша",), "екатерина": ("катя",),
    "елена": ("лена",), "ирина": ("ира",), "любовь": ("люба",),
    "людмила": ("люда",), "мария": ("маша",), "надежда": ("надя",),
    "наталья": ("наташа",), "наталия": ("наташа",), "ольга": ("оля",),
    "светлана": ("света",), "татьяна": ("таня",), "юлия": ("юля",),
}

# Фамилия без имени. В перечне иностранных агентов восемь сотен человек, и это
# публичные люди, и зовут их по фамилии. В
# перечне Росфинмониторинга двадцать две тысячи, и там по одной фамилии искать
# нечего: это не публичные люди, а однофамильцы находятся на каждое слово. Фамилия, которая совпадает с обычным словом, одна не
# ищется никогда: «Волков в лесу» и «Белый снег» иначе просят плашку.
ALONE = {"foreign": 4}


# Самые частые русские фамилии. Они ничего не говорят: «Петров и Сидоров
# пришли на собрание» — это не об иностранных агентах, хотя однофамильцы в
# перечне найдутся всегда. По одной такие фамилии не ищем.
PLAIN = {
    "иванов", "смирнов", "кузнецов", "попов", "васильев", "петров", "соколов",
    "михайлов", "новиков", "фёдоров", "федоров", "морозов", "волков",
    "алексеев", "лебедев", "семёнов", "семенов", "егоров", "павлов", "козлов",
    "степанов", "николаев", "орлов", "андреев", "макаров", "никитин",
    "захаров", "зайцев", "соловьёв", "соловьев", "борисов", "яковлев",
    "григорьев", "романов", "воробьёв", "воробьев", "сергеев", "кузьмин",
    "фролов", "александров", "дмитриев", "королёв", "королев", "гусев",
    "киселёв", "киселев", "ильин", "максимов", "поляков", "сорокин",
    "виноградов", "ковалёв", "ковалев", "белов", "медведев", "антонов",
    "тарасов", "жуков", "баранов", "филиппов", "комаров", "давыдов",
    "беляев", "герасимов", "богданов", "осипов", "сидоров", "матвеев",
    "титов", "марков", "миронов", "крылов", "куликов", "карпов", "власов",
    "мельников", "денисов", "гаврилов", "тихонов", "казаков", "афанасьев",
    "данилов", "савельев", "тимофеев", "фомин", "чернов", "абрамов",
    "мартынов", "ефимов", "федотов", "щербаков", "назаров", "калинин",
    "исаев", "чернышёв", "чернышев", "быков", "маслов", "родионов",
    "коновалов", "лазарев", "воронин", "климов", "филатов", "пономарёв",
    "пономарев", "голубев", "кудрявцев", "прохоров", "наумов", "потапов",
    "журавлёв", "журавлев", "овчинников", "трофимов", "леонов", "соболев",
    "ермаков", "колесников", "гончаров", "емельянов", "никифоров", "грачёв",
    "грачев", "котов", "гришин", "ефремов", "архипов", "громов", "кириллов",
    "малышев", "панов", "моисеев", "румянцев", "акимов", "кондратьев",
    "бирюков", "горбунов", "анисимов", "сазонов", "аксёнов", "аксенов",
    "коротков", "сафонов", "устинов", "миллер", "шмидт", "коваленко",
    "бондаренко", "ткаченко", "кравченко", "шевченко", "мельник", "бойко",
}


def _surname(word):
    """Фамилия с большой буквы во всех падежах.

    `_proper` режет одну букву, и «Ковалёвского» ей уже не поймать: у
    фамилий меняется не только последняя буква. Берём корень покороче, но
    только с большой буквы — иначе это ловило бы обычные слова.
    """
    long = len(word) >= 6
    root = word[:-2] if long else word[:-1]
    tail = r"\w{2,3}" if long else r"\w{1,2}"
    forms = {root.upper(), root.capitalize()}
    return "(?-i:" + "|".join(re.escape(f) + tail for f in sorted(forms)) + ")"


def _wordy(word):
    """Это обычное русское слово, а не только фамилия.

    Спрашиваем системную проверку орфографии — своего словаря у нас нет, а
    список фамилий надо как-то отделить от слов: «Волков» это ещё и волков,
    «Белый» — белый, а «Коваль» и «Ковалёвский» не значат ничего. Проверяем
    строчную форму: имена собственные с маленькой буквы словарь не признаёт.
    """
    known = _cache.setdefault("words", {})
    low = word.lower()
    if low not in known:
        check = _cache.get("speller", False)
        if check is False:
            try:
                from AppKit import NSSpellChecker
                from Foundation import NSNotFound
                speller = NSSpellChecker.sharedSpellChecker()
                tag = NSSpellChecker.uniqueSpellDocumentTag()

                def check(w):
                    where = speller.\
                        checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
                            w, 0, "ru", False, tag, None)[0]
                    return where.location == NSNotFound
            except Exception:
                check = None
            _cache["speller"] = check
        try:
            known[low] = bool(check(low)) if check else True
        except Exception:
            known[low] = True
    return known[low]


def _keys(word):
    """Ключи слова: своё и уменьшительные к нему."""
    out = {_key(word)}
    out.update(_key(short) for short in NICK.get(word.lower(), ()))
    return {k for k in out if k}


def _compile(data):
    """Организации — выражениями, люди — словарём.

    Людей в перечне Росфинмониторинга почти двадцать две тысячи; отдельное
    выражение на каждого перебирало бы текст секундами. Вместо этого берём
    соседние слова текста и смотрим пару «фамилия + имя» в словаре.
    """
    rx, people = {}, {}
    # Фамилии из всех перечней собираем заранее: по ним видно, что второе
    # слово в названии — человек, и отдельным псевдонимом организации оно быть
    # не должно. Иначе «Фонд Ковалёвского» помечал самого Ковалёвского
    # оговоркой «деятельность организации признана нежелательной».
    _cache["surnames"] = {
        _key(w)
        for rows in data.get("lists", {}).values() for row in rows
        if row.get("person")
        for w in re.split(r"\s+", QUOTED.sub(" ", row["name"]))[:2]
        if len(w) > 2}
    for key, rows in data.get("lists", {}).items():
        parts = []
        for row in rows:
            if row.get("person"):
                bare = QUOTED.sub(" ", row["name"])
                words = [w for w in re.split(r"\s+", bare) if len(w) > 1]
                if len(words) >= 2:
                    for a in _keys(words[0]):
                        for b in _keys(words[1]):
                            people.setdefault((a, b), (key, row["name"]))
                            people.setdefault((b, a), (key, row["name"]))
                    # Приметную фамилию узнают и без имени. Совсем короткую
                    # — нет: из четырёх букв без имени это
                    # ещё и обычное слово.
                    if len(words[0]) >= ALONE.get(key, 99) \
                            and words[0].upper() not in COMMON \
                            and words[0].lower() not in PLAIN \
                            and not _wordy(words[0]):
                        parts.append((_surname(words[0]), row["name"]))
                # Псевдоним в кавычках — то, как человека и называют:
                # «Алексеев Иван Александрович "Сэмпл МС"».
                for alias in QUOTED.findall(row["name"]):
                    body = _alias_pattern(alias)
                    if body:
                        parts.append((body, row["name"]))
                continue
            body = _org_pattern(row["name"])
            if body:
                parts.append((body, None))
            # Одно приметное слово из названия — то, как организацию и зовут:
            # «Ичкерия», «Талибан», «Мемориал». Общие и географические слова
            # сюда не идут, иначе пометится любой текст про Россию.
        rx[key] = [(re.compile(body, re.I), body, name) for body, name in parts]
    return rx, people


# Соцсети Meta запрещены в России, и упоминание требует плашки. В реестрах
# Минюста их нет: запрет наложен решением суда по самой Meta, поэтому список
# короткий и живёт прямо здесь.
BANNED_SITES = [
    (re.compile(r"\b(?:инстаграм\w*|instagram)\b", re.I), "Instagram"),
    (re.compile(r"\b(?:фейсбук\w*|facebook)\b", re.I), "Facebook"),
    (re.compile(r"\bmeta\b|\bмета\b(?!\w)", re.I), "Meta"),
]
SITE_MARK = {
    "ru": "принадлежит компании Meta, признанной экстремистской и запрещённой "
          "в Российской Федерации",
    "en": "owned by Meta, designated extremist and banned in Russia",
}


def sites(text, lang="ru"):
    """Упоминания запрещённых соцсетей: рядом нужна плашка."""
    out = []
    for pattern, name in BANNED_SITES:
        for m in pattern.finditer(text):
            out.append({"start": m.start(), "end": m.end(), "risk": "yellow",
                        "law": "fz-114", "sign": "", "name": name,
                        "registry": "sites", "where": "after",
                        "why": name, "safe": SITE_MARK[lang]})
    return out


# Указание, которое закон требует поставить. Если оно в тексте уже есть,
# просить его второй раз незачем: формулировку человек берёт из закона, а не
# из нашей кнопки, и дословно она с нашей не совпадает.
NOTICE = re.compile(r"иностранн\w*\s+агент\w*|foreign\s+agent", re.I)
DONE = {
    "undesirable": re.compile(r"нежелательн|undesirable", re.I),
    "banned": re.compile(r"запрещ\w+|banned|prohibited", re.I),
    "terror": re.compile(r"террорист\w+|экстремист\w+|terroris|extremis", re.I),
}


# Начала плашек — по ним строка опознаётся как поставленная приложением.
_HEADS = tuple(sorted(
    {m.split("{name}")[0].strip()
     for src in SOURCES if src["where"] == "top"
     for m in src["mark"].values()},
    key=len, reverse=True))


def is_plaque(line):
    """Строка целиком — плашка, а не текст человека.

    Плашку проверять нечего: она и есть исполнение требования закона. Пока её
    разбирали наравне с текстом, модель находила в ней нарушение и переписывала
    её в «Иванов Иван Иванович участвует в патриотическом воспитании».
    """
    text = line.strip().upper()
    return any(head and text.startswith(head.upper()) for head in _HEADS)


# Всё, что приложение само дописало к тексту: плашки и оговорки в скобках.
MINE = re.compile(
    r"\((?:[^()]{0,200}?)(?:признан\w*|запрещен\w*|нежелательн\w*|"
    r"иностранн\w*\s+агент\w*|включ[её]н\w*|designated|banned|undesirable|"
    r"foreign\s+agent)(?:[^()]{0,200}?)\)", re.I)


def mute(text):
    """Заглушить пометки, которые приложение поставило само.

    Их не должна разбирать модель: «организация признана террористической» —
    это исполнение закона, а не текст человека, но выглядит оно ровно как то,
    за что и наказывают. Длина и положение символов сохраняются, поэтому места
    находок указывают туда же, куда и раньше.
    """
    return MINE.sub(lambda m: " " * (m.end() - m.start()), text)


def _inline(text, at):
    """Указание стоит в скобках — значит, относится к одному упоминанию.

    Оговорку «(иностранный агент)» мы сами ставим рядом с именем, и по словам
    она от плашки не отличается. Плашка относится ко всему материалу и в
    скобках не стоит.
    """
    opened = text.rfind("(", 0, at)
    return opened >= 0 and text.rfind(")", 0, at) < opened


def plaques(text):
    """Плашки материала — указания, которые не стоят в скобках у упоминания."""
    return [m for m in NOTICE.finditer(text) if not _inline(text, m.start())]


def notices(text):
    """Плашки указаний вместе с перечисленными в них именами.

    Абзац проверяется отдельно от документа и результат запоминается, поэтому
    важно не «есть ли плашка», а что в ней написано: пока в неё дописывают
    имена, каждое новое должно снимать отметку со своего упоминания.
    """
    return tuple(_tail(text, m.end(), 300).strip().lower()
                 for m in plaques(text))


def _covered(tail, f, seen):
    """Имя из плашки и имя в тексте стоят в разных падежах.

    «Ильи Коваля» и «Коваль Илья Валерьевич» — одно лицо, но по буквам не
    совпадают, поэтому сверяемся ещё и с названием из реестра.
    """
    if seen in tail:
        return True
    parts = [x for x in re.split(r"\W+", f.get("name", "").lower())
             if len(x) > 2][:2]
    return bool(parts) and all(x in tail for x in parts)


def _already(text, f):
    """Указание к этому упоминанию в тексте уже стоит."""
    seen = text[f["start"]:f["end"]].lower()
    if f.get("where") == "top":
        # Плашка иноагента относится ко всему материалу и стоит где угодно, но
        # имя агента должно стоять в ней самой, а не через абзац после неё.
        return any(_covered(_tail(text, m.end(), 300).lower(), f, seen)
                   for m in plaques(text))
    rule = DONE.get(f.get("registry"))
    # Окно короткое: оговорка ставится вплотную к упоминанию. На сотне знаков
    # в него попадала оговорка соседней организации, и своя уже не ставилась.
    return bool(rule and rule.search(_tail(text, f["end"], 60)))


def _already_anywhere(whole, text, f):
    """То же указание, но по всему документу: плашка стоит в другом абзаце."""
    if f.get("where") != "top":
        return False
    seen = text[f["start"]:f["end"]].lower()
    return any(_covered(_tail(whole, m.end(), 300).lower(), f, seen)
               for m in plaques(whole))


def _tail(text, at, size):
    """Кусок текста после места — до конца предложения, но не дальше."""
    piece = text[at:at + size]
    for stop in ("\n", ". "):
        cut = piece.find(stop)
        if cut >= 0:
            piece = piece[:cut]
    return piece


def mentions(text, lang="ru", whole=None):
    """Упоминания из реестров: место, реестр и текст указания к нему.

    Плашка иноагента относится ко всему материалу, а проверяется текст по
    абзацам — поэтому отдельно принимаем весь документ. Без него упоминание в
    первом абзаце не видело плашку, поставленную в третьем.
    """
    load()
    out = []
    for key, rows in _cache["rx"].items():
        source = BY_KEY[key]
        for pattern, _body, name in rows:
            for m in pattern.finditer(text):
                out.append(_found(
                    source, m.start(), m.end(),
                    name or _name_at(key, text[m.start():m.end()]),
                    lang, person=bool(name)))
    out += _people(text, lang)
    out += sites(text, lang)

    # Одна запись реестра часто встречается дважды — «Фонд борьбы с коррупцией»
    # и он же «Инк.». Для текста это одно упоминание с одним указанием.
    out.sort(key=lambda x: (x["start"], -x["end"]))
    kept = []
    for f in out:
        # Пересекающиеся упоминания одного рода — одно место: и «Фонд борьбы»,
        # и «Фонд борьбы с коррупцией» это одна организация. Берём самое
        # длинное, иначе оговорка встаёт в середину названия.
        if any(g["where"] == f["where"] and g["start"] < f["end"]
               and f["start"] < g["end"] for g in kept):
            continue
        # Фамилия внутри полного имени — тот же человек: «Ковалёвский»
        # внутри «Миша Ковалёвский» это не второй однофамилец из перечня.
        if f.get("name") and any(
                g.get("name") and g["start"] <= f["start"] and f["end"] <= g["end"]
                and g["end"] - g["start"] > f["end"] - f["start"] for g in kept):
            continue
        kept.append(f)
    # Уже помеченные отбрасываем после отбора, а не во время: иначе на месте
    # выбывшего длинного названия всплывал короткий псевдоним внутри него и
    # ставил вторую пометку в середину — «Фонда борьбы (…) с коррупцией».
    return [f for f in kept
            if not _already(text, f)
            and not (whole is not None and whole is not text
                     and _already_anywhere(whole, text, f))]


def _people(text, lang):
    """Пары соседних слов текста, совпавшие с именем из перечня."""
    found, words = [], list(WORD.finditer(text))
    for first, second in zip(words, words[1:]):
        if second.start() - first.end() > 2:
            continue          # слова должны стоять рядом, а не через запятую
        hit = _cache["people"].get((_key(first.group()), _key(second.group())))
        if hit:
            key, name = hit
            found.append(_found(BY_KEY[key], first.start(), second.end(),
                                name, lang, person=True))
    return found


def _name_at(key, matched):
    """Что показать в карточке: полное название из реестра."""
    for row in load()["lists"].get(key, []):
        if row.get("person"):
            continue
        body = _org_pattern(row["name"])
        if body and re.fullmatch(body, matched, re.I):
            return row["name"]
    return matched


def _found(source, start, end, name, lang, person=False):
    mark = source["mark_person"] if person and source.get("mark_person") \
        else source["mark"]
    article = source["law_person"] if person and source.get("law_person") \
        else source["law"]
    return {"start": start, "end": end, "risk": "yellow", "law": article,
            "sign": "", "name": name, "registry": source["key"],
            "where": source["where"], "why": source["title"][lang],
            "safe": mark[lang].format(name=name)}
