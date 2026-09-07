#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv-ocr/bin/python ]; then
  echo '尚未安装运行环境，请按 README 的“本地启动”步骤安装 Python 依赖。'
  exit 1
fi
if [ ! -f app/config.ini ]; then
  echo '尚未创建配置，请先复制 app/config.sample.ini 为 app/config.ini。已有配置不要覆盖。'
  exit 1
fi
exec .venv-ocr/bin/python app/main.py
