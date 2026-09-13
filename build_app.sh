#!/bin/zsh
# Самодостаточный «Порядочный блокнот.app»: свой Python и библиотеки.
# Веса модели качаются из настроек — иначе бандл на двадцать гигабайт.
set -e
setopt null_glob
cd "${0:A:h}"
SRC="$PWD"
OUT="$SRC/build"
NAME="Порядочный блокнот"
APP="$OUT/$NAME.app"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.12.14%2B20260901-aarch64-apple-darwin-install_only_stripped.tar.gz"

say() { print -P "%F{green}==>%f $*"; }

rm -rf "$APP"
mkdir -p "$OUT" "$APP/Contents/MacOS" "$APP/Contents/Resources"
RES="$APP/Contents/Resources"

say "переносимый Python"
[ -f "$OUT/python.tar.gz" ] || curl -fsSL "$PY_URL" -o "$OUT/python.tar.gz"
mkdir -p "$RES/python"
tar xzf "$OUT/python.tar.gz" -C "$RES/python" --strip-components=1
PY="$RES/python/bin/python3"

say "библиотеки"
"$PY" -m pip -q install --upgrade pip
# Те же версии, на которых проверен набор случаев.
"$PY" -m pip -q install PySide6==6.11.2 mlx==0.32.2 mlx-lm==0.31.3 transformers==5.17.0 \
    huggingface_hub==1.31.0 truststore==0.10.4 certifi \
    pyobjc-framework-Cocoa==12.2.2 pyobjc-framework-Quartz==12.2.2 pyobjc-framework-Vision==12.2.2
# torch и его свита блокноту не нужны, а весят гигабайт.
"$PY" -m pip -q uninstall -y torch sympy networkx 2>/dev/null || true

say "чистка лишнего"
SP="$RES/python/lib/python3.12/site-packages"
# Нужны только виджеты: ни веб-движка, ни звука, ни QML.
for m in Qt3D QtCharts QtDataVis QtDesigner QtQuick3D QtSensors QtSerial QtSql \
         QtTest QtBluetooth QtNfc QtRemoteObjects QtScxml QtSpatialAudio \
         QtStateMachine QtTextToSpeech QtHelp QtUiTools QtPdf QtMultimedia \
         QtWebEngine QtWebView QtWebChannel QtWebSockets QtPositioning \
         QtLocation QtQuick QtQml QtGraphs QtVirtualKeyboard QtHttpServer; do
    rm -rf "$SP/PySide6/Qt/lib/${m}"*.framework "$SP/PySide6/${m}"* 2>/dev/null || true
done
rm -rf "$SP/PySide6/Qt/translations" "$SP/PySide6/Qt/qml" \
       "$SP/PySide6/Designer.app" "$SP/PySide6/assistant.app" \
       "$SP/PySide6/linguist.app" "$SP/PySide6/examples" 2>/dev/null || true
find "$SP" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
# dist-info не трогаем: без них transformers падает на проверке версий.
find "$RES/python/lib" -name "test" -type d -prune -exec rm -rf {} + 2>/dev/null || true

say "исходники"
mkdir -p "$RES/app"
cp app.py check.py i18n.py law.py models_home.py models_store.py papers.py phrases.py \
   registry.py support.py vision.py _style.py "$RES/app/"
cp -R certs "$RES/app/"

say "лицензии"
LIC="$RES/Лицензии"
mkdir -p "$LIC"
# find, а не шаблон: zsh на пустом совпадении падает, а с set -e рвёт сборку.
find "$SP" -maxdepth 1 -type d -name "*.dist-info" | while read -r d; do
    pkg=$(basename "$d" .dist-info)
    find "$d" -maxdepth 2 \( -name "LICENSE*" -o -name "COPYING*" -o -name "NOTICE*" \) \
        -type f 2>/dev/null | while read -r f; do
        mkdir -p "$LIC/$pkg"
        cp "$f" "$LIC/$pkg/" 2>/dev/null || true
    done
done
cat > "$LIC/О лицензиях.txt" <<'LICNOTE'
Из чего собран Порядочный блокнот и на каких условиях.

Qt / PySide6 — LGPL 3.0
    Библиотеки Qt лежат в приложении отдельными файлами и не вкомпилированы
    в него, поэтому их можно заменить своими сборками. Исходники:
    https://download.qt.io/official_releases/qt/

Python — PSF License
mlx, mlx-lm — MIT
transformers, huggingface_hub, tokenizers, safetensors — Apache 2.0
pyobjc — MIT
truststore — MIT, certifi — MPL 2.0
numpy — BSD

Полные тексты — в папках рядом, по одной на пакет.

Модели нейросетей в приложение не входят и скачиваются отдельно:
Qwen 3.5 и Qwen 3.6 — Apache 2.0.
LICNOTE

say "интерпретатор в MacOS"
# macOS зовёт программу по имени файла процесса: питон из Resources даёт
# в доке ракету и имя «python3». Интерпретатор кладём в MacOS под именем
# приложения; он статический, свою установку находит по PYTHONHOME.
# Имя — в разложенной форме юникода: образ (HFS+) раскладывает «й» на «и» и
# кратку, и подпись, снятая с исходного имени, внутри образа не сходится.
BIN=$("$PY" -c 'import sys, unicodedata; print(unicodedata.normalize("NFD", sys.argv[1]))' "$NAME")
cp "$RES/python/bin/python3.12" "$APP/Contents/MacOS/$BIN"

say "оболочка"
cat > "$APP/Contents/MacOS/launcher" <<'LAUNCH'
#!/bin/zsh
LOG="$HOME/Library/Logs/Порядочный блокнот.log"
mkdir -p "$HOME/Library/Logs"
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 5000000 ]; then : > "$LOG"; fi
exec >> "$LOG" 2>&1
echo "=== запуск $(date) ==="
DIR="${0:A:h}"
RES="$DIR/../Resources"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONHOME="$RES/python"
# Бандл подписан и после установки не меняется: запись внутрь — и macOS
# при следующем запуске проверяет его заново. Байт-код собран заранее.
export PYTHONDONTWRITEBYTECODE=1
export TOKENIZERS_PARALLELISM=false
cd "$RES/app"
exec "$DIR/Порядочный блокнот" "$RES/app/app.py"
LAUNCH
chmod +x "$APP/Contents/MacOS/launcher"
# Assets.car — значок в светлом и тёмном варианте; icns — для старых систем.
cp icon/AppIcon.icns "$RES/AppIcon.icns"
cp icon/Assets.car "$RES/Assets.car"

mkdir -p "$RES/ru.lproj" "$RES/en.lproj"
printf '"CFBundleDisplayName" = "Порядочный блокнот";\n"CFBundleName" = "Порядочный блокнот";\n' \
    > "$RES/ru.lproj/InfoPlist.strings"
printf '"CFBundleDisplayName" = "Decent Notebook";\n"CFBundleName" = "Decent Notebook";\n' \
    > "$RES/en.lproj/InfoPlist.strings"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>ru</string>
<key>CFBundleLocalizations</key><array><string>ru</string><string>en</string></array>
<key>CFBundleDisplayName</key><string>Порядочный блокнот</string>
<key>CFBundleExecutable</key><string>launcher</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleIconName</key><string>AppIcon</string>
<key>CFBundleIdentifier</key><string>space.bdub.sfwedit</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>Порядочный блокнот</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSDocumentsFolderUsageDescription</key><string>Порядочный блокнот открывает и сохраняет тексты в папке «Документы».</string>
<key>NSDownloadsFolderUsageDescription</key><string>Порядочный блокнот открывает тексты из папки «Загрузки».</string>
<key>NSDesktopFolderUsageDescription</key><string>Порядочный блокнот открывает и сохраняет тексты на рабочем столе.</string>
<key>NSHumanReadableCopyright</key><string>DrTonix · bdub.space</string>
</dict></plist>
PLIST

say "байт-код"
"$PY" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$RES/python/lib/python3.12" >/dev/null 2>&1 || true
"$PY" -m compileall -q --invalidation-mode unchecked-hash "$RES/app" >/dev/null

say "подпись"
# Без подписи macOS считает скачанное приложение повреждённым, а первый запуск
# большого бандла после установки идёт около 29 с.
codesign --force --deep --sign - "$APP" 2>/dev/null
codesign --verify --deep --strict "$APP"

say "готово: $(du -sh "$APP" | cut -f1)  ->  $APP"

# Копия в build — не второе приложение в Launchpad и Spotlight: снимаем с учёта.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$APP" >/dev/null 2>&1 || true
