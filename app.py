"""Порядочный блокнот — редактор с проверкой текста на нарушения закона.

Панель сверху одной строкой, дальше текст. Опасные места подчёркиваются по
ходу набора: красным то, что образует состав, жёлтым спорное. По нажатию на
подсветку показывается статья и предлагается безопасная формулировка.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (Qt, QEvent, QPoint, QRegularExpression, QSettings,
                            QThread, QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QGuiApplication,
                           QImage, QKeySequence, QPainter,
                           QRegularExpressionValidator,
                           QSyntaxHighlighter, QTextCharFormat, QTextCursor,
                           QTextDocument)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QTabBar, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

import i18n
import law
import models_store
import registry
import _style
from i18n import t, tf

FILTER = ("Документы (*.md *.markdown *.txt *.rtf *.docx *.odt *.pdf);;"
          "Все файлы (*)")
FILTER_SAVE = ("Markdown (*.md *.markdown);;Текст (*.txt);;Word (*.docx);;"
               "OpenDocument (*.odt);;RTF (*.rtf)")

ACCENT = "#5b7cfa"
RED, YELLOW = "#e5484d", "#d9a441"
AUTHOR, SITE, SITE_URL = "DrTonix", "bdub.space", "https://bdub.space"
# «Максимум» — та же модель, что и «Точно»: отличается не она, а работа.
# Снимаются смягчающие оговорки, и текст вдобавок читается целиком.
MODELS = {"fast": "mlx-community/Qwen3-8B-4bit",
          "good": "mlx-community/Qwen3-30B-A3B-4bit",
          "max": "mlx-community/Qwen3-30B-A3B-4bit"}

THEMES = ("system", "light", "dark")


def theme():
    """Что выбрано в настройках; «system» — вслед за оформлением macOS."""
    name = QSettings("local", "decent-notepad").value("theme", "system")
    return name if name in THEMES else "system"


def skin():
    """Какую палитру рисовать прямо сейчас."""
    name = theme()
    if name != "system":
        return name
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return "dark" if dark else "light"


class Markdown(QSyntaxHighlighter):
    """Разметка так, как она выглядит: заголовки крупнее, жирное жирным,
    ссылки и код своим цветом.

    Сами значки — решётки, звёздочки, галочки цитаты — не показываются: они
    сжимаются до нуля и красятся прозрачным. Из текста они при этом никуда не
    деваются, поэтому при копировании и сохранении разметка на месте.
    """

    def __init__(self, doc, colours):
        super().__init__(doc)
        self.ready = False               # первый разбор Qt сделает сам
        self.restyle(colours)
        self.ready = True

    def restyle(self, colours):
        """Перекраска под тему: правила собираются заново."""
        self.MARKS = colours["marks"]
        self.rules = []

        def rule(pattern, size=None, weight=None, colour=None, italic=False,
                 mono=False, mark=None, under=False, strike=False):
            f = QTextCharFormat()
            if size:
                f.setFontPointSize(size)
            if weight:
                f.setFontWeight(weight)
            if colour:
                f.setForeground(QColor(colour))
            f.setFontItalic(italic)
            if under:
                f.setFontUnderline(True)
            if strike:
                f.setFontStrikeOut(True)
            if mono:
                f.setFontFamilies(["SF Mono", "Menlo", "monospace"])
            self.rules.append((re.compile(pattern, re.M), f, mark))

        rule(r"^# .*", size=26, weight=QFont.Bold, colour=colours["bright"], mark=r"^#+\s*")
        rule(r"^## .*", size=21, weight=QFont.Bold, colour=colours["bright"], mark=r"^#+\s*")
        rule(r"^#{3,6} .*", size=17, weight=QFont.Bold, colour=colours["bright"], mark=r"^#+\s*")
        rule(r"\*\*[^*]+\*\*", weight=QFont.Bold, colour=colours["bright"], mark=r"\*\*")
        # Подчёркивание и зачёркивание пишут так же, как в Discord и Telegram.
        rule(r"__[^_\n]+__", under=True, colour=colours["text"], mark=r"__")
        rule(r"(?<!_)_[^_\n]+_(?!_)", italic=True, colour=colours["text"], mark=r"_")
        rule(r"~~[^~\n]+~~", strike=True, colour=colours["text"], mark=r"~~")
        rule(r"(?<!\*)\*[^*\n]+\*(?!\*)", italic=True, colour=colours["text"], mark=r"\*")
        rule(r"`[^`\n]+`", colour=colours["code"], mono=True, mark="`")
        rule(r"^\s*(?:[-*+]|\d+\.) ", colour=ACCENT)   # знак списка виден
        rule(r"^> .*", colour=colours["quote"], italic=True, mark=r"^>\s*")
        rule(r"\[[^\]]+\]\([^)]+\)", colour=ACCENT, mark=r"[\[\]()]|\([^)]+\)")
        rule(r"^(?:---|\*\*\*|___)\s*$", colour=self.MARKS)

        self.dim = QTextCharFormat()
        self.dim.setForeground(QColor(self.MARKS))

        # Знак разметки: прозрачный и без ширины. Убрать его из текста нельзя —
        # он нужен при копировании, — поэтому просто схлопываем.
        self.ghost = QTextCharFormat()
        self.ghost.setForeground(QColor(0, 0, 0, 0))
        # Кегль в единицу — знак сжимается почти в ноль. Отрицательный трекинг
        # пробовали и убрали: он утягивал следующую букву влево, и цифра в
        # начале строки уезжала за край.
        self.ghost.setFontPointSize(1)
        if self.ready:
            self.rehighlight()

    def highlightBlock(self, text):
        for rx, fmt, mark in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
                if not mark:
                    continue
                for g in re.finditer(mark, m.group(0), re.M):
                    at = m.start() + g.start()
                    self.setFormat(at, g.end() - g.start(), self.ghost)


class Editor(QTextEdit):
    """Текстовое поле: говорит, над каким местом курсор, и принимает картинки.

    Поле с оформлением, а не простое: иначе вставленную картинку негде
    показать, а по условию исправления должны стоять прямо под ней.
    """
    clicked = Signal(int)
    hovered = Signal(int)
    left = Signal()
    dropped = Signal(list)            # пути к брошенным файлам

    def __init__(self, *a):
        super().__init__(*a)
        self.setMouseTracking(True)
        self.setAcceptRichText(False)  # вставляем чужой текст без оформления
        self.setAcceptDrops(True)

    @staticmethod
    def _paths(event):
        data = event.mimeData()
        return [u.toLocalFile() for u in data.urls()] if data.hasUrls() else []

    def canInsertFromMimeData(self, data):
        return data.hasUrls() or super().canInsertFromMimeData(data)

    def dragEnterEvent(self, e):
        if self._paths(e):
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._paths(e):
            e.acceptProposedAction()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        paths = self._paths(e)
        if paths:
            e.acceptProposedAction()
            self.setTextCursor(self.cursorForPosition(e.position().toPoint()))
            self.dropped.emit(paths)
            return
        super().dropEvent(e)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.clicked.emit(self.cursorForPosition(e.pos()).position())

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        self.hovered.emit(self.cursorForPosition(e.pos()).position())

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self.left.emit()


class Reading(QThread):
    """Распознавание текста на картинке: Vision работает доли секунды, но
    держать на нём окно всё равно нельзя."""
    done = Signal(str, str)           # текст, ошибка

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            import vision
            self.done.emit(vision.read_image(self.path), "")
        except Exception as e:
            self.done.emit("", str(e))


class Worker(QThread):
    """Проверка абзацев в фоне: набор текста не должен ждать модель."""
    ready = Signal(int, str, list)     # номер абзаца, его текст, находки
    failed = Signal(str)

    def __init__(self, checker, jobs, whole=""):
        super().__init__()
        self.checker, self.jobs, self.whole = checker, jobs, whole
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for number, text in self.jobs:
            if self._stop:
                return
            try:
                self.ready.emit(number, text,
                                self.checker.check(text, self.whole))
            except Exception as e:
                self.failed.emit(str(e))
                return


class Download(QThread):
    """Скачивание модели: гигабайты идут мимо главного потока."""
    step = Signal("qint64", "qint64")     # 32 бита не хватает: модели по 16 ГБ
    done = Signal(bool, str)

    def __init__(self, repo):
        super().__init__()
        self.repo, self._stop = repo, False

    def stop(self):
        self._stop = True

    def run(self):
        import models_store
        try:
            ok = models_store.download(self.repo, self.step.emit,
                                       lambda: self._stop)
            self.done.emit(ok, "")
        except Exception as e:
            self.done.emit(False, str(e))


class Registries(QThread):
    """Обновление реестров Минюста в фоне: сеть не должна морозить окно."""
    line = Signal(str)
    done = Signal(dict)
    failed = Signal(str)

    def run(self):
        import registry
        try:
            registry.update(log=self.line.emit)
            self.done.emit(registry.counts())
        except Exception as e:
            self.failed.emit(str(e))


class Rewrite(QThread):
    """Замена подбирается по требованию: она нужна только там, куда навели."""
    done = Signal(str)

    def __init__(self, checker, quote, law_id, context=""):
        super().__init__()
        self.checker, self.quote, self.law_id = checker, quote, law_id
        self.context = context

    def run(self):
        try:
            self.done.emit(
                self.checker.rewrite(self.quote, self.law_id, self.context))
        except Exception:
            self.done.emit("")


class FixAll(QThread):
    """Замены сразу для всех находок: по одной на каждую, как при наведении.

    Считается в потоке и по очереди — модель всё равно отвечает по одному
    запросу, а окно за это время должно оставаться живым.
    """
    step = Signal(int)
    ready = Signal(list)

    def __init__(self, checker, jobs):
        super().__init__()
        self.checker, self.jobs, self.stopped = checker, jobs, False

    def stop(self):
        self.stopped = True

    def run(self):
        out = []
        for n, job in enumerate(self.jobs, 1):
            if self.stopped:
                return
            self.step.emit(n)
            found = job["found"]
            safe = found["safe"]
            if not safe:
                try:
                    safe = (self.checker.redo(job["para"], job["spots"],
                                              job["keep"])
                            if "para" in job else
                            self.checker.rewrite(job["quote"], found["law"],
                                                 job["context"]))
                except Exception:
                    safe = ""
            if not safe and "para" in job:
                # Перепись абзаца не вышла — правим места по одному, иначе
                # заход проходит впустую и текст остаётся как был.
                for one, (quote, _fix, _law) in zip(job["each"], job["spots"]):
                    try:
                        near = self.checker.rewrite(quote, one["law"],
                                                    job["context"])
                    except Exception:
                        near = ""
                    if near:
                        out.append((one, near))
                continue
            if safe:
                out.append((found, safe))
        self.ready.emit(out)


class Wide(QThread):
    """Свод по всему тексту: что он говорит целиком, а не по абзацам."""
    ready = Signal(str, list)

    def __init__(self, checker, text):
        super().__init__()
        self.checker, self.text = checker, text

    def run(self):
        try:
            self.ready.emit(self.text, self.checker.overall(self.text))
        except Exception:
            self.ready.emit(self.text, [])


class Popup(QWidget):
    """Карточка над подсвеченным местом: все статьи этого места сразу.

    Одна фраза нарушает несколько норм, и раньше в карточку попадала только
    первая находка — на «я трахаю несовершеннолетних» человек видел «тему под
    регулированием», а уголовная статья оставалась под ней невидимой.
    """

    MOST = 3
    WIDE = 460                           # ширина текста в карточке
    left = Signal()

    def __init__(self, parent):
        # Своё окно, а не часть главного: внутри окна карточку резало нижним
        # краем, а места под последними строками не хватало вовсе.
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.anchor = None
        self.at = (QPoint(0, 0), 0)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("pop")
        shell.addWidget(card)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Статьи прокручиваются, замена и кнопка — нет: в невысоком окне
        # прокрутка съедала кнопку, и нажать на замену было нечем.
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("popScroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inside = QWidget(); self.inside.setObjectName("popInside")
        self.scroll.setWidget(self.inside)
        outer.addWidget(self.scroll, 1)
        self.box = QVBoxLayout(self.inside)
        self.box.setContentsMargins(14, 12, 14, 6)
        self.box.setSpacing(6)
        self.rows = []
        for _ in range(self.MOST):
            head = QLabel(); head.setObjectName("popLaw")
            text = QLabel(); text.setObjectName("popWhy")
            for w in (head, text):
                w.setWordWrap(True)
                w.setFixedWidth(self.WIDE)
                self.box.addWidget(w)
            self.rows.append((head, text))
        self.box.addStretch()

        pinned = QWidget(); pinned.setObjectName("popInside")
        bottom = QVBoxLayout(pinned)
        bottom.setContentsMargins(14, 6, 14, 12)
        bottom.setSpacing(6)
        self.safe = QLabel(); self.safe.setObjectName("popSafe")
        self.safe.setWordWrap(True); self.safe.setFixedWidth(self.WIDE)
        bottom.addWidget(self.safe)
        row = QHBoxLayout(); row.setSpacing(8); row.addStretch()
        self.apply = QPushButton(); self.apply.setObjectName("tool")
        row.addWidget(self.apply)
        bottom.addLayout(row)
        outer.addWidget(pinned)
        self.pinned = pinned
        self.hide()

    def leaveEvent(self, e):
        # Карточка накрывает текст под собой, и пока курсор на ней, окно с
        # текстом о нём ничего не знает: без этого она висела, пока человек не
        # заденет текст снова.
        super().leaveEvent(e)
        self.left.emit()

    EDGE = 12                            # отступ карточки от края окна

    def _tall(self, label):
        """Сколько места займёт надпись с переносами по словам."""
        if not label.isVisible() or not label.text():
            return 0
        box = label.fontMetrics().boundingRect(
            0, 0, self.WIDE, 10000, int(Qt.TextWordWrap), label.text())
        return box.height()

    def _measure(self):
        """Высота карточки по её содержимому.

        sizeHint у надписи с переносами врёт: он считает по одной строке, и
        замена в две строки обрезалась снизу — текст выглядел рваным. Поэтому
        каждой надписи сначала задаём её настоящую высоту.
        """
        for label in [w for pair in self.rows for w in pair] + [self.safe]:
            label.setMinimumHeight(self._tall(label))
        rows = self.box.spacing()
        body = sum(self._tall(w) for pair in self.rows for w in pair)
        body += rows * max(0, sum(1 for pair in self.rows
                                  for w in pair if w.isVisible()) - 1)
        top, _l, _r, low = self.box.getContentsMargins()
        body += top + low
        tail = self._tall(self.safe) + self.apply.sizeHint().height()
        margins = self.pinned.layout().getContentsMargins()
        tail += margins[1] + margins[3] + self.pinned.layout().spacing()
        return body + tail + 4

    def place(self, line=None, height=0):
        """Поставить карточку под строкой — и не на неё саму.

        Место считается по экрану, а не по окну: карточка — отдельное окно и
        спокойно свешивается ниже приложения, поэтому текст остаётся видным.
        Над строкой встаёт, только если снизу нет места на самом экране.
        """
        if line is None:
            line, height = self.at
        self.at = (line, height)
        screen = QGuiApplication.screenAt(line) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.setFixedWidth(self.WIDE + 28)
        want = self._measure()
        self.setFixedHeight(min(want, area.height() - 2 * self.EDGE))

        below = line.y() + height + 8
        above = line.y() - self.height() - 8
        if below + self.height() <= area.bottom() - self.EDGE:
            top = below
        elif above >= area.top() + self.EDGE:
            top = above
        else:
            top = max(area.top() + self.EDGE,
                      area.bottom() - self.height() - self.EDGE)
        right = area.right() - self.width() - self.EDGE
        left = min(max(area.left() + self.EDGE, line.x()),
                   max(area.left() + self.EDGE, right))
        # setGeometry, а не move: move у окна ставит рамку, а у безрамочного
        # окна macOS всё равно считает рамку в двадцать точек — карточка
        # уезжала на эту высоту вверх и ложилась на подсвеченную строку.
        self.setGeometry(left, top, self.width(), self.height())

    @staticmethod
    def _where(item):
        act = t(item.get("act", ""))
        article = item.get("article", "").replace("ч.", t("ч."))
        return f'{act} {t("ст.")} {article}' if article else act

    def show_for(self, items, anchor):
        lang = i18n.current()
        items = sorted(items, key=lambda f: f["risk"] != "red")[:self.MOST]
        for (head, text), f in zip(self.rows, items):
            item = law.BY_ID.get(f["law"], {})
            red = f["risk"] == "red"
            title = t("Нарушение закона") if red else t("Спорное место")
            head.setText(f'{title} · {self._where(item)} · '
                         f'{t(item.get("penalty", ""))}')
            head.setStyleSheet(f"color: {RED if red else YELLOW}")
            # Дословная норма, а не пересказ: по ней видно, что именно не так.
            text.setText(law.statute(item, lang))
            head.setVisible(True); text.setVisible(True)
        for head, text in self.rows[len(items):]:
            head.setVisible(False); text.setVisible(False)

        # Действие — по самой тяжёлой находке, у которой оно вообще есть.
        act = next((f for f in items if f["safe"]), items[0])
        item = law.BY_ID.get(act["law"], {})
        self.action = act
        if act.get("where"):
            # Пометку закон требует добавить, а не заменить ею упоминание.
            self.safe.setText("+ " + act["safe"])
            self.apply.setText(t("Добавить пометку"))
            self.apply.setEnabled(True)
        elif act["safe"]:
            self.safe.setText("→ " + act["safe"])
            self.apply.setText(t("Изменить"))
            self.apply.setEnabled(True)
        else:
            # Замену подбирает модель — пока ждём, кнопка недоступна.
            self.safe.setText("→ " + t("подбор замены…"))
            self.apply.setText(t("Изменить"))
            self.apply.setEnabled(False)
        self.anchor = anchor      # размер и место считает place()


class TabShut(QPushButton):
    """Кнопка вкладки: точка, пока есть несохранённое, и крестик под курсором.

    Точка стояла в самом названии и висела выше строки — у неё своя высота в
    шрифте. В кнопке она рисуется по центру ярлычка и не спорит с текстом.
    """

    def __init__(self):
        super().__init__("✕")
        self.setObjectName("tabShut")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)
        self.dirty = False

    def show_dirty(self, dirty):
        self.dirty = dirty
        self._draw()

    def _draw(self):
        self.setText("●" if self.dirty and not self.underMouse() else "✕")

    def enterEvent(self, e):
        super().enterEvent(e)
        self._draw()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._draw()


class Zoom(QFrame):
    """Плашка масштаба поверх текста: показалась, дала нажать и ушла.

    В строке состояния масштабу не место — он к длине текста отношения не
    имеет, а рядом с ней читался как ещё одна его мера.
    """
    LOW, HIGH, STEP = 50, 400, 10
    STAY = 2500                          # сколько висит без внимания, мс

    picked = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("zoom")
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(2)
        self.less = QPushButton("−"); self.less.setObjectName("zoomStep")
        self.more = QPushButton("+"); self.more.setObjectName("zoomStep")
        # Поле, а не список: значение вводится любое, а не из готовых.
        self.now = QLineEdit("100%"); self.now.setObjectName("zoomNow")
        self.now.setAlignment(Qt.AlignCenter)
        self.now.setFixedWidth(58)
        self.now.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"\d{1,3}\s*%?")))
        for w in (self.less, self.now, self.more):
            row.addWidget(w)
        for b in (self.less, self.more):
            b.setCursor(Qt.PointingHandCursor)
        self.less.clicked.connect(lambda: self.picked.emit(self._step(-1)))
        self.more.clicked.connect(lambda: self.picked.emit(self._step(1)))
        self.now.returnPressed.connect(self._typed)
        self.value = 100
        self.fade = QTimer(self)
        self.fade.setSingleShot(True)
        self.fade.setInterval(self.STAY)
        self.fade.timeout.connect(self._maybe_hide)
        self.hide()

    def _step(self, way):
        return max(self.LOW, min(self.HIGH, self.value + way * self.STEP))

    def _typed(self):
        digits = re.sub(r"\D", "", self.now.text())
        # Сначала снимаем ввод, потом сообщаем: пока поле в работе, плашка не
        # трогает его текст, и в нём оставалось введённое «999» вместо 400.
        self.now.clearFocus()
        self.parentWidget().editor.setFocus()
        self.picked.emit(max(self.LOW, min(self.HIGH, int(digits)))
                         if digits else self.value)

    def _maybe_hide(self):
        if self.underMouse() or self.now.hasFocus():
            self.fade.start()
            return
        self.hide()

    def show_at(self, value, corner):
        self.value = value
        if not self.now.hasFocus():
            self.now.setText(f"{value}%")
        self.less.setEnabled(value > self.LOW)
        self.more.setEnabled(value < self.HIGH)
        self.adjustSize()
        room = self.parentWidget()
        left = min(corner.x() - self.width(), room.width() - self.width() - 12)
        self.move(max(12, left), max(12, corner.y()))
        self.show()
        self.raise_()
        self.fade.start()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("Порядочный блокнот"))
        self.resize(1040, 720)
        self.settings = QSettings("local", "decent-notepad")
        saved = int(self.settings.value("zoom", 100) or 100)
        self.scale = max(Zoom.LOW, min(Zoom.HIGH, saved))
        self.docs = {}                   # поле ввода -> состояние документа
        self.worker = None
        self.checker = None
        self._alive = []
        self._downloading = {}

        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        box = QVBoxLayout(root)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)
        box.addWidget(self._toolbar())

        # Документы лежат по вкладкам: «Новый» больше ничего не стирает.
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs")
        self.tabs.setDocumentMode(True)

        self.tabs.setMovable(True)
        self.tabs.currentChanged.connect(self._switched)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBar().setElideMode(Qt.ElideRight)
        box.addWidget(self.tabs, 1)

        self.pop = Popup(self)
        self.zoomer = Zoom(self)
        self.zoomer.picked.connect(self.set_zoom)

        row = QHBoxLayout(); row.setContentsMargins(6, 0, 6, 0); row.setSpacing(12)
        # Слева — что с проверкой и что она нашла одной строкой; справа только
        # длина текста. Раньше «Проверено» и «Нарушения: 2» стояли по разным
        # краям окна и читались как две несвязанные надписи.
        self.status = QLabel(); self.status.setObjectName("status")
        self.count = QLabel(); self.count.setObjectName("count")
        self.fixall = QPushButton(); self.fixall.setObjectName("fixall")
        self.fixall.setText(t("Исправить всё"))
        self.fixall.clicked.connect(self._fix_all)
        self.fixall.hide()
        row.addWidget(self.status); row.addWidget(self.fixall)
        row.addStretch(); row.addWidget(self.count)
        box.addLayout(row)

        # Прячем карточку не сразу: курсор идёт по строке через пробелы и
        # знаки, и без задержки она гаснет и зажигается на каждом промежутке.
        self.rounds = 0          # сколько ещё заходов «исправить всё» осталось
        self.was = 0             # сколько находок было в начале захода
        self.fade = QTimer(self)
        self.fade.setSingleShot(True)
        self.fade.setInterval(220)
        self.fade.timeout.connect(self._hide_pop)
        self.pop.left.connect(self._maybe_hide)

        self.wait = QTimer(self)
        self.wait.setSingleShot(True)
        self.wait.setInterval(1200)       # проверяем, когда человек остановился
        self.wait.timeout.connect(self._recheck)

        for keys, slot in (("Ctrl+T", self.new_file),
                           ("Ctrl+W", lambda: self.close_tab(
                               self.tabs.currentIndex()))):
            act = QAction(self); act.setShortcut(QKeySequence(keys))
            act.triggered.connect(slot); self.addAction(act)
        for keys, step in (("Ctrl+=", 1), ("Ctrl++", 1), ("Ctrl+-", -1),
                           ("Ctrl+0", 0)):
            act = QAction(self); act.setShortcut(QKeySequence(keys))
            act.triggered.connect(lambda _=False, d=step: self.zoom(d))
            self.addAction(act)
        self.add_tab()
        self.apply_theme()
        # macOS переключает оформление на ходу — окно должно идти следом.
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            lambda _s: self.apply_theme())
        self._retitle()
        QTimer.singleShot(0, self._start_checker)

    # ── вкладки

    @property
    def editor(self):
        return self.tabs.currentWidget()

    @property
    def doc(self):
        return self.docs.get(self.tabs.currentWidget(), {})

    @property
    def md(self):
        return self.doc.get("md")

    @property
    def path(self):
        return self.doc.get("path")

    @path.setter
    def path(self, value):
        self.doc["path"] = value

    @property
    def pictures(self):
        return self.doc.setdefault("pictures", {})

    @property
    def found(self):
        return self.doc.setdefault("found", {})

    @found.setter
    def found(self, value):
        self.doc["found"] = value

    @property
    def sure(self):
        return self.doc.setdefault("sure", {})

    @sure.setter
    def sure(self, value):
        self.doc["sure"] = value

    def add_tab(self, text="", path=None):
        """Ещё один документ рядом, а не вместо."""
        ed = Editor()
        ed.setObjectName("editor")
        ed.setFrameShape(QFrame.NoFrame)
        ed.setTabStopDistance(28)
        ed.textChanged.connect(self._typed)
        ed.clicked.connect(self._clicked)
        ed.hovered.connect(self._hovered)
        ed.left.connect(self._maybe_hide)
        ed.dropped.connect(self._dropped)
        ed.verticalScrollBar().valueChanged.connect(self._drop_pop)
        self.docs[ed] = {"path": path, "found": {}, "sure": {}, "pictures": {},
                         "clean": text,
                         "md": Markdown(ed.document(), _style.palette(skin()))}
        if text:
            ed.setPlainText(text)
        at = self.tabs.addTab(ed, "")
        # Крестик ставим своим виджетом: встроенный macOS держит слева и
        # рисует вокруг него серый квадрат.
        shut = TabShut()
        shut.clicked.connect(
            lambda _=False, w=ed: self.close_tab(self.tabs.indexOf(w)))
        bar = self.tabs.tabBar()
        bar.setTabButton(at, QTabBar.LeftSide, None)
        bar.setTabButton(at, QTabBar.RightSide, shut)
        self.tabs.setCurrentIndex(at)
        self._show_tabs()
        self._relayout()
        self._retitle(ed)
        ed.setFocus()
        return ed

    def _warn(self, text):
        box = QMessageBox(self)
        box.setStyleSheet(_style.sheet(skin()))
        box.setIcon(QMessageBox.NoIcon)
        box.setWindowTitle(t("Не получилось"))
        box.setText(text)
        box.setDefaultButton(box.addButton(t("Понятно"), QMessageBox.AcceptRole))
        box.exec()

    def dirty(self, ed=None):
        """Текст отличается от сохранённого.

        Флаг самого документа сюда не годится: подсветка разметки помечает
        его изменённым, едва открыв файл, и новая вкладка сразу считалась
        непустой.
        """
        ed = ed or self.editor
        doc = self.docs.get(ed)
        return bool(doc) and ed.toPlainText() != doc.get("clean", "")

    def close_tab(self, at):
        ed = self.tabs.widget(at)
        if ed is None:
            return
        if self.dirty(ed) and not self._offer_save(ed):
            return
        self.tabs.removeTab(at)
        self.docs.pop(ed, None)
        ed.deleteLater()
        if not self.tabs.count():
            self.add_tab()
        self._show_tabs()

    def _show_tabs(self):
        """Одна вкладка — полоска не нужна, как в любом редакторе."""
        self.tabs.tabBar().setVisible(self.tabs.count() > 1)

    def _offer_save(self, ed):
        """Спросить про несохранённое. False — человек передумал закрывать."""
        box = QMessageBox(self)
        box.setStyleSheet(_style.sheet(skin()))
        box.setIcon(QMessageBox.NoIcon)
        box.setWindowTitle(t("Не сохранено"))
        box.setText(t("Текст изменён. Сохранить перед закрытием?"))
        yes = box.addButton(t("Сохранить"), QMessageBox.YesRole)
        no = box.addButton(t("Не сохранять"), QMessageBox.DestructiveRole)
        box.addButton(t("Отмена"), QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is yes:
            self.tabs.setCurrentWidget(ed)
            self.save_file()
            return not self.dirty(ed)
        return box.clickedButton() is no

    def _switched(self, _at):
        """Перешли на другую вкладку: подсветка и проверка — её."""
        if self.editor is None:
            return
        self._drop_pop()
        self._relayout()
        self._retitle()
        self._instant()
        self._recheck()

    def _cross(self, tone, name):
        """Крестик закрытия вкладки: Qt в стилях понимает только файл."""
        store = Path.home() / "Library" / "Application Support" / "decent-notepad"
        store.mkdir(parents=True, exist_ok=True)
        path = store / f"cross-{name}.png"
        dot = QImage(24, 24, QImage.Format_ARGB32)
        dot.fill(Qt.transparent)
        p = QPainter(dot)
        p.setRenderHint(QPainter.Antialiasing)
        pen = p.pen(); pen.setColor(QColor(tone)); pen.setWidthF(2.4)
        pen.setCapStyle(Qt.RoundCap); p.setPen(pen)
        p.drawLine(7, 7, 17, 17); p.drawLine(17, 7, 7, 17)
        p.end()
        dot.save(str(path))
        return path.as_posix()

    def apply_theme(self):
        """Палитра окна и подсветки разметки под выбранную тему."""
        colours = _style.palette(skin())
        self.setStyleSheet(_style.sheet(
            skin(), self.text_size,
            self._cross(colours["faint"], "off"),
            self._cross(colours["bright"], "on")))
        self.pop.setStyleSheet(_style.sheet(skin()))
        for doc in self.docs.values():
            doc["md"].restyle(colours)
        self._paint()

    BASE = 15                            # размер текста при ста процентах

    @property
    def text_size(self):
        return max(9, round(self.BASE * self.scale / 100))

    def zoom(self, step):
        """⌘+ и ⌘− по ступеням, ⌘0 — обратно к ста процентам."""
        self.set_zoom(100 if step == 0 else self.zoomer._step(step))

    def set_zoom(self, value):
        self.scale = value
        self.settings.setValue("zoom", value)
        self.apply_theme()
        corner = self.editor.mapTo(self, QPoint(self.editor.width() - 12, 12))
        self.zoomer.show_at(value, corner)

    # ── панель

    def _tool(self, text, slot, tip_key=None, shortcut=None):
        b = QPushButton(t(text)); b.setObjectName("tool")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        if shortcut:
            act = QAction(self); act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot); self.addAction(act)
        return b

    def _toolbar(self):
        """Одна строка: пунктов мало, раскладывать их по вкладкам незачем."""
        bar = QFrame(); bar.setObjectName("bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(2)
        for text, slot, keys in (("Новый", self.new_file, "Ctrl+N"),
                                 ("Открыть", self.open_file, "Ctrl+O"),
                                 ("Сохранить", self.save_file, "Ctrl+S")):
            row.addWidget(self._tool(text, slot, shortcut=keys))
        row.addWidget(self._divider())
        for text, wrap, keys in (("Жирный", "**", "Ctrl+B"),
                                 ("Курсив", "*", "Ctrl+I"),
                                 ("Код", "`", None)):
            row.addWidget(self._tool(text, lambda _=False, w=wrap: self._wrap(w),
                                     shortcut=keys))
        for text, prefix in (("Заголовок", "## "), ("Список", "- "), ("Цитата", "> ")):
            row.addWidget(self._tool(text, lambda _=False, p=prefix: self._prefix(p)))
        row.addWidget(self._divider())
        row.addWidget(self._tool("Картинка", self.add_image))
        row.addStretch()
        row.addWidget(self._modes())
        row.addWidget(self._tool("Настройки", self.open_settings))
        return bar

    def _modes(self):
        """Переключатель проверки — такой же, как в Дубле и Конспекте."""
        frame = QFrame(); frame.setObjectName("segment")
        row = QHBoxLayout(frame)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.modes = {}
        for key, name in (("fast", "Быстро"), ("good", "Точно"),
                          ("max", "Максимум")):
            b = QPushButton(t(name)); b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._mode_changed(k))
            self.modes[key] = b
            row.addWidget(b)
        return frame

    def set_mode(self, key):
        for code, b in self.modes.items():
            b.setChecked(code == key)

    def _divider(self):
        s = QFrame(); s.setObjectName("sep")
        s.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        s.setFixedWidth(1)
        return s

    # ── правка текста

    def _wrap(self, mark):
        c = self.editor.textCursor()
        if c.hasSelection():
            c.insertText(mark + c.selectedText() + mark)
        else:
            c.insertText(mark * 2)
            c.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(mark))
            self.editor.setTextCursor(c)

    def _prefix(self, mark):
        c = self.editor.textCursor()
        c.movePosition(QTextCursor.StartOfBlock)
        c.insertText(mark)

    # ── проверка

    def _start_checker(self):
        import check
        key = self.settings.value("model", "good")
        self.set_mode(key)
        repo = MODELS[key]
        if not models_store.is_ready(repo, 4.5 if key == "fast" else 16.0):
            self.busy = False
            self.status.setText(t("Модель не установлена"))
            self.checker = None
            return
        # «Максимум» — то же, что «Точно», плюс чтение всего текста целиком.
        self.hard = key == "max"
        self.wide_for = None
        if self.checker is None or self.checker.model_id != repo:
            self.checker = check.Checker(repo, i18n.current())
        self._recheck()

    def _mode_changed(self, key):
        self.settings.setValue("model", key)
        self.set_mode(key)
        self.found.clear()
        self._start_checker()

    def _typed(self):
        # Правишь отмеченное место — подсветка уходит сразу, а не через секунду
        # после того, как модель заново проверит абзац.
        number = self.editor.textCursor().blockNumber()
        if self.found.pop(number, None) is not None:
            self.pop.hide()
        # Строк стало больше или меньше — все номера ниже съехали, и находки
        # показывают на чужие места. Плашка иноагента сверху сдвигает весь
        # текст на две строки разом.
        lines = self.editor.document().blockCount()
        if lines != getattr(self.editor, "lines", lines):
            self.found.clear()
            self._drop_pop()
        self.editor.lines = lines
        self._retitle()
        self._instant()
        self.wait.start()

    def _instant(self):
        """Что видно без модели: требования к оформлению. Считается за
        миллисекунды, поэтому идёт прямо по ходу набора."""
        self.sure = {n: law.certain(law.unmix(txt), i18n.current())
                     for n, txt in self._blocks()}
        self._paint()

    PICTURE = "\ufffc"                # место картинки внутри текста

    def _distance(self, job):
        """Насколько абзац далёк от того места, куда человек смотрит."""
        number, _text = job
        block = self.editor.document().findBlockByNumber(number)
        if not block.isValid():
            return 10 ** 9
        box = self.editor.document().documentLayout().blockBoundingRect(block)
        top = box.top() - self.editor.verticalScrollBar().value()
        height = self.editor.viewport().height()
        if -box.height() <= top <= height:
            return 0                     # на виду
        return int(abs(top) if top < 0 else top - height)

    def _blocks(self):
        """Абзацы документа: номер и текст, пустые пропускаем."""
        out, b = [], self.editor.document().firstBlock()
        while b.isValid():
            # Абзац из одной картинки проверять нечего — проверяем то, что
            # под ней распозналось. Плашку — тем более: она и есть исполнение
            # требования закона.
            if b.text().replace(self.PICTURE, "").strip() \
                    and not registry.is_plaque(b.text()):
                out.append((b.blockNumber(), b.text()))
            b = b.next()
        return out

    def _recheck(self):
        if self.checker is None:
            self.busy = False        # ждать нечего: модели нет
            self._count()
            return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        whole = self.editor.toPlainText()
        jobs = [(n, txt) for n, txt in self._blocks()
                if self.checker.key(txt, whole) not in self.checker.cache]
        # Сначала то, что человек видит: на длинном тексте подсветка
        # появляется сразу, а не после того, как проверится весь документ.
        jobs.sort(key=self._distance)
        alive = {n for n, _ in self._blocks()}
        self.found = {n: v for n, v in self.found.items() if n in alive}
        for n, txt in self._blocks():                 # готовое берём из памяти
            if self.checker.key(txt) in self.checker.cache:
                # Реестры и плашки считаются заново: модель для этого абзаца
                # уже отвечала, а плашка могла поменяться минуту назад.
                self.found[n] = self.checker.check(txt, whole)
        self._paint()
        if not jobs:
            self.busy = False
            self._count()
            self._keep_fixing()
            return
        self.busy = True
        self._count()
        self.worker = Worker(self.checker, jobs, whole)
        self.worker.ready.connect(self._got)
        self.worker.failed.connect(lambda m: self.status.setText(m[:80]))
        self.worker.finished.connect(lambda w=self.worker: self._done(w))
        self._alive.append(self.worker)
        self.worker.finished.connect(lambda w=self.worker: self._alive.remove(w))
        self.worker.start()

    def _done(self, worker):
        """Проверка закончилась — но только если это она и была.

        Новая проверка останавливает предыдущую, и та тоже сообщает, что
        закончила. Пока её слушали, «Проверено» появлялось на середине работы,
        а «Исправить всё» бралось за половину находок.
        """
        if worker is not self.worker:
            return
        text = self.editor.toPlainText()
        if getattr(self, "hard", False) and self.checker and text.strip() \
                and getattr(self, "wide_for", None) != text:
            # «Максимум»: абзацы разобраны, остался свод по всему тексту.
            self.wide_for = text
            job = self._keep(Wide(self.checker, text))
            job.ready.connect(self._got_wide)
            job.start()
            return                    # проверка ещё идёт, приговора нет
        self.busy = False
        self._count()
        self._keep_fixing()

    def _got_wide(self, text, found):
        """Находки свода ложатся в те абзацы, где стоят их предложения."""
        if self.editor.toPlainText() == text:
            doc = self.editor.document()
            for f in found:
                block = doc.findBlock(f["start"])
                if registry.is_plaque(block.text()):
                    continue          # плашка — не текст человека
                here = self.found.setdefault(block.blockNumber(), [])
                near = dict(f, start=max(0, f["start"] - block.position()),
                            end=min(f["end"] - block.position(),
                                    len(block.text())))
                if near["end"] <= near["start"]:
                    continue
                if any(g["law"] == near["law"] and g["start"] < near["end"]
                       and near["start"] < g["end"] for g in here):
                    continue
                here.append(near)
                here.sort(key=lambda x: x["start"])
            self._paint()
        self.busy = False
        self._count()
        self._keep_fixing()

    def _got(self, number, text, found):
        """Ответ принимаем, только если абзац остался на месте.

        Пока модель считала, текст могли поправить — и вставка плашки сдвигает
        все абзацы разом. Тогда ответ про третий абзац ложился на пятый, и
        подсветка указывала на середину чужого слова.
        """
        if self.editor.document().findBlockByNumber(number).text() != text:
            return
        self.found[number] = found
        self._paint()

    def _paint(self):
        """Подсветка находок. Тексту она не принадлежит: extraSelections живут
        поверх, поэтому разметка Markdown остаётся нетронутой.

        Одно место — одна заливка. Раньше на фразу, нарушающую три статьи,
        ложились три полупрозрачных слоя, и цвет выходил бурым, а границы
        находок мешались друг с другом.
        """
        bar = self.editor.verticalScrollBar()
        was = bar.value()
        doc = self.editor.document()
        marks = []
        for number, items in self._marks().items():
            block = doc.findBlockByNumber(number)
            if not block.isValid():
                continue
            size = len(block.text())
            level = bytearray(size)
            for f in items:
                want = 2 if f["risk"] == "red" else 1
                for at in range(max(0, f["start"]), min(size, f["end"])):
                    if level[at] < want:
                        level[at] = want
            at = 0
            while at < size:
                if not level[at]:
                    at += 1
                    continue
                end = at
                while end < size and level[end] == level[at]:
                    end += 1
                sel = QTextEdit.ExtraSelection()
                fmt = QTextCharFormat()
                colour = QColor(RED if level[at] == 2 else YELLOW)
                fmt.setUnderlineColor(colour)
                fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                tint = QColor(colour); tint.setAlpha(40)
                fmt.setBackground(tint)
                sel.format = fmt
                cur = QTextCursor(block)
                cur.setPosition(block.position() + at)
                cur.setPosition(block.position() + end, QTextCursor.KeepAnchor)
                sel.cursor = cur
                marks.append(sel)
                at = end
        self.editor.setExtraSelections(marks)
        # Место в тексте не должно уезжать от того, что проверка досчиталась.
        bar.setValue(was)
        self._count()

    def _marks(self):
        """Правила и модель вместе. Если места пересекаются, остаётся находка
        модели: она знает, о чём текст, а правило знает только слово."""
        out = {}
        for number in set(self.found) | set(self.sure):
            model = self.found.get(number, [])
            taken = [(f["start"], f["end"]) for f in model]
            rules = [f for f in self.sure.get(number, [])
                     if not any(a < f["end"] and f["start"] < b for a, b in taken)]
            out[number] = sorted(model + rules, key=lambda f: f["start"])
        return out

    def _count(self):
        """Что с проверкой и что она нашла — одной строкой.

        Пока проверка идёт, приговора нет: «нарушений нет» рядом с «проверка…»
        противоречит сам себе — он о прошлом тексте.
        """
        marks = self._marks()
        red = sum(1 for v in marks.values() for f in v if f["risk"] == "red")
        yellow = sum(1 for v in marks.values() for f in v if f["risk"] != "red")
        self.count.setText(tf("Знаков: {n}", n=len(self.editor.toPlainText())))
        if getattr(self, "busy", False):
            self.status.setText(t("Проверка…"))
        elif red or yellow:
            self.status.setText(tf("Проверено · нарушения: {red}, "
                                   "спорные места: {yellow}", red=red, yellow=yellow))
        else:
            self.status.setText(t("Проверено · нарушений нет"))
        # Кнопка появляется только по готовой проверке: на половине разбора
        # она чинила бы то, что через секунду окажется другим.
        fixer = getattr(self, "fixer", None)
        self.fixall.setVisible(not getattr(self, "busy", False)
                               and not self.rounds
                               and bool(self._fixable())
                               and not (fixer and fixer.isRunning()))

    # ── замена

    def _fixable(self):
        """Находки, для которых есть что поставить вместо них.

        Спорные места без статьи пропускаем: там нечего исправлять — это
        предупреждение, а не нарушение.
        """
        doc = self.editor.document()
        out = []
        for number, items in self._marks().items():
            block = doc.findBlockByNumber(number)
            if not block.isValid():
                continue
            for f in items:
                if f["law"] == "topic":
                    continue
                out.append(dict(f, start=block.position() + f["start"],
                                end=block.position() + f["end"]))
        return sorted(out, key=lambda f: f["start"])

    ROUNDS = 3               # столько раз текст правится и проверяется заново
    LONG = 200               # длиннее — абзац, короче — одиночное сообщение

    def _keep_fixing(self):
        """Замена меняет абзац, и проверка находит в нём новое — правим снова.

        Не бесконечно: если после трёх заходов текст всё ещё не чист, дальше
        человек разбирается сам.
        """
        fixer = getattr(self, "fixer", None)
        if self.rounds <= 0 or self.busy or (fixer and fixer.isRunning()):
            return
        left = self._fixable()
        # Пометки (плашка иноагента, оговорка о запрете) ставятся без модели и
        # всегда получаются — ради них заход делаем даже когда счёт не упал.
        marks = any(f.get("where") for f in left)
        # Заход не помог — дальше он не поможет тем более, а текст от каждой
        # новой правки только портится.
        if not left or (len(left) >= self.was and not marks):
            self.rounds = 0
            return
        self.rounds -= 1
        self._fix_all(again=True)

    def _fix_all(self, again=False):
        """Заменить все найденные места разом."""
        if self.checker is None:
            return
        if not again:
            self.rounds = self.ROUNDS
        found = self._fixable()
        if not found:
            self.rounds = 0
            return
        text = self.editor.toPlainText()
        doc = self.editor.document()
        по_абзацам = {}
        for f in found:
            по_абзацам.setdefault(doc.findBlock(f["start"]).blockNumber(),
                                  []).append(f)
        jobs = []
        for number, items in по_абзацам.items():
            block = doc.findBlockByNumber(number)
            # Несколько мест в одном абзаце правим одной переписью: по
            # отдельности каждая замена складна сама по себе, а вместе абзац
            # перестаёт сходиться — «горжусь перечнями… попадают под
            # подозрение».
            own = [f for f in items if not f["safe"] and not f.get("where")]
            # Длинный абзац правится целиком даже из-за одного места: доброе
            # утверждение посреди рассуждения читается вставкой, и текст
            # разваливается на «половину лозунгов и половину как было».
            if len(own) > 1 or (own and len(block.text()) > self.LONG):
                spots = [(text[f["start"]:f["end"]],
                          law.BY_ID.get(f["law"], {}).get("fix", {})
                          .get(i18n.current(), "убрать опасное место"),
                          f["law"])
                         for f in own]
                # Имена иностранных агентов перепись обязана сохранить:
                # без них плашку, которой требует закон, будет некуда ставить.
                # Названия запрещённых объединений сюда не идут — они под
                # запретом наравне с бранью.
                keep = [text[f["start"]:f["end"]] for f in items
                        if f.get("where") == "top"]
                jobs.append({"para": block.text(), "spots": spots, "keep": keep,
                             "each": own, "context": block.text(),
                             "found": dict(own[0], where="", safe="",
                                           start=block.position(),
                                           end=block.position()
                                           + len(block.text()))})
                items = [f for f in items if f not in own]
            for f in items:
                jobs.append({"found": f, "quote": text[f["start"]:f["end"]],
                             "context": self._around(f["start"])})
        self.before = text           # правим ровно тот текст, что проверяли
        self.was = len(found)        # с чем зашли: заход обязан сокращать счёт
        self.fixall.hide()
        self._drop_pop()
        self.fixer = self._keep(FixAll(self.checker, jobs))
        self.fixer.step.connect(
            lambda n, all=len(jobs): self.status.setText(
                tf("Исправление… {n} из {all}", n=n, all=all)))
        self.fixer.ready.connect(self._apply_all)
        self.fixer.finished.connect(self._count)
        self.fixer.start()

    def _apply_all(self, pairs):
        """Поставить все замены разом, снизу вверх.

        Снизу вверх — чтобы места выше не съезжали, пока правится то, что
        ниже. Плашка идёт последней: она вставляется в самое начало и двигает
        весь текст.
        """
        if self.editor.toPlainText() != getattr(self, "before", None):
            self.rounds = 0
            self.status.setText(t("Текст изменился — исправление отменено"))
            return
        # На одном месте бывает несколько статей. Правим один раз и по самому
        # широкому месту: узкое внутри широкого оставляло от предложения
        # огрызок — «…значимости для страны., Кавказа или Кубани давно
        # существуют». Плашки и оговорки в споре не участвуют: они не
        # заменяют текст, а добавляются к нему.
        wide, taken = [], []
        for found, safe in sorted(pairs, key=lambda x: x[0]["start"] - x[0]["end"]):
            if found.get("where") in ("top", "after"):
                continue
            if any(a < found["end"] and found["start"] < b for a, b in taken):
                continue
            taken.append((found["start"], found["end"]))
            wide.append((found, safe))
        for found, safe in pairs:
            # Плашка и оговорка добавляются к тексту, а не заменяют его. Но
            # упоминание внутри переписанного места исчезнет вместе с ним, и
            # вставка туда разрезала бы и замену, и саму оговорку.
            if found.get("where") not in ("top", "after"):
                continue
            if any(a < found["end"] and found["start"] < b for a, b in taken):
                continue
            wide.append((found, safe))

        cur = self.editor.textCursor()
        cur.beginEditBlock()
        names = []
        for found, safe in sorted(wide, key=lambda x: -x[0]["start"]):
            start, end = found["start"], found["end"]
            if found.get("where") == "top":
                # Плашка одна на весь материал, и в ней перечисляются все:
                # ставим её в конце, когда известны все имена.
                if found.get("name"):
                    names.insert(0, found["name"])
                continue
            cur.setPosition(start)
            if found.get("where") == "after":
                cur.setPosition(end)
                cur.insertText(f" ({safe})")
            else:
                cur.setPosition(end, QTextCursor.KeepAnchor)
                cur.insertText(safe)
        if names:
            # Имя, которое в плашке уже стоит, второй раз не дописываем.
            doc = self.editor.toPlainText()
            # dict.fromkeys — одно имя один раз: одного агента находят и в
            # первом абзаце, и в третьем.
            fresh = ", ".join(dict.fromkeys(x for x in names if x not in doc))
            if fresh:
                mark = registry.BY_KEY["foreign"]["mark"][i18n.current()]
                self._add_top("" if self._plaque() is not None
                              else mark.format(name=fresh), fresh)
        cur.endEditBlock()
        self.found.clear()
        self._instant()
        # Между заходами ждать нечего: человек нажал кнопку и ждёт итога.
        self._recheck() if self.rounds else self.wait.start()

    def _at(self, position):
        """Все находки под курсором: одна фраза нарушает по нескольку статей."""
        doc = self.editor.document()
        out = []
        for number, items in self._marks().items():
            block = doc.findBlockByNumber(number)
            if not block.isValid():
                continue
            for f in items:
                a, b = block.position() + f["start"], block.position() + f["end"]
                if a <= position <= b:
                    out.append((dict(f, start=a, end=b), a, b))
        return out

    def _around(self, at):
        """Абзац с местом и соседние с ним.

        Одного абзаца мало: в переписке и в списке коротких строк замена
        выходит складной сама по себе и спорит с тем, что стоит рядом.
        """
        block = self.editor.document().findBlock(at)
        rows = [block.previous().text()[-400:], block.text(),
                block.next().text()[:400]]
        return "\n".join(x for x in rows if x.strip())

    def _keep(self, job):
        """Ссылка на поток живёт до конца работы: без неё Qt роняет процесс."""
        self._alive.append(job)
        job.finished.connect(lambda: self._alive.remove(job)
                             if job in self._alive else None)
        return job

    def _on_pop(self):
        """Курсор стоит на самой карточке.

        Меряем по месту курсора, а не `underMouse`: карточка — отдельное окно
        и появляется прямо под указателем, а уход с неё Qt иногда не замечает.
        Тогда карточка считала, что человек на ней, и переставала слушать
        текст — до следующей другой она так и висела.
        """
        pop = getattr(self, "pop", None)
        return bool(pop and pop.isVisible()
                    and pop.frameGeometry().contains(QCursor.pos()))

    def _hide_pop(self):
        """Уходим с текста — карточку убираем, но не тогда, когда курсор
        переехал на неё саму: иначе до кнопки не добраться."""
        if not self._on_pop():
            self._drop_pop()

    def _drop_pop(self):
        """Убрать карточку сразу. Она отдельное окно, поэтому при прокрутке,
        переносе окна и уходе в фон обязана исчезать — иначе висит поверх
        чужих окон и указывает на строку, которой там уже нет."""
        if getattr(self, "pop", None) is None:
            return                       # окно ещё собирается
        self.fade.stop()
        self.pop.hide()
        self.pop.anchor = None

    def moveEvent(self, e):
        super().moveEvent(e)
        self._drop_pop()

    def _relayout(self):
        """Поля текста — обычные, как в любом текстовом редакторе."""
        ed = self.editor
        if ed is None:
            return
        ed.document().setDocumentMargin(0)
        ed.setViewportMargins(22, 18, 22, 18)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()
        self._drop_pop()
        if getattr(self, "zoomer", None):
            self.zoomer.hide()           # угол уехал, плашке там не место

    def changeEvent(self, e):
        # Щелчок по карточке — это тоже уход окна в фон: карточка своё окно и
        # при нажатии забирает себе активность. Если гасить её здесь без
        # разбора, кнопка «Изменить» не срабатывает никогда.
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() \
                and not self._pop_busy():
            self._drop_pop()
        super().changeEvent(e)

    def _pop_busy(self):
        """Карточка сейчас в руках у человека — трогать её нельзя."""
        pop = getattr(self, "pop", None)
        return bool(pop and pop.isVisible()
                    and (pop.isActiveWindow() or self._on_pop()))

    def _maybe_hide(self):
        self.fade.start()

    def _far(self):
        """Курсор ушёл далеко от карточки.

        Рядом с ней задержка нужна: человек ведёт мышь к кнопке «Изменить» и
        по дороге выходит за подсветку. Далеко от неё ждать нечего.
        """
        pop = getattr(self, "pop", None)
        if pop is None or not pop.isVisible():
            return False
        return not pop.frameGeometry().adjusted(-40, -30, 40, 30) \
            .contains(QCursor.pos())

    def _hovered(self, position):
        if self._on_pop():
            return
        hit = self._at(position)
        if not hit:
            self._drop_pop() if self._far() else self._maybe_hide()
            return
        items = [f for f, _a, _b in hit]
        a = min(b for _f, b, _e in hit)
        b = max(e for _f, _a, e in hit)
        self.fade.stop()
        if self.pop.isVisible() and self.pop.anchor == (a, b):
            return
        # Карточка встаёт под всей подсветкой, а не под её началом: длинная
        # фраза переносится на несколько строк, и карточка от первой из них
        # ложилась прямо на остальные.
        cur = self.editor.textCursor()
        cur.setPosition(a)
        left = self.editor.cursorRect(cur).left()
        bottom = max(self._line_bottom(a), self._line_bottom(b))
        # Считать от viewport, а не от самого поля: у поля свои поля в
        # оформлении, и карточка оказывалась на два десятка точек выше — как
        # раз на последней строке абзаца.
        line = self.editor.viewport().mapToGlobal(QPoint(left, bottom))
        try:
            self.pop.apply.clicked.disconnect()
        except RuntimeError:
            pass
        self.pop.apply.clicked.connect(
            lambda: self._fix(self.pop.action,
                              self.pop.action["start"], self.pop.action["end"]))
        self.pop.show_for(items, (a, b))
        self._want_fix(self.pop.action)
        # Показать до того, как ставить: пока окна нет, macOS считает размер
        # его рамки по-своему и при появлении сдвигает карточку вверх — прямо
        # на подсвеченную строку.
        self.pop.show()
        self.pop.place(line, 0)
        self.pop.raise_()

    def _line_bottom(self, position):
        """Низ строки, в которой стоит это место, в точках области текста.

        Не по каретке: она ровно по высоте букв, а строка выше и ниже шире её
        на междустрочие — карточка садилась на хвосты. И не по всему абзацу:
        под длинным абзацем она уезжала слишком далеко от самой подсветки.
        """
        cur = self.editor.textCursor()
        cur.setPosition(position)
        block = cur.block()
        box = self.editor.document().documentLayout().blockBoundingRect(block)
        row = block.layout().lineForTextPosition(position - block.position())
        top = box.top() - self.editor.verticalScrollBar().value()
        if not row.isValid():
            return int(box.bottom() - self.editor.verticalScrollBar().value())
        return int(top + row.y() + row.height())

    def _clicked(self, position):
        self._hovered(position)

    def _want_fix(self, found):
        """Просим у модели замену, если готовой нет."""
        if found["safe"] or not self.checker:
            return
        text = self.editor.toPlainText()
        quote = text[found["start"]:found["end"]]
        # Абзац вокруг места: без него модель придумывает замену с нуля и
        # получается складно, но не о том, о чём написано. Абзац — это строка
        # документа, тот же кусок, которым текст и проверяется: по пустым
        # строкам выходил весь текст целиком, и замена переписывала его начало.
        job = Rewrite(self.checker, quote, found["law"],
                      self._around(found["start"]))
        job.done.connect(lambda text, f=found: self._got_fix(f, text))
        self._keep(job)
        job.start()

    def _got_fix(self, found, text):
        found["safe"] = text
        if not self.pop.isVisible() or self.pop.action is not found:
            return
        self.pop.safe.setText("→ " + (text or t("замену подобрать не удалось")))
        self.pop.apply.setEnabled(bool(text))
        self.pop.place()

    def _fix(self, found, start, end):
        where = found.get("where")
        if where == "top":
            self._add_top(found["safe"], found.get("name", ""))
        elif where == "after":
            self._add_after(end, found["safe"])
        else:
            self._replace(start, end, found["safe"])

    def _add_top(self, note, name=""):
        """Указание об иноагенте ставится перед текстом материала.

        Если плашка уже есть, вторую не заводим: закон разрешает перечислить
        всех через запятую, и человеку не нужна стопка одинаковых строк.
        """
        doc = self.editor.toPlainText()
        if name and name in doc:
            self._hide_pop()
            return
        block = self._plaque()
        if block is not None and name:
            line = block.text()
            cur = QTextCursor(block)
            cur.setPosition(block.position() + len(line.rstrip()))
            cur.insertText((", " if not line.rstrip().endswith((".", "!", "?"))
                            else " ") + name)
            self._hide_pop()
            self.wait.start()
            return
        if note.split(",")[0][:40] in doc:
            self._hide_pop()
            return
        cur = self.editor.textCursor()
        cur.setPosition(0)
        cur.insertText(note + "\n\n")
        self._hide_pop()
        self.wait.start()

    def _plaque(self):
        """Строка с плашкой, если она в документе есть.

        Именно строка-плашка, а не любое место со словами «иностранный агент»:
        по ним за плашку сходило обычное предложение «оба официально
        иностранные агенты», и имена дописывались в середину текста.
        """
        block = self.editor.document().firstBlock()
        while block.isValid():
            if registry.is_plaque(block.text()):
                return block
            block = block.next()
        return None

    def _add_after(self, end, note):
        """Оговорка про организацию ставится рядом с упоминанием."""
        cur = self.editor.textCursor()
        cur.setPosition(end)
        cur.insertText(f" ({note})")
        self._hide_pop()
        self.wait.start()

    def _replace(self, start, end, safe):
        cur = self.editor.textCursor()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.KeepAnchor)
        cur.insertText(safe)
        self._hide_pop()
        self.wait.start()

    # ── файлы

    def _retitle(self, ed=None):
        ed = ed or self.editor
        if ed is None:
            return
        doc = self.docs.get(ed, {})
        path = doc.get("path")
        name = path.name if path else t("Без названия")
        at = self.tabs.indexOf(ed)
        if at >= 0:
            self.tabs.setTabText(at, name)
            self.tabs.setTabToolTip(at, str(path) if path else "")
            shut = self.tabs.tabBar().tabButton(at, QTabBar.ButtonPosition.RightSide)
            if isinstance(shut, TabShut):
                shut.show_dirty(self.dirty(ed))
        if ed is self.editor:
            self.setWindowTitle(f'{t("Порядочный блокнот")} — {name}')

    def new_file(self):
        self.add_tab()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("Открыть текст"), str(Path.home()), t(FILTER))
        if path:
            self.load(Path(path))

    def load(self, path):
        """Открыть документ любого известного вида."""
        import papers
        try:
            body = papers.read(path)
        except Exception as e:
            self._warn(str(e)[:300])
            return
        empty = (self.editor is not None and self.path is None
                 and not self.editor.toPlainText().strip())
        if empty:
            self.path = path
            self.editor.setPlainText(body)
            self.found.clear()
            self.doc["clean"] = body
        else:
            self.add_tab(body, path)
        self._retitle()
        self._recheck()

    def save_file(self):
        import papers
        if self.path is None or self.path.suffix.lower() in papers.READ_ONLY:
            start = self.path.with_suffix(".md") if self.path \
                else Path.home() / "text.md"
            path, _ = QFileDialog.getSaveFileName(
                self, t("Сохранить текст"), str(start), t(FILTER_SAVE))
            if not path:
                return
            self.path = Path(path)
        try:
            papers.write(self.path, self.editor.toPlainText())
        except Exception as e:
            self._warn(str(e)[:300])
            return
        self.doc["clean"] = self.editor.toPlainText()
        self._retitle()

    # ── картинки

    PICTURES = (".png", ".jpg", ".jpeg", ".heic", ".tiff", ".tif", ".gif",
                ".bmp", ".webp")

    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("Выбрать картинку"), str(Path.home()),
            t("Картинки (*.png *.jpg *.jpeg *.heic *.tiff *.gif *.bmp *.webp)"))
        if path:
            self.insert_image(path)

    def _dropped(self, paths):
        """Файл бросили в окно: картинку вставляем, документ открываем."""
        for path in paths:
            if Path(path).suffix.lower() in self.PICTURES:
                self.insert_image(path)
            else:
                self.load(Path(path))
                return

    def insert_image(self, path):
        """Картинка встаёт отдельным абзацем, под ней — распознанный текст."""
        image = QImage(path)
        if image.isNull():
            self._warn(t("Не удалось открыть картинку"))
            return
        wide = max(200, self.editor.viewport().width() - 60)
        if image.width() > wide:
            image = image.scaledToWidth(wide, Qt.SmoothTransformation)
        name = f"picture-{len(self.pictures)}"
        self.pictures[name] = Path(path)
        self.editor.document().addResource(QTextDocument.ImageResource, name, image)

        cur = self.editor.textCursor()
        if not cur.atBlockStart():
            cur.insertBlock()
        cur.insertImage(name)
        cur.insertBlock()
        spot = cur.blockNumber()
        cur.insertText(t("распознаю текст…"))
        self.editor.setTextCursor(cur)

        job = Reading(path)
        job.done.connect(lambda text, err, n=spot: self._read_image(n, text, err))
        self._keep(job)
        job.start()

    def _read_image(self, number, text, error):
        """Заменить строку ожидания распознанным текстом."""
        block = self.editor.document().findBlockByNumber(number)
        if not block.isValid():
            return
        cur = QTextCursor(block)
        cur.select(QTextCursor.BlockUnderCursor)
        body = text.strip() or (t("на картинке текста нет") if not error
                                else tf("распознать не вышло: {why}", why=error[:80]))
        # Блок выделяется вместе с переводом строки перед ним — вернём его.
        cur.insertText(("\n" if block.blockNumber() else "") + body)
        self._recheck()

    # ── настройки

    def _card(self, box, name, note):
        """Карточка настроек: название, пояснение, состояние справа."""
        card = QFrame(); card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(3)
        top = QHBoxLayout(); top.setSpacing(8)
        title = QLabel(name); title.setObjectName("cardName")
        state = QLabel(); state.setObjectName("dim")
        state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(title); top.addStretch(); top.addWidget(state)
        inner.addLayout(top)
        sub = QLabel(note); sub.setObjectName("dim"); sub.setWordWrap(True)
        inner.addWidget(sub)
        box.addWidget(card)
        return inner, state, sub

    def _card_button(self, inner, text, accent=False):
        row = QHBoxLayout(); row.setSpacing(8); row.addStretch()
        b = QPushButton(text)
        b.setObjectName("cardbtnAccent" if accent else "cardbtn")
        b.setCursor(Qt.PointingHandCursor)
        row.addWidget(b)
        inner.addSpacing(6)
        inner.addLayout(row)
        return b

    def open_settings(self):
        import models_store, registry
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Настройки"))
        dlg.setStyleSheet(_style.sheet(skin()))
        dlg.setMinimumWidth(520)
        box = QVBoxLayout(dlg)
        box.setContentsMargins(16, 16, 16, 16)
        box.setSpacing(10)

        for meta in models_store.CATALOG:
            self._model_card(box, dlg, meta)

        inner, state, sub = self._card(
            box, t("Реестры"),
            t("Иноагенты, нежелательные, запрещённые и террористические организации"))
        refresh = self._card_button(inner, t("Обновить"))

        def show_registry():
            when = registry.updated()
            total = sum(registry.counts().values())
            state.setText(time.strftime("%d.%m.%Y", time.localtime(when)) if when
                          else t("не загружены"))
            if total:
                sub.setText(tf("Записей: {n}", n=f"{total:,}".replace(",", " ")))

        show_registry()

        def update_registry():
            refresh.setEnabled(False)
            refresh.setText(t("Обновление…"))
            job = Registries()
            job.line.connect(state.setText)
            job.done.connect(lambda _n: (show_registry(), refresh.setEnabled(True),
                                         refresh.setText(t("Обновить")),
                                         self.checker and self.checker.cache.clear(),
                                         self._recheck()))
            job.failed.connect(lambda e: (state.setText(t("не получилось")),
                                          refresh.setEnabled(True),
                                          refresh.setText(t("Обновить")),
                                          self._warn(e)))
            self._keep(job); job.start()

        refresh.clicked.connect(update_registry)

        # Выражения: чего не хватает, человек дописывает себе сам — файлом,
        # который лежит рядом с перечнями.
        import phrases
        inner, свои_state, свои_sub = self._card(
            box, t("Выражения"), t("Опасные слова и обороты"))
        row = QHBoxLayout(); row.setSpacing(8); row.addStretch()
        открыть = QPushButton(t("Открыть список")); открыть.setObjectName("cardbtn")
        перечитать = QPushButton(t("Перечитать")); перечитать.setObjectName("cardbtn")
        for b in (открыть, перечитать):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        inner.addSpacing(6); inner.addLayout(row)

        def show_own():
            сколько = sum(len(v) for v in phrases.свои(law.НОМЕРА).values())
            свои_state.setText(tf("Выражений: {n}", n=сколько) if сколько
                               else t("пока пусто"))

        def open_own():
            if not phrases.СВОИ.exists():
                phrases.СВОИ.parent.mkdir(parents=True, exist_ok=True)
                phrases.СВОИ.write_text(phrases.ШАПКА, encoding="utf-8")
            subprocess.run(["open", "-t", str(phrases.СВОИ)], check=False)

        def reread_own():
            law.reload()
            if self.checker:
                self.checker.cache.clear()
                self.checker.ready.clear()
            show_own()
            self._recheck()

        show_own()
        открыть.clicked.connect(open_own)
        перечитать.clicked.connect(reread_own)

        inner, _state, _sub = self._card(box, t("Язык"), t("Язык интерфейса"))
        row = QHBoxLayout(); row.setSpacing(8); row.addStretch()
        for code, label in (("ru", "Русский"), ("en", "English")):
            b = QPushButton(label)
            b.setObjectName("cardbtnAccent" if code == i18n.current() else "cardbtn")
            b.setEnabled(code != i18n.current())
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: (i18n.set_current(c),
                                                       dlg.accept(), self.retranslate()))
            row.addWidget(b)
        inner.addSpacing(6); inner.addLayout(row)

        self._theme_card(box, dlg)

        box.addStretch()
        подпись = QLabel(f'{t("Порядочный блокнот")} · {AUTHOR} · '
                         f'<a href="{SITE_URL}">{SITE}</a>')
        подпись.setObjectName("dim")
        подпись.setAlignment(Qt.AlignCenter)
        подпись.setOpenExternalLinks(True)
        box.addWidget(подпись)
        dlg.exec()

    def _theme_card(self, box, dlg):
        """Светлая, тёмная или как в системе."""
        inner, _state, _sub = self._card(box, t("Оформление"),
                                         t("Цвета окна и текста"))
        row = QHBoxLayout(); row.setSpacing(8); row.addStretch()
        buttons = {}

        def pick(name):
            self.settings.setValue("theme", name)
            for code, b in buttons.items():
                b.setObjectName("cardbtnAccent" if code == name else "cardbtn")
                b.setStyleSheet("")          # чтобы Qt перечитал правило
                b.setEnabled(code != name)
            dlg.setStyleSheet(_style.sheet(skin()))
            self.apply_theme()

        for code, label in (("system", t("Как в системе")),
                            ("light", t("Светлое")), ("dark", t("Тёмное"))):
            b = QPushButton(label)
            b.setObjectName("cardbtnAccent" if code == theme() else "cardbtn")
            b.setEnabled(code != theme())
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: pick(c))
            buttons[code] = b
            row.addWidget(b)
        inner.addSpacing(6); inner.addLayout(row)

    def _model_card(self, box, dlg, meta):
        """Одна модель: сколько занимает, кнопка скачать или удалить."""
        import models_store
        repo = meta["repo"]
        inner, state, _sub = self._card(box, models_store.short_name(repo),
                                        t(meta["role"]))
        bar = QProgressBar(); bar.setRange(0, 100); bar.setVisible(False)
        bar.setTextVisible(False)
        inner.addWidget(bar)
        button = self._card_button(inner, "")

        def show():
            ready = models_store.is_ready(repo, meta["gb"])
            state.setText(models_store.human(models_store.size_ready(repo)) if ready
                          else tf("нет, скачать {gb} ГБ", gb=meta["gb"]))
            button.setText(t("Удалить") if ready else t("Скачать"))
            button.setObjectName("cardbtn" if ready else "cardbtnAccent")
            button.setStyleSheet("")
            button.setEnabled(True)

        def act():
            if repo in self._downloading:
                self._downloading[repo].stop()
                return
            if models_store.is_ready(repo, meta["gb"]):
                if not self._confirm(dlg, t("Удалить модель"),
                                     tf("Удалить {name}?",
                                        name=models_store.short_name(repo))):
                    return
                models_store.delete(repo)
                show()
                return
            bar.setVisible(True); bar.setValue(0)
            button.setText(t("Отмена"))
            job = Download(repo)
            self._downloading[repo] = job
            job.step.connect(lambda done, total: bar.setValue(
                int(done * 100 / total) if total else 0))
            job.done.connect(lambda ok, err: (self._downloading.pop(repo, None),
                                              bar.setVisible(False), show(),
                                              self._start_checker() if ok else None,
                                              None if ok or not err
                                              else self._warn(err[:300])))
            self._keep(job); job.start()

        button.clicked.connect(act)
        show()

    @staticmethod
    def _confirm(parent, title, text):
        box = QMessageBox(parent)
        box.setStyleSheet(_style.sheet(skin()))
        box.setIcon(QMessageBox.NoIcon)
        box.setWindowTitle(title)
        box.setText(text)
        yes = box.addButton(t("Удалить"), QMessageBox.YesRole)
        box.setDefaultButton(box.addButton(t("Отмена"), QMessageBox.NoRole))
        box.exec()
        return box.clickedButton() is yes

    def retranslate(self):
        """Перевод собранного окна: ключ ищется по видимой надписи."""
        for w in self.findChildren(QWidget):
            for get, put in ((getattr(w, "text", None), getattr(w, "setText", None)),):
                if not (get and put):
                    continue
                try:
                    cur = get()
                except TypeError:
                    continue
                key = i18n.key_of(cur) if cur else None
                if key:
                    put(t(key))
        for code, name in (("fast", "Быстро"), ("good", "Точно"),
                           ("max", "Максимум")):
            self.modes[code].setText(t(name))
        self._retitle()
        self._count()

    def closeEvent(self, e):
        """Выход: сначала про несохранённое, потом про потоки."""
        for at in range(self.tabs.count()):
            ed = self.tabs.widget(at)
            if self.dirty(ed) and not self._offer_save(ed):
                e.ignore()
                return
        for job in list(self._alive):
            if hasattr(job, "stop"):
                job.stop()   # потоки прерываем только когда уходим наверняка
        until = time.time() + 3
        for job in list(self._alive):
            job.wait(max(0, int((until - time.time()) * 1000)))
        super().closeEvent(e)
        if any(job.isRunning() for job in self._alive):
            # Поток с ответом модели прервать нечем: mlx считает внутри C++ и
            # о просьбе выйти не знает. Живой QThread при разрушении вызывает
            # abort, и вместо закрытия человек видит отчёт о падении Python.
            QApplication.processEvents()
            os._exit(0)


def _name_in_menu(name):
    """Имя программы в строке меню и в Dock.

    Полоса меню берёт название из бандла того, кто её нарисовал, а рисует её
    питон — и в меню стоит «Python». Подменяем название в описании бандла
    до создания QApplication: позже оно уже прочитано.
    """
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
            if info is not None:
                info["CFBundleName"] = name
                info["CFBundleDisplayName"] = name
    except Exception:
        pass                      # не macOS или нет pyobjc — переживём


def main():
    _name_in_menu("Порядочный блокнот")
    app = QApplication(sys.argv)
    app.setApplicationName("Порядочный блокнот")
    app.setApplicationDisplayName("Порядочный блокнот")
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
