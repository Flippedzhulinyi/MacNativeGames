#!/bin/bash
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/games/totk/scripts/offline_save_editor.py"
PY=""

for candidate in "${TOTK_SAVE_EDITOR_PYTHON:-}" \
    /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 \
    /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/bin/python3; do
    [ -n "$candidate" ] || continue
    if [ -x "$candidate" ] && "$candidate" -c \
        'import sys, tkinter; sys.exit(tuple(map(int, tkinter.Tcl().eval("info patchlevel").split(".")))[:2] < (8, 6))' \
        >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "没有找到带 Tk 8.6 或更新版本的 Python。旧版 Tk 可能无法正确绘制窗口。"
    echo "可运行：brew install python-tk@3.14"
    echo "然后设置 TOTK_SAVE_EDITOR_PYTHON=/opt/homebrew/bin/python3.14 再启动。"
    read -r -p "按 Return 关闭窗口。 " _ || true
    exit 1
fi

exec "$PY" "$SCRIPT"
