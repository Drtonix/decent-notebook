"""Раскладка установочного образа для dmgbuild.

Через Finder её задать нельзя: AppleScript требует доступа к автоматизации
и на чужой машине молча не срабатывает. dmgbuild пишет .DS_Store напрямую.
"""
import os

NAME = "Порядочный блокнот"
app = os.path.join(os.getcwd(), "build", NAME + ".app")

# Размер — с запасом от самого приложения: на автоматическом dmgbuild
# не хватало места, и большие файлы ложились в образ обрезанными.
_mb = sum(f.stat().st_size for f in __import__("pathlib").Path(app).rglob("*")
          if f.is_file() and not f.is_symlink()) / 2**20 if os.path.isdir(app) else 0
size = f"{int(_mb * 1.3) + 300}M"

files = [app]
symlinks = {"Applications": "/Applications"}
volume_name = NAME
format = "UDZO"
compression_level = 9

icon_size = 128
window_rect = ((260, 220), (560, 340))      # положение и размер окна
icon_locations = {
    NAME + ".app": (150, 150),
    "Applications": (410, 150),
}
background = "#1e1e20"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
default_view = "icon-view"
arrange_by = None
text_size = 13
label_pos = "bottom"
