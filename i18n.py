"""Язык интерфейса. Ключ перевода — сама русская строка."""
from PySide6.QtCore import QLocale, QSettings

LANGS = ("ru", "en")

EN = {
    # панель
    "Новый": "New", "Открыть": "Open", "Сохранить": "Save",
    "Сохранить как…": "Save as…",
    "Жирный": "Bold", "Курсив": "Italic", "Заголовок": "Heading",
    "Список": "List", "Цитата": "Quote", "Код": "Code", "Ссылка": "Link",
    "Проверка": "Checking", "Настройки": "Settings",
    # лента
    "Главная": "Home", "Вставка": "Insert", "Рецензирование": "Review",
    "Вид": "View", "Файл": "File", "Начертание": "Font", "Абзац": "Paragraph",
    "Иллюстрации": "Illustrations", "Данные": "Data", "Масштаб": "Zoom",
    "Оформление": "Appearance", "Мельче": "Smaller", "Крупнее": "Larger",
    "100 %": "100%",
    "Реестры Минюста": "Ministry of Justice registries",
    "Обновить": "Update",
    "Выражения": "Expressions",
    "Опасные слова и обороты": "Dangerous words and phrases",
    "Открыть список": "Open the list", "Перечитать": "Reload",
    "Выражений: {n}": "Expressions: {n}", "пока пусто": "empty so far",
    "не загружены": "not downloaded",
    "не получилось": "failed",
    "Не получилось": "Failed",
    "Изменить": "Change",
    "Порядочный блокнот": "Decent Notepad",
    "подбор замены…": "finding a replacement…",
    "замену подобрать не удалось": "no replacement found",
    "Добавить пометку": "Add the notice",
    "Исправить всё": "Fix everything",
    "Исправление… {n} из {all}": "Fixing… {n} of {all}",
    "Текст изменился — исправление отменено":
        "The text changed, so nothing was fixed",
    "Иноагентов: {a} · нежелательных: {b} · запрещённых: {c} · террористических: {d}":
        "Foreign agents: {a} · undesirable: {b} · banned: {c} · terrorist: {d}",

    "Предпросмотр": "Preview",

    # режим проверки
    "Точно": "Accurate", "Быстро": "Fast", "Максимум": "Maximum",

    # размеры
    "Б": "B", "КБ": "KB", "МБ": "MB", "ГБ": "GB",

    # состояние
    "Проверка…": "Checking…", "Проверено": "Checked",
    "Проверено · нарушения: {red}, спорные места: {yellow}":
        "Checked · violations: {red}, borderline: {yellow}",
    "Проверено · нарушений нет": "Checked · nothing found",
    "Модель не установлена": "The model is not installed",
    "Знаков: {n}": "Characters: {n}",
    "Масштаб: {z}% · Знаков: {n}": "Zoom: {z}% · characters: {n}",

    # разбор
    "Нарушение закона": "Breaks the law",
    "Спорное место": "Borderline",
    "Заменить": "Replace", "Удалить": "Delete", "Оставить": "Keep",
    "Безопасной замены нет — фрагмент нужно удалить":
        "There is no safe wording — the fragment has to go",

    # файлы
    "Открыть текст": "Open a text",
    "Сохранить текст": "Save the text",
    "Документы (*.md *.markdown *.txt *.rtf *.docx *.odt *.pdf);;Все файлы (*)":
        "Documents (*.md *.markdown *.txt *.rtf *.docx *.odt *.pdf);;All files (*)",
    "Markdown (*.md *.markdown);;Текст (*.txt);;Word (*.docx);;"
    "OpenDocument (*.odt);;RTF (*.rtf)":
        "Markdown (*.md *.markdown);;Text (*.txt);;Word (*.docx);;"
        "OpenDocument (*.odt);;RTF (*.rtf)",
    "Картинка": "Picture",
    "Выбрать картинку": "Choose a picture",
    "Картинки (*.png *.jpg *.jpeg *.heic *.tiff *.gif *.bmp *.webp)":
        "Pictures (*.png *.jpg *.jpeg *.heic *.tiff *.gif *.bmp *.webp)",
    "Не удалось открыть картинку": "The picture could not be opened",
    "распознаю текст…": "reading the text…",
    "на картинке текста нет": "no text on the picture",
    "распознать не вышло: {why}": "could not read it: {why}",
    "Без названия": "Untitled",
    "Не сохранено": "Not saved",
    "Текст изменён. Сохранить перед закрытием?":
        "The text has changed. Save before closing?",
    "Не сохранять": "Don't save", "Понятно": "OK",

    # настройки
    "Реестры": "Registries",
    "Иноагенты, нежелательные, запрещённые и террористические организации":
        "Foreign agents, undesirable, banned and terrorist organisations",
    "Записей: {n}": "Records: {n}",
    "Обновление…": "Updating…",
    "Язык": "Language",
    "Оформление": "Appearance",
    "Цвета окна и текста": "Window and text colours",
    "Как в системе": "Match the system",
    "Светлое": "Light",
    "Тёмное": "Dark",
    "Удалить модель": "Delete the model",
    "Удалить {name}?": "Delete {name}?",
    "Проверка, режим «Быстро»": "Checking, Fast mode",
    "Проверка, режимы «Точно» и «Максимум»":
        "Checking, Accurate and Maximum modes",
    "Язык интерфейса": "Interface language",
    "Модель проверки": "Checking model",
    "Скачать": "Download", "Отмена": "Cancel",
    "нет, скачать {gb} ГБ": "not installed, {gb} GB",
    "Скачивание {name}": "Downloading {name}",
    "О программе {name}": "About {name}",
    "Проверка текста на нарушения закона": "Checks text against the law",

    # кодексы и законы в шапке карточки
    "УК РФ": "Criminal Code", "КоАП РФ": "Administrative Code",
    "ГК РФ": "Civil Code",
    "ФЗ-38": "Federal Law 38", "ФЗ-114": "Federal Law 114",
    "ФЗ-115": "Federal Law 115", "ФЗ-152": "Federal Law 152",
    "ФЗ-255": "Federal Law 255", "ФЗ-272": "Federal Law 272",
    "ФЗ-436": "Federal Law 436",
    "ст.": "art.", "ч.": "part",

    # наказания — они стоят в шапке карточки нарушения
    "до 1 года исправительных работ": "up to 1 year of correctional labour",
    "до 1 года лишения свободы": "up to 1 year in prison",
    "до 2 лет лишения свободы": "up to 2 years in prison",
    "до 5 лет лишения свободы": "up to 5 years in prison",
    "до 6 лет лишения свободы": "up to 6 years in prison",
    "до 7 лет лишения свободы": "up to 7 years in prison",
    "до 8 лет лишения свободы": "up to 8 years in prison",
    "до 10 лет лишения свободы": "up to 10 years in prison",
    "до 15 лет лишения свободы": "up to 15 years in prison",
    "до 20 лет лишения свободы": "up to 20 years in prison",
    "до пожизненного лишения свободы": "up to life in prison",
    "опровержение и возмещение вреда по суду":
        "a court-ordered retraction and damages",
    "удаление изображения и компенсация по суду":
        "court-ordered removal of the image and damages",
    "удаление сведений и компенсация по суду":
        "court-ordered removal of the data and damages",
    "штраф до 2 000 ₽ или арест до 15 суток":
        "a fine up to 2,000 ₽ or 15 days' detention",
    "штраф до 3 000 ₽ или арест до 15 суток":
        "a fine up to 3,000 ₽ or 15 days' detention",
    "штраф до 20 000 ₽ или арест до 15 суток":
        "a fine up to 20,000 ₽ or 15 days' detention",
    "штраф до 300 000 ₽ или арест до 15 суток":
        "a fine up to 300,000 ₽ or 15 days' detention",
    "штраф до 300 000 ₽ или арест до 30 суток":
        "a fine up to 300,000 ₽ or 30 days' detention",
    "штраф до 3 000 ₽ по статье 20.29 КоАП":
        "a fine up to 3,000 ₽ under article 20.29 of the Code of Administrative Offences",
    "штраф до 5 000 ₽": "a fine up to 5,000 ₽",
    "штраф до 15 000 ₽": "a fine up to 15,000 ₽",
    "штраф до 15 000 ₽ по статье 20.33 КоАП":
        "a fine up to 15,000 ₽ under article 20.33 of the Code of Administrative Offences",
    "штраф до 30 000 ₽": "a fine up to 30,000 ₽",
    "штраф до 50 000 ₽": "a fine up to 50,000 ₽",
    "штраф до 50 000 ₽ по статье 19.34 КоАП":
        "a fine up to 50,000 ₽ under article 19.34 of the Code of Administrative Offences",
    "штраф до 50 000 ₽ по статье 6.17 КоАП":
        "a fine up to 50,000 ₽ under article 6.17 of the Code of Administrative Offences",
    "штраф до 100 000 ₽": "a fine up to 100,000 ₽",
    "штраф до 100 000 ₽ по статье 13.11 КоАП":
        "a fine up to 100,000 ₽ under article 13.11 of the Code of Administrative Offences",
    "штраф до 200 000 ₽": "a fine up to 200,000 ₽",
    "штраф до 400 000 ₽": "a fine up to 400,000 ₽",
    "штраф до 500 000 ₽": "a fine up to 500,000 ₽",
    "штраф до 500 000 ₽ по статье 14.3 КоАП":
        "a fine up to 500,000 ₽ under article 14.3 of the Code of Administrative Offences",
    "уголовная ответственность": "criminal liability",
    "административная ответственность": "administrative liability",
    "гражданская ответственность": "civil liability",
    "ответственность по закону": "liability under the law",
}

_lang = None


def current():
    """Настройка важнее системного языка."""
    global _lang
    if _lang is None:
        saved = QSettings("local", "decent-notepad").value("lang", "")
        if saved in LANGS:
            _lang = saved
        else:
            # По умолчанию русский: проверяются российские законы, и язык
            # системы тут плохой советчик — на маке с английским интерфейсом
            # приложение открывалось не на том языке, что нужно.
            _lang = "en" if QLocale.system().language() == QLocale.English else "ru"
    return _lang


def set_current(lang):
    global _lang
    if lang in LANGS:
        _lang = lang
        QSettings("local", "decent-notepad").setValue("lang", lang)


def key_of(text):
    """Русский ключ по видимой надписи — для перевода собранного окна."""
    return text if text in EN else _BACK.get(text)


_BACK = {v: k for k, v in EN.items() if v != k}


def tf(fmt, **kw):
    return t(fmt).format(**kw)


def t(s):
    return EN.get(s, s) if current() == "en" else s
