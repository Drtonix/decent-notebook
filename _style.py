"""Оформление. Две палитры, светлая и тёмная; какую взять — решает app.py."""

PALETTES = {
    "dark": {
        "bg": "#1e1e20", "panel": "#26262a", "paper": "#232327",
        "pop": "#34343b", "edge": "rgba(255,255,255,0.10)",
        "rim": "rgba(255,255,255,0.30)",
        "text": "#e9ebef", "bright": "#f4f5f7", "dim": "#8a8f98",
        "faint": "#6f747d", "note": "#b6bac1",
        "soft": "rgba(255,255,255,0.08)", "softer": "rgba(255,255,255,0.14)",
        "flat": "rgba(255,255,255,0.05)",
        "marks": "#4a4d55", "quote": "#9aa0a8", "code": "#8ad6a0",
        "pick": "rgba(91,124,250,0.35)", "on": "rgba(91,124,250,0.30)",
    },
    "light": {
        "bg": "#e8e9ec", "panel": "#ffffff", "paper": "#ffffff",
        "pop": "#ffffff", "edge": "rgba(0,0,0,0.10)",
        "rim": "rgba(0,0,0,0.28)",
        "text": "#1d1f24", "bright": "#111318", "dim": "#6a6f78",
        "faint": "#9aa0a8", "note": "#4a4f58",
        "soft": "rgba(0,0,0,0.06)", "softer": "rgba(0,0,0,0.11)",
        "flat": "rgba(0,0,0,0.04)",
        "marks": "#b6bac1", "quote": "#6a6f78", "code": "#1f7a45",
        "pick": "rgba(91,124,250,0.25)", "on": "rgba(91,124,250,0.18)",
    },
}

ACCENT, ACCENT_ON = "#5b7cfa", "#6d8bff"

SHEET = """
/* Пунктирная рамка фокуса читается как россыпь точек. */
* {{ outline: none; }}

QWidget {{ font-family: "Helvetica Neue", Arial, sans-serif; font-size: 13px; }}
QWidget#root, QDialog {{ background: {bg}; }}
/* Без своей подложки: внутри скруглённых блоков проступают прямоугольники. */
QLabel, QCheckBox {{ background: transparent; color: {text}; font-size: 13px; }}

/* Поле ввода — лист: поля по краям, тень не нужна, её даёт фон окна. */
QTextEdit#editor {{
    background: {paper}; border: none; border-radius: 12px;
    padding: 0; color: {text};
    font-family: "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: {size}px; line-height: 160%;
    selection-background-color: {pick};
}}


QFrame#bar {{ background: {panel}; border-radius: 12px; }}
QFrame#segment {{ background: {soft}; border-radius: 10px; }}
QPushButton#seg {{
    background: transparent; border: none; border-radius: 8px;
    padding: 5px 12px; color: {dim}; font-size: 13px;
}}
QPushButton#seg:hover {{ color: {text}; }}
QPushButton#seg:checked {{ background: {accent}; color: #ffffff; font-weight: 600; }}
QFrame#sep {{ background: {edge}; max-width: 1px; }}

QPushButton#tool {{
    background: transparent; border: none; border-radius: 8px;
    color: {text}; padding: 6px 10px; font-size: 13px;
}}
QPushButton#tool:hover   {{ background: {soft}; }}
QPushButton#tool:checked {{ background: {on}; color: {bright}; }}

QLabel#status, QLabel#count, QLabel#dim {{ color: {dim}; font-size: 12px; }}

/* Кнопка в строке состояния: одного роста с надписью рядом, иначе строка
   подпрыгивает, когда проверка закончилась. */
QPushButton#fixall {{
    background: transparent; border: none; border-radius: 6px;
    color: {text}; padding: 1px 8px; font-size: 12px;
}}
QPushButton#fixall:hover {{ background: {soft}; }}

QFrame#pop {{ background: {pop}; border: 1px solid {rim}; border-radius: 12px; }}
QFrame#zoom {{
    background: {pop}; border: 1px solid {edge}; border-radius: 10px;
}}
QLineEdit#zoomNow {{
    background: transparent; border: none; border-radius: 7px;
    color: {text}; padding: 3px 4px; font-size: 13px;
    selection-background-color: {pick};
}}
QLineEdit#zoomNow:hover, QLineEdit#zoomNow:focus {{ background: {soft}; }}
QPushButton#zoomStep {{
    background: transparent; border: none; border-radius: 7px;
    color: {text}; padding: 2px 9px; font-size: 15px;
}}
QPushButton#zoomStep:hover {{ background: {soft}; }}
QPushButton#zoomStep:disabled {{ color: {faint}; }}
/* Окна с вопросом macOS рисует сама, но наши цвета к ним всё же попадают —
   и кнопки становились серым по серому. Задаём их целиком. */
QMessageBox {{ background: {bg}; }}
QMessageBox QLabel {{ color: {text}; font-size: 13px; }}
QMessageBox QPushButton {{
    background: {soft}; border: none; border-radius: 8px;
    color: {text}; padding: 7px 18px; font-size: 13px; min-width: 84px;
}}
QMessageBox QPushButton:hover {{ background: {softer}; }}
QMessageBox QPushButton:default {{ background: {accent}; color: #ffffff; }}
QMessageBox QPushButton:default:hover {{ background: {accent_on}; }}

QTabWidget#tabs::pane {{
    border: none; background: transparent; top: -1px;
}}
/* Вкладки документов: плоские ярлычки над листом. */
QTabWidget#tabs > QTabBar {{ qproperty-drawBase: 0; }}
QTabWidget#tabs > QTabBar::tab {{
    background: {soft}; color: {dim}; border: none;
    padding: 0 8px 0 14px; margin: 0 2px 0 0;
    min-width: 120px; max-width: 230px; height: 30px;
    border-top-left-radius: 10px; border-top-right-radius: 10px;
    font-size: 13px;
}}
QTabWidget#tabs > QTabBar::tab:hover {{ color: {text}; }}
QTabWidget#tabs > QTabBar::tab:selected {{ background: {paper}; color: {bright}; }}
QPushButton#tabShut {{
    background: transparent; border: none; border-radius: 8px;
    color: {faint}; font-size: 10px; padding: 0; text-align: center;
}}
QPushButton#tabShut:hover {{ background: {softer}; color: {bright}; }}

QScrollArea#popScroll, QWidget#popInside {{ background: transparent; border: none; }}
QLabel#popLaw  {{ color: {bright}; font-size: 13px; font-weight: 600; }}
QLabel#popWhy  {{ color: {note}; font-size: 12px; }}
QLabel#popSafe {{ color: {text}; font-size: 13px; }}

QFrame#card {{ background: {panel}; border: 1px solid {edge}; border-radius: 12px; }}
QLabel#cardName {{ color: {bright}; font-size: 14px; font-weight: 600; }}

QPushButton#cardbtn {{
    background: {soft}; border: none; border-radius: 8px;
    color: {text}; padding: 7px 16px; font-size: 13px;
}}
QPushButton#cardbtn:hover    {{ background: {softer}; }}
QPushButton#cardbtn:disabled {{ color: {faint}; background: {flat}; }}
QPushButton#cardbtnAccent {{
    background: {accent}; border: none; border-radius: 8px;
    color: #ffffff; padding: 7px 16px; font-size: 13px;
}}
QPushButton#cardbtnAccent:hover    {{ background: {accent_on}; }}
QPushButton#cardbtnAccent:disabled {{ color: rgba(255,255,255,0.55); }}

QComboBox {{
    background: {soft}; border: none; border-radius: 9px;
    padding: 5px 10px; color: {text};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {pop}; color: {text}; border: 1px solid {edge};
    selection-background-color: {on};
}}

QProgressBar {{
    background: {soft}; border: none; border-radius: 3px;
    height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {softer}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def sheet(theme, size=15, cross="", cross_on=""):
    """size — размер текста в поле ввода, cross — файл с крестиком вкладки."""
    return SHEET.format(accent=ACCENT, accent_on=ACCENT_ON, size=size,
                        cross=cross, cross_on=cross_on, **PALETTES[theme])


def palette(theme):
    return PALETTES[theme]
