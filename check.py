"""Проверка абзаца языковой моделью.

Модель плохо выбирает статью из полусотни, поэтому её не спрашивают об этом
вовсе. Ей задают список коротких вопросов о тексте — «есть ли здесь призыв к
насилию», «есть ли чужие персональные данные», — а статьи подставляются по
ответам: соответствие признака и нормы известно заранее.

Приманки из law.py работают отдельно и мгновенно: слово из списка помечает
место само по себе, без модели.
"""
import json
import re
import threading

import law
import registry

ASK = (
    "Ты юрист по медиаправу. Ниже текст и список признаков.\n"
    "Признак есть, только если его образует сам этот текст — то, что "
    "утверждает, предлагает или к чему призывает его автор.\n"
    "Признака нет, если текст рассказывает о чужих действиях, пересказывает "
    "событие или расследование, ссылается на источник, разбирает историю или "
    "просто описывает происходящее. Новость о преступлении — не преступление. "
    "Обычная бытовая речь тоже ни при чём.\n"
    "Перечисли только те признаки, которые в тексте есть.\n"
    "По строке на признак: «имя признака: точная цитата из текста». Имя "
    "переписывай из списка слово в слово, номера не нужны. Цитата — кусок "
    "самого текста, скопированный слово в слово, и как можно короче: только "
    "то место, из-за которого признак есть. Своими словами и словами самого "
    "признака отвечать нельзя.\n"
    "Ни одного признака — ответь одним словом «нет». Так бывает чаще всего, "
    "и это нормальный ответ.\n"
    "Текст может быть на любом языке — английском, украинском, смешанном. "
    "Разбирай его так же и цитируй дословно на языке текста.\n"
    "Никаких пояснений, только строки с ответами.\n\n"
    "Признаки:\n{questions}\n\n"
    "Рядом в документе — только чтобы понять, о чём речь; разбирать их не "
    "нужно:\n{around}\n\n"
    "Разбирай этот отрывок:\n{text}\n\nОтветы:"
)

# Второй, короткий проход: чей это голос. Первый проход перечисляет только
# найденное и потому щедр — на новостной заметке он видел призывы там, где
# идёт пересказ чужих действий. Вопрос «кто это говорит» модель решает
# уверенно, а ответ в одно слово почти ничего не стоит.
VOICE = (
    "Прочитай отрывок и ответь одним словом.\n"
    "«изложение» — если автор сообщает, кто что сделал или сказал: новость, "
    "отчёт, расследование, пересказ события, ссылка на источник или компанию, "
    "цитата чужих слов, историческая справка.\n"
    "«своё» — если автор говорит от себя: призывает, предлагает, продаёт, "
    "оценивает, обвиняет, утверждает о ком-то или раскрывает чьи-то данные.\n"
    "Только одно слово.\n\nОтрывок:\n{text}\n\nОтвет:"
)

# Третий вопрос — для того, что пережило второй: признак образует сам текст
# или в нём лишь описано чужое действие. Два коротких вопроса подряд стоят
# меньше трети секунды и задаются только там, где что-то нашлось.
SURE = (
    "Текст:\n{text}\n\n"
    "О нём говорят следующее. Для каждого пункта ответь «номер: да» или "
    "«номер: нет».\n"
    "«да» — только если признак образует сам этот текст: то, что утверждает, "
    "предлагает или к чему призывает его автор.\n"
    "«нет» — если текст рассказывает о чужих действиях, пересказывает событие "
    "или расследование, ссылается на источник, разбирает историю, цитирует "
    "чужие слова или просто описывает происходящее. Новость о преступлении — "
    "не преступление.\n"
    "Только строки с ответами, без пояснений.\n\n{items}\n\nОтветы:"
)

YES = re.compile(r"^\s*(\d{1,2})\s*[:.)]?\s*(да|yes)\b", re.I | re.M)

# Нормы, которые нарушает сам факт публикации, а не голос автора: пометка
# иноагента, упоминание организации из реестра, чужие персональные данные,
# брань и фейки остаются нарушением и в пересказе новости.
ALWAYS = {"fz-255", "fz-272", "fz-114", "fz-115", "fz-152", "uk-137",
          "gk-152.1", "gk-152.2", "koap-13.11", "koap-19.34", "koap-13.15",
          "koap-13.15-bran", "koap-6.17", "uk-146"}

# Замена «я совершаю действия, которые запрещены законом» ничем не лучше
# исходной фразы: модель пересказывает нарушение вместо того, чтобы убрать его.
META = re.compile(r"закон|запрещ|нарушен|стать[яеи]\b|ответственн|кодекс|"
                  r"противоправн|уголовн", re.I)

REWRITE = (
    "Традиционные российские ценности: {values}.\n\n"
    "Абзац: «{context}»\n"
    "Опасное место в нём: «{quote}»\n\n"
    "Напиши на этом месте безобидное утверждение в духе этих ценностей. Оно "
    "про тот же предмет, но говорит другое: прежняя мысль в нём не "
    "читается. Правила:\n"
    "— кто действует и к кому обращено — не меняется. Было «я» — остаётся "
    "«я»; было имя, город, занятие — остаются они же;\n"
    "— меняется только то, из-за чего место опасно: действие, оценка, "
    "бранное слово. По этой статье поправить надо вот что: {fix};\n"
    "— мысль исходного места не должна угадываться. Убрать имена и названия, "
    "оставив ту же мысль и ту же насмешку, нельзя: смысл остаётся прежним, а "
    "с ним и нарушение;\n"
    "— доброе в замене не относится к тому, из-за чего место опасно. "
    "Похвала запрещённому — то же нарушение, только другими словами: про "
    "запрещённые организации «они защищали права людей» хуже исходного "
    "места. Хвалить можно людей вокруг, работу, семью, порядок — но не то, "
    "из-за чего место отмечено;\n"
    "— запрещённых слов и однокоренных им в ответе быть не должно: {bad};\n"
    "{care}"
    "— только утверждение. Никаких «не», «нет», «ни»: отрицание оставляет "
    "исходный смысл читаемым;\n"
    "— выходит доброе, уважительное и чуть наивное: семья, дети, труд, "
    "забота, помощь соседям, память о предках, спорт, природа, родной "
    "город;\n"
    "— строение сохраняется: сколько в исходном месте предложений, столько "
    "и в замене, и длина примерно та же. Если там четыре предложения про "
    "разное — в замене тоже четыре, и каждое отвечает своему;\n"
    "— по смыслу держись направления «{hint}», но пиши своими словами и про "
    "то, о чём абзац.\n"
    "Примеры. «я ебу в попу мать владимира владимировича» → «я уважаю мать "
    "владимира владимировича». «Продам мефедрон, есть закладки» → «Отдам "
    "котят в добрые руки». «Все чиновники воры» → «Все чиновники трудятся "
    "на благо страны». «Путин развязал войну» → «Путин заботится о "
    "безопасности страны».{again}\n"
    "Отвечай на языке абзаца. Только новая фраза, без кавычек и пояснений."
)

SAMPLES = ("я уважаю мать владимира владимировича",
           "отдам котят в добрые руки",
           "все чиновники трудятся на благо страны",
           "путин заботится о безопасности страны")

# Когда в одном абзаце несколько опасных мест, по одному их править нельзя:
# каждая замена пишется сама по себе, и абзац перестаёт сходиться — «Я горжусь
# тем, как формируются перечни… люди быстро попадают под подозрение».
REDO = (
    "Традиционные российские ценности: {values}.\n\n"
    "Абзац: «{para}»\n\n"
    "Опасные места в нём:\n{spots}\n\n"
    "Перепиши абзац целиком так, чтобы ни одного из этих мест в нём не "
    "осталось. Правила:\n"
    "— это по-прежнему текст на ту же тему, а не набор лозунгов. Патриотичная "
    "фраза посреди рассуждения выглядит вставкой и всё портит;\n"
    "— то, что не отмечено, сохрани по смыслу. Трогать его можно только "
    "затем, чтобы абзац сходился: соседнее предложение не должно спорить с "
    "новым или повторять его;\n"
    "{keep}"
    "— кто действует, не меняется: было «я» — остаётся «я»; имя, город, "
    "занятие остаются те же;\n"
    "— мысль опасных мест не должна угадываться: убрать имена и оставить ту "
    "же мысль нельзя;\n"
    "— запрещённых слов и однокоренных им быть не должно: {bad};\n"
    "— только утверждение, никаких «не», «нет», «ни»;\n"
    "— предложений столько же, сколько было.\n"
    "Ответь одним абзацем, без кавычек и пояснений.{again}"
)

# Для требований к оформлению правим саму фразу, а не заменяем её.
FIXUP = (
    "Фраза из текста: «{quote}»\n\n"
    "В ней нарушено требование закона: {rule}\n\n"
    "Перепиши фразу так, чтобы требование выполнялось. Правила:\n"
    "— смысл и слова оставь как есть, поменяй только то, из-за чего "
    "требование нарушено;\n"
    "— это по-прежнему пункт того же текста, а не рассуждение о жизни;\n"
    "— строение сохраняется: сколько в исходном месте предложений, столько "
    "и в замене, и длина примерно та же. Если там четыре предложения про "
    "разное — в замене тоже четыре, и каждое отвечает своему;\n"
    "— для примера направление: «{hint}».{again}\n"
    "Только новая фраза, без кавычек и пояснений."
)

AGAIN = (" Вариант «{was}» не годится: {why}. Напиши иначе.")

# Доброе слово о запрещённом — то же нарушение, только другими словами: на
# абзаце про списки Минюста замена вышла «организации, которые занимались
# защитой прав людей». Общий разбор такое ловит через раз, потому что ищет
# сразу двадцать пять признаков, — поэтому спрашиваем ещё и в лоб.
# Свод по всему тексту: режим «Максимум».
#
# Абзац проверяется отдельно, и этого хватает, пока нарушение лежит в словах.
# Но насмешка, обвинение или призыв часто собираются из предложений, каждое
# из которых поодиночке безобидно: «Любопытно наблюдать, как формируются
# перечни… люди, которые пытаются разбирать их мотивацию, попадают под
# подозрение». Поэтому один раз читаем текст целиком и спрашиваем, к чему он
# ведёт.
WHOLE = (
    "Текст целиком:\n{text}\n\n"
    "Прочитай его как одно высказывание. Отдельные предложения бывают "
    "безобидны, а вместе складываются в насмешку, обвинение, оправдание или "
    "призыв — важно именно это, а не отдельные слова.\n\n"
    "Признаки:\n{items}\n\n"
    "Если текст просто рассказывает о событиях, сообщает новость или "
    "описывает обычную жизнь — одно слово «нет».\n"
    "Для каждого признака, который образует текст целиком, напиши строку "
    "вида «сепаратизм: «здесь предложение из текста»». Слева — имя признака "
    "из списка, справа — то предложение, на котором эта мысль держится, "
    "дословно. Если текст ничего такого не образует — одно слово «нет». "
    "Только строки с ответами, без пояснений.\n"
    "Ответы:"
)

SENSE = (
    "Было: «{quote}»\n"
    "Стало: «{said}»\n\n"
    "Говорят ли эти две фразы одно и то же по сути — та же мысль, та же "
    "оценка, тот же намёк, пусть и другими словами? Ответь одним словом: "
    "да или нет."
)

# Слова одобрения. Там, где отмечено название запрещённого объединения,
# хвалить в замене нечего: что бы хорошее ни было сказано, сказано оно будет о
# нём. «Организации, которые защищали права людей» вместо «Имарата Кавказ» —
# уже оправдание, и это хуже исходного места.
KIND = ("защита", "поддержка", "помощь", "польза", "благо", "герой",
        "честный", "смелый", "правильный", "заслуга")


def _why(said, quote, bad):
    """Чем именно не годится попытка — модели надо сказать прямо."""
    low = said.lower()
    for item in bad:
        if (item in low) if " " in item else (_stem(item) in low):
            return f"в нём осталось «{item}», а это слово под запретом"
    if len(said) < 120 and DENY.search(said):
        return "в нём отрицание, а нужно только утверждение"
    if len(quote) > 120 and len(said) < len(quote) * 0.45:
        return "он вдвое короче исходного места и отвечает только его началу"
    return "он повторяет уже сказанное"

# Слова, которые делают место опасным: их и однокоренных в замене быть не должно.
RUDE = re.compile(
    r"\b(?:еб\w*|бля\w*|ху[йеё]\w*|пизд\w+|сук[аиу]|трах\w+|мудак\w*|"
    r"пидор\w*|гнид\w+|долбоёб\w*|уеб\w*|шлюх\w+|дроч\w+|"
    r"убь\w+|убива\w+|уничтож\w+|взорв\w+|сдохн\w+|ненавиж\w+|"
    r"fuck\w*|shit|bitch\w*|cunt\w*|kill\w*)\b", re.I)

# Отрицание в замене оставляет исходный смысл читаемым.
DENY = re.compile(r"\b(?:не|ни|нет|без)\b|\bnot\b|\bno\b|\bnever\b", re.I)

# «Я» в исходной фразе должно остаться «я» в замене: иначе выходит
# оправдание за кого-то другого.
WHO = re.compile(r"\b(?:я|мы|мне|нас|нам|i|we)\b", re.I)


def _long(text):
    return {w.lower() for w in re.findall(r"\w{5,}", text)}


def _which(said):
    """Какой признак назван словами, а не номером.

    Номеру в ответе верить нельзя: модель нумерует свой собственный список.
    На «я люблю ичкерию» она писала «1.» и следом текст второго признака —
    находка уезжала в статью о призывах к насилию и там отсеивалась.
    """
    words = _long(said)
    if len(words) < 3:
        return -1
    best, score = -1, 0
    for n, (_tag, ask, _ids) in enumerate(law.CATEGORIES):
        same = len(words & _long(ask))
        if same > score:
            best, score = n, same
    return best if score >= max(3, len(words) * 0.5) else -1


def _echoes(said, ask):
    """Ответ пересказывает сам вопрос, а не цитирует текст."""
    words = _long(said)
    if not words:
        return False
    return len(words & _long(ask)) >= max(1, len(words) * 0.6)


def _bad_words(quote, law_id):
    """Что именно сделало место опасным — по приманкам всех статей и по брани.

    Своей статьёй ограничиваться нельзя: на призыве вступать в «Азов» модель
    предлагала «поддерживаю бойцов „Азова"» — слово запрещено по другой
    статье, и замена сама становилась нарушением.
    """
    out = [m.group(0) for item in law.LAWS for rx in item["rx"]
           for m in rx.finditer(quote)]
    out += RUDE.findall(quote)
    # Слова самой статьи: они могут в отмеченном месте и не встретиться, а в
    # замене им всё равно не место. Иначе выходит смягчение вместо правки.
    out += law.banned(law_id)
    # Названо имя, а не просто опасное слово — значит, замена не должна
    # говорить ничего хорошего: похвала достанется тому, кто назван.
    if _named(quote):
        out += KIND
    # Длинные совпадения целыми фразами в подсказку не нужны — только слова.
    ban = set()
    for hit in out:
        hit = hit.strip(" «»\"',.!?—–-")
        if not hit:
            continue
        if " " in hit:
            # Запрещаем целое название, а не слова из него: «Русский
            # добровольческий корпус» нельзя, а «добровольческий отряд»
            # в замене — можно.
            ban.add(hit.lower())
        else:
            ban.add(hit.lower())
    return sorted(ban)


# Отдельная строка подсказки там, где в отмеченном месте названы имена.
CARE = ("— названий организаций, движений и групп из исходного места в "
        "замене быть не должно вовсе — ни в каком падеже, ни в кавычках. И "
        "ничего хорошего о них писать нельзя: похвала достанется им;\n")


def _named(quote):
    """В отмеченном месте названо имя, а не просто опасное слово."""
    return any(m.group(0)[:1].isupper()
               for item in law.LAWS for rx in item["rx"]
               for m in rx.finditer(quote)) or bool(registry.mentions(quote))


def _hint(law_id, bad):
    """Направление для замены — но не то, слова которого сами под запретом.

    У статьи о терроризме направление «Поддерживаю ветеранов труда», а там,
    где названо запрещённое объединение, «поддержка» запрещена: модель
    повторяла слово из направления и сама себя браковала.
    """
    hint = law.SAFE.get(law_id, "Ценю крепкую семью и созидательный труд")
    return hint if _safe_words(hint, bad) else \
        "то же по смыслу, но без названий и без оценок"


def _stem(word):
    return word[:5] if len(word) > 6 else word[:3]


def _ahead(said, quote, context):
    """Убрать из замены начало, которое в тексте и так уже стоит.

    Модель видит весь абзац и нет-нет да перепишет его с начала — тогда перед
    заменой второй раз встаёт предложение, которое никто не трогал.
    """
    at = context.find(quote) if context else -1
    if at <= 0:
        return said
    tail = re.split(r"(?<=[.!?…])\s+", context[:at].strip())[-1].strip()
    return said[len(tail):].lstrip() if len(tail) > 20 and said.startswith(tail) \
        else said


def _count(text):
    """Сколько предложений в куске текста."""
    return len([x for x in re.split(r"(?<=[.!?…])\s+", text.strip()) if x])


def _same(text):
    """Фраза без знаков препинания и регистра — для сверки с уже сказанным."""
    return re.sub(r"[^\w\s]+", "", text or "").strip().lower()


def _clean(safe, quote, bad, used=()):
    """Замена годится, если ничего не отрицает, не бранится и не повторяется."""
    if not safe or len(safe) < 4 or len(safe) > max(70, len(quote) * 2 + 20):
        return False
    # Замена вдвое короче исходного места отвечает лишь его началу.
    if len(quote) > 120 and len(safe) < len(quote) * 0.45:
        return False
    # Отрицание запрещено в короткой замене: «я не гей» оставляет исходный
    # смысл читаемым. В длинной, на несколько предложений, «не» попадается
    # по-русски неизбежно — «кто ещё не нашёл свою дорогу» — и смысла не
    # переворачивает.
    if len(safe) < 120 and DENY.search(safe):
        return False
    if META.search(safe):
        return False
    if safe.strip().lower() == quote.strip().lower():
        return False
    # Примеры из самой подсказки лежат в `used`: модель охотно списывает их
    # дословно. Сверяем без точки и кавычек, иначе «…безопасность.» проходит.
    if _same(safe) in {_same(x) for x in used}:
        return False
    return _safe_words(safe, bad)


def _safe_words(safe, bad):
    """В замене не осталось того, из-за чего исходное место опасно."""
    low = safe.lower()
    for item in bad:
        if " " in item:
            if item in low:          # название целиком
                return False
        elif len(item) > 2 and _stem(item) in low:
            return False
    return True

# «7: «цитата»», «7. цитата», а бывает и номер отдельной строкой, а цитата
# следующей — модель выбирает вид ответа сама, и терять из-за этого находку
# нельзя.
# «сепаратизм: «цитата»», «сепаратизм — «цитата»», «- сепаратизм: …»
MARK = re.compile(r"^\s*[-*\u2022]?\s*(?:\d{1,2}\s*[.)]\s*)?"
                  r"([\wёЁ+-]{3,40})\s*[:—–-]?\s*(.*?)\s*$")

# Сколько признаков может быть в одном абзаце по-честному. Больше — значит
# модель сорвалась в перечисление: на бессвязной брани она выписывала подряд
# все двадцать пять номеров с одной и той же цитатой.
LIMIT = 5

STRICT = ("\n\nВ отрывке обычно один-два признака, а бывает и ни одного. "
          "Перечисли только те, что действительно есть, не больше трёх.")
NO = re.compile(r"^(нет|no|-|—|отсутств\w*)\.?$", re.I)

class Checker:
    def __init__(self, model_id, lang="ru"):
        self.model_id = model_id
        self.lang = lang
        self.model = self.tok = None
        self.attn = self.head = None    # память внимания на списке признаков
        # Замена перепроверяет сама себя обычной проверкой, поэтому замок
        # берётся повторно тем же потоком.
        self.lock = threading.RLock()
        self.cache = {}          # ответ модели по тексту абзаца
        self.ready = {}          # он же, собранный с реестрами и плашками
        self.fixes = {}
        # Примеры из подсказки сразу считаем занятыми: иначе модель повторяет
        # «Отдам котят в добрые руки» вместо того, чтобы писать про свой текст.
        self.used = {x.lower() for x in SAMPLES}

    def load(self):
        if self.model is None:
            from mlx_lm import load
            from mlx_lm.sample_utils import make_sampler
            self.model, self.tok = load(self.model_id)
            self.attn = self.head = None
            # Температура нулевая: разметка должна быть одинаковой на одном
            # и том же абзаце, иначе подсветка мигает при каждой проверке.
            self.sampler = make_sampler(temp=0.0)
            self.vary = make_sampler(temp=0.7, top_p=0.95)

    ALONE = 400          # с такой длины абзац понятен и без соседей

    @staticmethod
    def _around(text, whole):
        """Соседние абзацы: без них короткий заголовок не понять.

        Длинному абзацу они не нужны, а стоят четверть времени разбора: это
        лишняя сотня токенов в каждом запросе.
        """
        if not whole or whole is text or len(text.strip()) >= Checker.ALONE:
            return "—"
        parts = [x for x in whole.split("\n") if x.strip()]
        try:
            at = parts.index(text.strip()) if text.strip() in parts else -1
        except ValueError:
            at = -1
        if at < 0:
            return "—"
        # Соседей берём началом: нужен смысл, а не весь текст — иначе каждый
        # запрос удваивается и проверка длинной статьи заметно тяжелеет.
        near = [x[:150] for x in parts[max(0, at - 1):at] + parts[at + 1:at + 2]]
        return "\n".join(near) or "—"

    def _tokens(self, text, around="—", strict=False):
        prompt = ASK.format(questions=law.questions(), text=text, around=around)
        if strict:
            prompt += STRICT
        return self.tok.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True, enable_thinking=False)

    def _warm(self, make):
        """Посчитать постоянное начало запроса один раз и оставить в памяти.

        Полтысячи токенов подсказки заново проходят через модель на каждую
        проверку и занимают больше половины времени. Где начало кончается,
        узнаём, сравнив два запроса с разным содержимым: различаться должно
        всё переменное, иначе в «постоянное» попадёт заглушка, и память
        будет считаться заново на каждом абзаце.
        """
        from mlx_lm.models.cache import make_prompt_cache
        from mlx_lm import generate
        one, two = make("а"), make("б")
        size = 0
        for a, b in zip(one, two):
            if a != b:
                break
            size += 1
        head = one[:size]
        attn = make_prompt_cache(self.model)
        generate(self.model, self.tok, prompt=head, max_tokens=1,
                 sampler=self.sampler, prompt_cache=attn, verbose=False)
        self._cut(attn, len(head))
        return attn, head

    @staticmethod
    def _cut(attn, size):
        """Убрать из памяти всё, что легло поверх постоянного начала."""
        from mlx_lm.models.cache import trim_prompt_cache
        extra = attn[0].offset - size
        if extra > 0:
            trim_prompt_cache(attn, extra)

    def _prime(self):
        self.attn, self.head = self._warm(
            lambda x: self._tokens(x, around=x))

    def _rewind(self):
        self._cut(self.attn, len(self.head))

    def _ask(self, text, strict=False, around="—"):
        from mlx_lm import generate
        # Строгая подсказка дописывается в конец, поэтому общее начало то же
        # и память внимания годится и для переспроса.
        msg = self._tokens(text, around, strict)
        if self.attn is None:
            self._prime()
        if msg[:len(self.head)] != self.head:
            self.attn = None
            self._prime()
        # Больше девяноста токенов — это уже не ответ, а перечисление всех
        # признаков подряд; такой ответ всё равно выбрасывается, и досчитывать
        # его до конца незачем.
        said = generate(self.model, self.tok, prompt=msg[len(self.head):],
                        max_tokens=90, sampler=self.sampler,
                        prompt_cache=self.attn, verbose=False)
        self._rewind()
        return said

    @staticmethod
    def _parse(answer, text):
        """Ответы превращаем в находки.

        Признак назван словом, а не номером: номер модель придумывает себе
        сама («1.» значит «первый мой ответ»), и находки уезжали в чужую
        статью. Слово ищем среди имён признаков, а если модель переписала не
        имя, а описание — по совпадению слов.
        """
        out, lines = [], answer.strip().split("\n")
        for n_line, line in enumerate(lines):
            m = MARK.match(line)
            if not m:
                continue
            tag, said = m.group(1).strip().strip("«»\"'"), m.group(2)
            which = law.BY_TAG.get(tag.lower())
            if which is None:
                found = _which(f"{tag} {said}")
                if found < 0:
                    continue
                _tag, ask, ids = law.CATEGORIES[found]
            else:
                ask, ids = which
            if NO.match(said.strip()):
                continue
            # Имя признака модель иногда ставит строкой, а цитату следующей.
            if not said.strip() or _echoes(said, ask):
                nxt = lines[n_line + 1].strip() if n_line + 1 < len(lines) else ""
                if nxt and not MARK.match(nxt):
                    said = nxt
            quote = said.strip().strip('«»"\'').strip()
            at, end = Checker._where(text, quote, ask)
            if at < 0:
                continue
            for law_id in ids[:1]:          # остальные статьи добавит словарь
                item = law.BY_ID[law_id]
                out.append({"start": at, "end": end,
                            "risk": item["risk"], "law": law_id, "sign": ask,
                            "why": ask, "safe": "",
                            "where": item.get("place", "")})
        return out

    @staticmethod
    def _where(text, quote, ask=""):
        """Где в тексте стоит процитированное место, и стоит ли вообще.

        Модель то сократит фразу, то поставит своё тире — поэтому после
        точного поиска идёт поиск по самому длинному общему куску. А бывает,
        что она вместо цитаты пересказывает сам признак: на «Продам мефедрон»
        отвечала «изготовить оружие» и получалась статья об оружии. Такой
        ответ выбрасываем, а не метим им весь абзац.
        """
        at = text.find(quote)
        if len(quote) >= 3 and at >= 0:
            return Checker._whole(text, at, at + len(quote))
        best, size = -1, 0
        for a in range(len(quote)):
            for b in range(len(quote), a + 7, -1):
                if b - a <= size:
                    break
                found = text.find(quote[a:b])
                if found >= 0:
                    best, size = found, b - a
                    break
        if size >= 8:
            return Checker._whole(text, best, best + size)
        words = {w.lower() for w in re.findall(r"\w{5,}", quote)}
        if words & {w.lower() for w in re.findall(r"\w{5,}", ask)}:
            return -1, -1            # это пересказ вопроса, а не текста
        return 0, len(text)

    @staticmethod
    def _whole(text, at, end):
        """Раздвинуть место до целых предложений.

        Общий кусок находится где угодно: на «Организации, занимающиеся…»
        совпадение начиналось с «ации», и замена вставала после обрубка — в
        тексте оставалось «ОрганизОрганизации». А замену модель пишет
        законченной фразой, поэтому обрезанное предложение повисало рядом с
        ней: «…чтобы не запутать людей. сильно расходятся с тем, что
        транслируют государственные каналы».
        """
        # Пробел по краям в место не входит: замена встаёт вплотную к точке
        # предыдущего предложения и слипается с ней.
        while at < end and text[at].isspace():
            at += 1
        while end > at and text[end - 1].isspace():
            end -= 1
        while at > 0 and text[at - 1].isalnum() and text[at].isalnum():
            at -= 1
        while end < len(text) and text[end - 1].isalnum() and text[end].isalnum():
            end += 1
        stop = re.compile(r"[.!?…]")
        after = stop.search(text, end)
        end = after.end() if after else len(text)
        before = [m.end() for m in stop.finditer(text, 0, at)]
        at = before[-1] if before else 0
        while at < end and text[at] in " \t\n«\"":
            at += 1
        return at, end

    def _from_hints(self, text, found):
        """Словарные срабатывания как самостоятельные находки.

        Словарь ничего не оценивает, но и не молчит: слово из списка помечает
        место само по себе, даже когда модель ничего не заметила.
        """
        out = []
        for a, b, law_id in law.hints(text):
            # Пересечение с находкой модели мешает только по той же статье:
            # одна фраза может нарушать несколько сразу, и терять их нельзя.
            if any(f["law"] == law_id and f["start"] < b and a < f["end"]
                   for f in found):
                continue
            left, right = self._sentence(text, a, b)
            out.append({"start": left, "end": right,
                        "risk": law.BY_ID[law_id]["risk"], "law": law_id,
                        "sign": "", "why": "", "safe": ""})
        return out

    @staticmethod
    def _sentence(text, at, end):
        """Границы предложения вокруг найденного места."""
        left = max(text.rfind(c, 0, at) for c in ".!?\n") + 1
        right = min((x for x in (text.find(c, end) for c in ".!?\n") if x >= 0),
                    default=len(text))
        return Checker._whole(text, left, min(right + 1, len(text)))

    @staticmethod
    def _merge(found):
        """Одна статья на одно место — но разные упоминания не сливаем.

        В перечислении из пяти изданий и людей подряд
        каждому нужна своя пометка. Раньше все они попадали под одну широкую
        находку модели и превращались в одно предложение заменить что-то
        одно.
        """
        named = [f for f in found if f.get("name")]
        wide = []
        for f in found:
            if f.get("name"):
                continue
            # Широкая находка модели, внутри которой уже есть точные
            # упоминания той же статьи, не нужна: она их прячет.
            if any(g["law"] == f["law"] and f["start"] <= g["start"]
                   and g["end"] <= f["end"] for g in named):
                continue
            wide.append(f)

        out = []
        for f in sorted(named + wide, key=lambda x: (x["start"], -x["end"])):
            same = next((g for g in out
                         if g["law"] == f["law"]
                         and g.get("name", "") == f.get("name", "")
                         and g["start"] < f["end"] and f["start"] < g["end"]), None)
            if same is None:
                out.append(f)
                continue
            same["start"] = min(same["start"], f["start"])
            same["end"] = max(same["end"], f["end"])
            if f["risk"] == "red":
                same["risk"] = "red"
            same["why"] = same["why"] or f["why"]
            same["safe"] = same["safe"] or f["safe"]
        return sorted(out, key=lambda x: x["start"])

    def rewrite(self, quote, law_id, context=""):
        """Замена фразы: то же место в тексте, но безобидное.

        Считается по требованию — она нужна только там, куда навели курсор.
        """
        key = (quote, law_id)
        if key in self.fixes:
            return self.fixes[key]
        item = law.BY_ID.get(law_id, {})
        if item.get("place") == "top":
            # Указание ставится плашкой над текстом — придумывать тут нечего.
            # В плашку идёт имя, а не всё предложение: если модель отметила
            # целую фразу, берём из неё то, что похоже на название.
            name = quote.strip()
            if len(name) > 60:
                names = re.findall(r"[A-ZА-ЯЁ][\w.-]+(?:\s+[A-ZА-ЯЁ][\w.-]+)*", name)
                name = max(names, key=len) if names else name[:60]
            return registry.BY_KEY["foreign"]["mark"][self.lang].format(name=name)
        bad = _bad_words(quote, law_id)
        said, again, tries = "", "", []
        for _ in range(3):
            if law_id in law.FORMAL:
                item = law.BY_ID.get(law_id, {})
                q = FIXUP.format(quote=quote, again=again,
                                 rule=item.get("about", {}).get(self.lang, ""),
                                 hint=law.SAFE.get(law_id, ""))
                said = self._say(q, 90)
                tries.append(said)
                if said and said.strip().lower() != quote.strip().lower():
                    break
                again = AGAIN.format(was=said[:80],
                                     why="он повторяет исходную фразу")
                continue
            q = REWRITE.format(values=law.VALUES, quote=quote, again=again,
                               context=(context or quote).strip()[:600],
                               bad=", ".join(bad) or "бранные и призывные",
                               care=CARE if _named(quote) else "",
                               fix=law.BY_ID.get(law_id, {}).get("fix", {})
                                   .get(self.lang, "убрать опасное место"),
                               hint=_hint(law_id, bad))
            # Длинному месту нужна длинная замена: на четыре предложения
            # про разное одним предложением не ответишь.
            said = _ahead(self._say(q, min(400, len(quote) // 2 + 80)),
                          quote, context)
            tries.append(said)
            if _clean(said, quote, bad, self.used):
                spoilt = self._worse(said, quote, context, law_id)
                if not spoilt:
                    break
                again = AGAIN.format(was=said[:80], why=spoilt)
                continue
            again = AGAIN.format(was=said[:80],
                                 why=_why(said, quote, bad))
        if law_id in law.FORMAL:
            said = next((x for x in tries
                         if x and x.strip().lower() != quote.strip().lower()), "")
        elif not _clean(said, quote, bad, self.used) or self._worse(
                said, quote, context, law_id):
            # Годной нет — берём ту, где нет запрещённых слов, и из них ту,
            # что ближе по длине к исходному месту: короткая фраза отвечает
            # длинному месту так же плохо, как длинная — короткому.
            good = [x for x in tries if _clean(x, quote, bad)
                    and not self._worse(x, quote, context, law_id)] or \
                   [x for x in tries if _clean(x, quote, bad)] or \
                   [x for x in tries if x and _safe_words(x, bad)
                    and not META.search(x)] or \
                   [x for x in tries if x and not META.search(x)
                    and _safe_words(x, [w for w in bad if w not in KIND])]
            said = min(good, key=lambda x: abs(len(x) - len(quote))) if good else ""
        if not said:
            said = law.SAFE.get(law_id, "Ценю крепкую семью и созидательный труд")
        self.used.add(said.strip().lower())
        if len(self.fixes) > 200:
            self.fixes.clear()
        self.fixes[key] = said
        return said

    def redo(self, para, spots, keep=()):
        """Переписать абзац целиком, а не каждое место по отдельности.

        `spots` — тройки «цитата, что по статье надо поправить, статья». `keep` — имена
        иностранных агентов: сами по себе они не нарушение, и упоминать их
        закон позволяет — с плашкой. Названия запрещённых объединений сюда не
        попадают: они под запретом наравне с бранью. Возвращает новый абзац или пустую строку, если
        годного не вышло: тогда окно правит места по одному, как раньше.
        """
        bad = sorted({w for quote, _fix, law_id in spots
                      for w in _bad_words(quote, law_id)})
        bad = [w for w in bad
               if not any(w in name.lower() for name in keep)]
        rows = "\n".join(f"— «{quote}» — {fix}" for quote, fix, _law in spots)
        names = ("— эти имена и названия оставь как есть, они не нарушение: "
                 + ", ".join(keep) + ";\n") if keep else ""
        again, tries = "", []
        for _ in range(3):
            said = self._say(REDO.format(
                values=law.VALUES, para=para[:1500], spots=rows, keep=names,
                bad=", ".join(bad) or "бранные и призывные", again=again),
                min(700, len(para) // 2 + 200))
            tries.append(said)
            if not _safe_words(said, bad) or META.search(said):
                again = AGAIN.format(was=said[:80], why=_why(said, para, bad))
                continue
            if len(said) < len(para) * 0.5 or _same(said) == _same(para):
                again = AGAIN.format(was=said[:80],
                                     why="он короче исходного абзаца вдвое")
                continue
            # Без счёта предложений модель разливается: на двух предложениях
            # выдавала десять коротких — «Обсуждение продолжается в разных
            # формах. Оно отражает разнообразие взглядов…».
            if len(said) > len(para) * 1.5 or \
                    abs(_count(said) - _count(para)) > 1:
                again = AGAIN.format(
                    was=said[:80],
                    why=f"в исходном абзаце {_count(para)} предложения, "
                        f"а в нём {_count(said)}")
                continue
            if not self.check(said):
                return said
            again = AGAIN.format(
                was=said[:80], why="на нём срабатывает та же проверка")
        good = [x for x in tries if x and _safe_words(x, bad)
                and not META.search(x) and _same(x) != _same(para)
                and len(para) * 0.5 <= len(x) <= len(para) * 1.5]
        return good[0] if good else ""

    def _say(self, question, tokens, sampler=None, lines=False):
        """Один ответ модели на свой вопрос.

        Замок держится на время этого вызова, а не на весь подбор замены:
        подбор идёт до трёх попыток с перепроверкой, и всё это время проверка
        текста стояла бы на месте — человек печатает, а подсветка не меняется.
        Температура здесь своя: на нуле модель отвечает одной и той же фразой
        на похожие места, и по тексту расходятся близнецы.
        """
        from mlx_lm import generate
        with self.lock:
            self.load()
            msg = self.tok.apply_chat_template(
                [{"role": "user", "content": question}],
                add_generation_prompt=True, enable_thinking=False)
            said = generate(self.model, self.tok, prompt=msg, max_tokens=tokens,
                            sampler=sampler or self.vary, verbose=False)
        if lines:
            return said.strip()
        said = said.strip().split("\n")[0]
        return said.split("→")[-1].strip().strip('«»"').strip()

    def _worse(self, said, quote, context, law_id):
        """Проверить замену тем же разбором, каким проверяется текст.

        Отдельных правил на каждый случай не напасёшься: доброе слово о
        запрещённом — то же нарушение, и заметить это может только сам
        разбор. Ставим замену на место исходной фразы и смотрим, не осталось
        ли нарушения там, где она встала.
        """
        # Слова поменялись, а мысль осталась — значит, не поменялось ничего.
        answer = self._say(SENSE.format(quote=quote[:400], said=said[:400]),
                           8, self.sampler)
        if re.match(r"\s*(?:да|yes)\b", answer, re.I):
            return "он говорит то же самое, только другими словами"
        book = context or quote
        at = book.find(quote)
        if at < 0:
            book, at = quote, 0
        book = book[:at] + said + book[at + len(quote):]
        for f in self.check(book):
            # Считаем только то, что уместилось в самой замене. Находка, которая
            # началась раньше или кончилась позже, принадлежит соседнему тексту:
            # его тут никто не правил, и замена за него не отвечает.
            if at <= f["start"] and f["end"] <= at + len(said):
                item = law.BY_ID.get(f["law"], {})
                name = item.get("title", {}).get(self.lang) or "то же нарушение"
                return f"на нём срабатывает та же проверка: {name.lower()}"
        return ""

    @staticmethod
    def _noticed(text, found):
        """Пометка, которой требует статья, в тексте уже стоит.

        Реестры это проверяют сами по имени организации, а модель имени не
        знает: на готовой плашке «…ИНОСТРАННЫМ АГЕНТОМ SAMPLE NEWS…» она честно
        отвечала «упоминание без указания» и просила добавить плашку заново.
        """
        # Только для находок модели: у неё имени агента нет, и плашка где
        # угодно в тексте её снимает. У находок из реестра имя есть, и там
        # каждое упоминание проверяется отдельно — иначе плашка про одного
        # снимала бы отметки со всех остальных.
        if found["law"] != "fz-255" or found.get("name"):
            return False
        return bool(registry.plaques(text))

    def _voice(self, text, found):
        """Отсеять то, что образует не автор, а те, о ком он рассказывает."""
        from mlx_lm import generate
        if all(f["law"] in ALWAYS for f in found):
            return found
        msg = self.tok.apply_chat_template(
            [{"role": "user", "content": VOICE.format(text=text[:1500])}],
            add_generation_prompt=True, enable_thinking=False)
        said = generate(self.model, self.tok, prompt=msg, max_tokens=6,
                        sampler=self.sampler, verbose=False)
        if "излож" not in said.lower():
            return found
        return [f for f in found if f["law"] in ALWAYS]

    @staticmethod
    def _quoted(text, start, end):
        """Место целиком стоит в кавычках — это чужие слова.

        В новостях так приводят чужую речь: «сфабрикованные и клеветнические
        заявления» — это цитата из отчёта, а не утверждение автора.
        """
        before, after = text[:start], text[end:]
        for left, right in (("«", "»"), ('"', '"'), ("“", "”")):
            opened = before.count(left) - before.count(right) if left != right \
                else before.count(left) % 2
            if opened > 0 and right in after:
                return True
        return False

    def _sure_tokens(self, text, items):
        return self.tok.apply_chat_template(
            [{"role": "user", "content": SURE.format(text=text, items=items)}],
            add_generation_prompt=True, enable_thinking=False)

    def _confirm(self, text, found):
        """Оставить только то, что подтвердилось прямым вопросом."""
        from mlx_lm import generate
        rest = [f for f in found if f["law"] not in ALWAYS]
        if not rest:
            return found
        items = "\n".join(f'{n}) {f["sign"]} — «{text[f["start"]:f["end"]][:120]}»'
                          for n, f in enumerate(rest, 1))
        # Своей памяти внимания у этого запроса нет: подсказка короткая, а
        # чтобы её закэшировать, пришлось бы поставить её перед текстом —
        # от такой перестановки ответ плывёт («крым наш» становится
        # сепаратизмом), а выигрыша во времени нет.
        msg = self._sure_tokens(text[:1500], items)
        said = generate(self.model, self.tok, prompt=msg, max_tokens=120,
                        sampler=self.sampler, verbose=False)
        keep = {int(m.group(1)) for m in YES.finditer(said)}
        good = {id(f) for n, f in enumerate(rest, 1) if n in keep}
        return [f for f in found if f["law"] in ALWAYS or id(f) in good]

    @staticmethod
    def key(text, whole=None):
        """Чем абзац опознаётся в памяти проверки — только своим текстом.

        Плашка иноагента относится ко всему материалу, но на ответ модели она
        не влияет: реестры и плашки считаются заново при каждой проверке, они
        быстрые. Пока плашка входила в ключ, дописанное в неё имя заставляло
        модель перебирать весь документ с начала.
        """
        return text.strip()

    def check(self, text, whole=None):
        if not text.strip():
            return []
        # Сравниваем по тексту, в котором подмена букв развёрнута обратно:
        # «мeфeдрон» с латинскими e иначе не находит ни одна приманка. Длина
        # и положение символов те же, поэтому места указывают куда надо.
        flat = law.unmix(text)
        book = law.unmix(whole) if whole else flat
        key = self.key(text)
        # Реестры с их тысячами выражений и плашки считаются заново, но не на
        # каждое нажатие клавиши: окно берёт готовое по этому же ключу, и без
        # этой памяти сборка бежала по всем абзацам документа подряд.
        ready = self.ready.get((key, registry.notices(whole or text)))
        if ready is not None:
            return ready
        said = self.cache.get(key)
        if said is not None:
            return self._done(key, whole or text, said, flat, book)
        with self.lock:
            self.load()
            near = self._around(text, whole)
            # Свои же пометки модели не показываем: «организация признана
            # террористической» она честно отмечает как нарушение.
            quiet = registry.mute(flat)
            found = self._parse(self._ask(quiet, around=near), quiet)
            if len(found) > LIMIT:
                # Модель сорвалась в перечисление — даём один переспрос, и
                # только потом остаёмся со словарём.
                found = self._parse(
                    self._ask(quiet, strict=True, around=near), quiet)
                if len(found) > LIMIT:
                    found = []
            # Статья о призыве требует побуждения в самой фразе: рассказ о
            # чужих действиях призывом не бывает.
            found = [f for f in found
                     if f["law"] not in law.CALLS
                     or law.is_call(flat[f["start"]:f["end"]])]
            # Статья о сепаратизме требует названия земли: «пророссийские
            # тезисы» отделением ничего не объявляют.
            found = [f for f in found
                     if f["law"] not in law.NEEDS_PLACE
                     or law.has_place(flat[f["start"]:f["end"]])]
            # Чужая речь в кавычках — не слова автора.
            found = [f for f in found
                     if f["law"] in ALWAYS
                     or not self._quoted(flat, f["start"], f["end"])]
            if found:
                found = self._confirm(quiet, found)
            found += self._from_hints(flat, found)
        if len(self.cache) > 400:
            self.cache.clear()
            self.ready.clear()
        self.cache[key] = found
        return self._done(key, whole or text, found, flat, book)

    def _done(self, key, whole, said, flat, book):
        """Собрать ответ и запомнить его вместе с видом плашек."""
        out = self._settle([dict(f) for f in said], flat, book)
        if len(self.ready) > 400:
            self.ready.clear()
        self.ready[(key, registry.notices(whole))] = out
        return out

    def overall(self, text):
        """Признаки, которые видны только по всему тексту разом.

        Места ставятся по цитате, как и в обычном разборе, — но спрошено про
        целое, поэтому находятся предложения, которые сами по себе чисты.
        """
        flat = law.unmix(text)
        quiet = registry.mute(flat)
        said = self._say(
            WHOLE.format(text=quiet[:6000], items=law.wide_questions()),
            220, self.sampler, lines=True)
        found = self._parse(said, quiet)
        if len(found) > LIMIT:
            return []                # модель сорвалась в перечисление
        # Те же оговорки, что и в обычном разборе: призыв требует побуждения,
        # сепаратизм — названия земли.
        found = [f for f in found
                 if f["law"] not in law.CALLS
                 or law.is_call(flat[f["start"]:f["end"]])]
        found = [f for f in found
                 if f["law"] not in law.NEEDS_PLACE
                 or law.has_place(flat[f["start"]:f["end"]])]
        # Тот же переспрос, что и для обычных находок: свод охотно записывает
        # в подрыв доверия обычный разговор про блогеров.
        return self._confirm(quiet, found) if found else []

    def _settle(self, found, flat, book):
        """Добавить к ответу модели то, что считается без неё.

        Реестры и плашки зависят от всего документа, а не от одного абзаца,
        поэтому их нельзя запоминать вместе с ответом модели: плашка меняется
        чаще, чем текст абзаца.
        """
        found = self._merge(
            found + registry.mentions(flat, self.lang, whole=book))
        return [f for f in found if not self._noticed(book, f)]
