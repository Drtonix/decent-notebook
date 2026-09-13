# Сторонние компоненты

Лицензия MIT в `LICENSE` распространяется только на код этого репозитория.
Программа работает вместе с компонентами ниже; они устанавливаются отдельно
и остаются под своими лицензиями.

| Компонент | Версия | Лицензия | Источник |
|---|---|---|---|
| Qt (через PySide6) | 6.11.2 | LGPL-3.0 | https://download.qt.io/official_releases/QtForPython/ |
| MLX, mlx-lm | 0.32.2 / 0.31.3 | MIT | https://github.com/ml-explore/mlx |
| huggingface-hub | 1.31.0 | Apache-2.0 | https://github.com/huggingface/huggingface_hub |
| pyobjc (Cocoa, Quartz, Vision) | 12.2.2 | MIT | https://github.com/ronaldoussoren/pyobjc |
| NumPy | 2.5.3 | BSD-3-Clause | https://numpy.org |

## Веса моделей

Скачиваются при первом запуске и в репозитории не лежат.

| Модель | Лицензия | Источник |
|---|---|---|
| Qwen3-8B, 4 бита | Apache-2.0 | https://huggingface.co/mlx-community/Qwen3-8B-4bit |
| Qwen3-30B-A3B, 4 бита | Apache-2.0 | https://huggingface.co/mlx-community/Qwen3-30B-A3B-4bit |

## Данные

Перечни скачиваются с сайтов Минюста и Росфинмониторинга при обновлении и
хранятся в `~/Library/Application Support/decent-notepad`. В репозитории их нет.

`certs/russian-trusted-ca.pem` — открытый корневой сертификат Минцифры: без
него не открывается `fedsfm.ru`.
