"""Иконка: блокнот с триколорным корешком.

Рисуем в край — macOS обрежет по своей маске, и собственные поля выглядели бы
вдавленными. Всё построено на одной сетке: радиусы, отступы и толщина линий
кратны 16, поэтому фигура читается и в 32 точки, и в 1024.
"""
import sys
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient)

S = 1024
U = 16                                   # шаг сетки

# Две темы: macOS сама подставит нужную. Фон нейтрально-чёрный, в тёмной теме
# чуть светлее — иначе иконка сливается с тёмным доком.
THEMES = {
    "light": {"top": "#141416", "low": "#08080a", "page": "#f2f4f8",
              "line": "#aab2c0", "edge": "#000000"},
    "dark":  {"top": "#26262b", "low": "#17171a", "page": "#e8ebf1",
              "line": "#9aa3b2", "edge": "#3a3a41"},
}
BLUE, RED, WHITE = QColor("#1e4fa3"), QColor("#d02b2b"), QColor("#ffffff")


def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw(path, theme="light", layer=False):
    """layer=True — только блокнот на прозрачном фоне: фон и тень в этом случае
    рисует сама macOS, по своим правилам для светлой и тёмной темы."""
    QGuiApplication.instance() or QGuiApplication([])
    skin = THEMES[theme]
    page, line = QColor(skin["page"]), QColor(skin["line"])
    img = QImage(S, S, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    if not layer:
        back = QLinearGradient(0, 0, 0, S)
        back.setColorAt(0.0, QColor(skin["top"]))
        back.setColorAt(1.0, QColor(skin["low"]))
        p.fillRect(QRectF(0, 0, S, S), QBrush(back))

    book = QRectF(9 * U, 7 * U, 46 * U, 50 * U)
    radius = 3 * U

    p.setPen(Qt.NoPen)
    for step in range(0 if layer else 1, 0 if layer else 7):
        p.setBrush(QColor(0, 0, 0, 16))
        p.drawPath(rounded(book.adjusted(-step * 2, step * 3, step * 2, step * 4),
                           radius + step * 2))

    p.setBrush(QBrush(page))
    p.drawPath(rounded(book, radius))

    # Корешок: три полосы флага, скруглённые по левому краю блокнота.
    spine = QRectF(book.left(), book.top(), 8 * U, book.height())
    p.setClipPath(rounded(book, radius))
    third = spine.height() / 3
    for n, colour in enumerate((WHITE, BLUE, RED)):
        p.setBrush(QBrush(colour))
        p.drawRect(QRectF(spine.left(), spine.top() + n * third, spine.width(), third + 1))
    # Граница корешка и страницы: без неё белая полоса флага сливается с листом.
    p.setPen(QPen(QColor(0, 0, 0, 40), 3))
    p.drawLine(QPointF(spine.right(), spine.top()),
               QPointF(spine.right(), spine.bottom()))
    p.setClipping(False)

    # Строки текста — три ровных штриха, последний короче.
    p.setPen(QPen(line, 2 * U, Qt.SolidLine, Qt.RoundCap))
    left = spine.right() + 5 * U
    for n, width in enumerate((22, 22, 13)):
        y = book.top() + 15 * U + n * 9 * U
        p.drawLine(QPointF(left, y), QPointF(left + width * U, y))

    p.setPen(QPen(QColor(skin["edge"]), 4))
    p.setBrush(Qt.NoBrush)
    p.drawPath(rounded(book, radius))

    p.end()
    img.save(path)


if __name__ == "__main__":
    draw(sys.argv[1] if len(sys.argv) > 1 else "icon/AppIcon-1024.png",
         sys.argv[2] if len(sys.argv) > 2 else "light",
         len(sys.argv) > 3 and sys.argv[3] == "layer")
