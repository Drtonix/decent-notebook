#!/bin/zsh
# Ярлык для запуска из исходников: приложение с иконкой в доке, но питон берётся
# из .venv рядом. Самодостаточный бандл собирает build_app.sh — он будет позже.
set -e
cd "${0:A:h}"
APP="$PWD/build/Порядочный блокнот.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp icon/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
# Assets.car — тот же значок в светлом и тёмном варианте; icns остаётся
# запасным для старых систем, которые каталог не читают.
[ -f icon/Assets.car ] && cp icon/Assets.car "$APP/Contents/Resources/Assets.car"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Порядочный блокнот</string>
<key>CFBundleDisplayName</key><string>Порядочный блокнот</string>
<key>CFBundleIdentifier</key><string>space.bdub.sfwedit</string>
<key>CFBundleExecutable</key><string>launcher</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleIconName</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
# Приложение опознаётся по пути процесса: питон из .venv даёт в доке и в
# строке меню имя «Python». Кладём сам интерпретатор в MacOS, рядом pyvenv.cfg
# с путём к настоящей установке, а библиотеки добираем через PYTHONPATH.
# Берём именно бинарник из Python.app: тот, что в bin, — заглушка, которая
# перезапускает его сама, и процесс снова зовётся «Python».
REAL=$("$PWD/.venv/bin/python" - <<'FIND'
import os, sys
app = os.path.join(sys.base_prefix, "Resources", "Python.app",
                   "Contents", "MacOS", "Python")
print(app if os.path.exists(app) else os.path.realpath(sys._base_executable))
FIND
)
SITE=$("$PWD/.venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
# Имя процесса — это имя файла: так оно и попадает в строку меню и в Dock.
cp "$REAL" "$APP/Contents/MacOS/Порядочный блокнот"
cat > "$APP/Contents/MacOS/pyvenv.cfg" <<CFG
home = $(dirname "$REAL")
include-system-site-packages = true
version = $("$PWD/.venv/bin/python" -c 'import platform; print(platform.python_version())')
CFG
cat > "$APP/Contents/MacOS/launcher" <<LAUNCH
#!/bin/zsh
DIR="\${0:A:h}"
cd "$PWD"
export PYTHONPATH="$SITE"
exec "\$DIR/Порядочный блокнот" "$PWD/app.py"
LAUNCH
chmod +x "$APP/Contents/MacOS/launcher"
echo "готово: $APP"
