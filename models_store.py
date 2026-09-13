"""Каталог моделей: наличие, размер на диске, скачивание и удаление.

Веса лежат в общем кэше Hugging Face, а не в бандле: они большие и переживают
обновление приложения.
"""
import os
import shutil
from pathlib import Path
from i18n import t

CACHE = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"

# role — ключ перевода, а не готовый текст: язык переключается на лету.
CATALOG = [
    {"kind": "llm", "repo": "mlx-community/Qwen3-8B-4bit",
     "role": "Проверка, режим «Быстро»", "gb": 4.3},
    {"kind": "llm", "repo": "mlx-community/Qwen3-30B-A3B-4bit",
     "role": "Проверка, режимы «Точно» и «Максимум»", "gb": 16.0},
]

def short_name(repo):
    return repo.split("/")[-1]


def _dir_for(repo):
    return CACHE / ("models--" + repo.replace("/", "--"))


def size_on_disk(repo):
    """Сколько уже лежит, вместе с недокачанным: по нему считается ход."""
    d = _dir_for(repo) / "blobs"
    if not d.exists():
        return 0
    total = 0
    for f in d.iterdir():
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def size_ready(repo):
    """Размер только целых файлов — по ссылкам в снимке.

    Считать по blobs нельзя: там лежат и обрывки прерванных закачек, и от
    них модель кажется скачанной, а при запуске обнаруживается, что файла
    нет.
    """
    snap = _dir_for(repo) / "snapshots"
    if not snap.exists():
        return 0
    total = 0
    for f in snap.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def is_ready(repo, gb):
    """Готова, когда целых файлов набралось почти на весь объём."""
    return size_ready(repo) >= gb * 1024 ** 3 * 0.95


def human(n):
    if n <= 0:
        return "—"
    for unit in (t("Б"), t("КБ"), t("МБ"), t("ГБ")):
        if n < 1024 or unit == t("ГБ"):
            return f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1024


def delete(repo):
    shutil.rmtree(_dir_for(repo), ignore_errors=True)


GRAB = ("import sys\n"
        "from huggingface_hub import snapshot_download\n"
        "snapshot_download(repo_id=sys.argv[1])\n")


def download(repo, on_progress=lambda done, total: None, should_stop=lambda: False):
    """Скачивание отдельным процессом; ход считается по размеру на диске.

    Процессом, а не потоком: остановку huggingface_hub не умеет, поток
    продолжал качать и после отмены. Процесс снимается целиком.
    """
    import subprocess, sys, tempfile

    # Xet качает быстрее, но пишет файл на диск целиком в самом конце: полоса
    # стоит на месте всю закачку, а на модели из одного файла — вообще всегда.
    # Обычная загрузка кладёт рядом .incomplete и растёт на глазах.
    env = {**os.environ, "HF_HUB_DISABLE_PROGRESS_BARS": "1",
           "HF_HUB_DISABLE_XET": "1"}
    log = tempfile.TemporaryFile()      # не канал: он забьётся и всё встанет
    proc = subprocess.Popen([sys.executable, "-c", GRAB, repo],
                            stdout=log, stderr=log, env=env)
    # Целое: сигнал о ходе объявлен целочисленным, и дробное значение роняло
    # каждый шаг — полоса стояла на нуле, хотя файлы качались.
    expected = int(next((m["gb"] for m in CATALOG if m["repo"] == repo), 1.0)
                   * 1024 ** 3)
    while proc.poll() is None:
        if should_stop():
            proc.terminate()
            return False        # недокачанное докачается при следующем запуске
        on_progress(int(size_on_disk(repo)), expected)
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
    if proc.returncode:
        log.seek(0)
        lines = [x.strip() for x in
                 log.read().decode("utf-8", "replace").splitlines() if x.strip()]
        # Последняя строка трассировки бывает подсказкой про пароль; берём саму ошибку.
        why = next((x for x in reversed(lines) if "Error" in x), lines[-1] if lines else "")
        raise RuntimeError(why[:300] or "скачивание не удалось")
    # Обрывки прошлых попыток больше не нужны и мешают считать размер.
    blobs = _dir_for(repo) / "blobs"
    if blobs.exists():
        for f in blobs.iterdir():
            if f.name.endswith(".incomplete"):
                f.unlink(missing_ok=True)
    on_progress(int(size_on_disk(repo)), expected)
    return True
