#!/bin/zsh
# Образ для установки: приложение и ярлык «Программы». После build_app.sh.
set -e
cd "${0:A:h}"
OUT="$PWD/build"
NAME="Порядочный блокнот"
DMG="$OUT/decent-notebook.dmg"

[ -d "$OUT/$NAME.app" ] || { echo "Сначала ./build_app.sh"; exit 1; }

say() { print -P "%F{green}==>%f $*"; }

say "сборка образа"
rm -f "$DMG"
PY=./.venv/bin/python
"$PY" -c "import dmgbuild" 2>/dev/null || PY=python3
"$PY" -m dmgbuild -s dmg_settings.py "$NAME" "$DMG"

say "готово: $(du -sh "$DMG" | cut -f1)  ->  $DMG"
