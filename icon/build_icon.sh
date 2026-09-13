#!/bin/zsh
# Иконка собирается из документа Icon Composer: один слой с блокнотом на
# прозрачном фоне, подложку и тень macOS рисует сама и по-своему для светлой и
# тёмной темы. Варианты лежат в Assets.car; .icns остаётся для старых систем.
set -e
cd "${0:A:h}/.."
PY=./.venv/bin/python
ACTOOL=/Applications/Xcode.app/Contents/Developer/usr/bin/actool
ICTOOL="/Applications/Xcode.app/Contents/Applications/Icon Composer.app/Contents/Executables/ictool"

"$PY" icon/drawicon.py icon/AppIcon.icon/Assets/notebook.png light layer
"$PY" icon/drawicon.py icon/AppIcon-1024.png light

if [ -x "$ACTOOL" ]; then
    OUT=$(mktemp -d)
    "$ACTOOL" icon/AppIcon.icon --compile "$OUT" --platform macosx \
        --minimum-deployment-target 26.0 --app-icon AppIcon \
        --output-partial-info-plist "$OUT/partial.plist" >/dev/null
    cp "$OUT/Assets.car" icon/Assets.car
    # .icns рисуем тем же движком, что и каталог, иначе запасной значок
    # отличается от того, что показывает док.
    rm -rf "$OUT/set.iconset" && mkdir -p "$OUT/set.iconset"
    for sz in 16 32 128 256 512; do
        "$ICTOOL" icon/AppIcon.icon --export-image --platform macOS --rendition Default \
            --output-file "$OUT/set.iconset/icon_${sz}x${sz}.png" --width $sz --height $sz --scale 1 >/dev/null
        "$ICTOOL" icon/AppIcon.icon --export-image --platform macOS --rendition Default \
            --output-file "$OUT/set.iconset/icon_${sz}x${sz}@2x.png" --width $sz --height $sz --scale 2 >/dev/null
    done
    iconutil -c icns "$OUT/set.iconset" -o icon/AppIcon.icns
    rm -rf "$OUT"
    echo "готово: Assets.car со всеми темами и запасной AppIcon.icns"
else
    rm -rf /tmp/iconset.iconset && mkdir -p /tmp/iconset.iconset
    for sz in 16 32 64 128 256 512; do
        sips -z $sz $sz icon/AppIcon-1024.png --out /tmp/iconset.iconset/icon_${sz}x${sz}.png >/dev/null
        sips -z $((sz*2)) $((sz*2)) icon/AppIcon-1024.png --out /tmp/iconset.iconset/icon_${sz}x${sz}@2x.png >/dev/null
    done
    iconutil -c icns /tmp/iconset.iconset -o icon/AppIcon.icns
    echo "готово: только AppIcon.icns — actool не найден"
fi
