#!/bin/zsh
set -euo pipefail

# GUI 下常缺 PATH，这里手动补（含 Apple Silicon & Intel）
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# 解析启动器的绝对路径（含软链）
script_path="${0:A}"
repo_root="${script_path:h}"

# 从当前目录往上找到仓库根（带 scripts/start.sh）
current="$repo_root"
start_script=""
while [[ "$current" != "/" ]]; do
  if [[ -x "$current/scripts/start.sh" ]]; then
    start_script="$current/scripts/start.sh"
    repo_root="$current"
    break
  fi
  current="${current:h}"
done

if [[ -z "${start_script}" ]]; then
  /usr/bin/osascript -e 'display dialog "未找到 scripts/start.sh。请把启动器放在仓库根目录。" buttons {"好"} default button 1 with icon stop'
  exit 1
fi

cd "$repo_root"

# **关键**：若存在 .venv，强制让 start.sh 走 venv
if [[ -x ".venv/bin/python3" ]]; then
  export USE_VENV=1
fi

# 可选：加载 .env / .env.local（若你的 UI 高级设置依赖这些变量）
for envf in ".env.local" ".env"; do
  if [[ -f "$envf" ]]; then
    set -a
    source "$envf"
    set +a
  fi
done

# 日志可留存（需要的话取消注释）
# mkdir -p logs
# "$start_script" 2>&1 | tee -a "logs/start-$(date +%Y%m%d-%H%M%S).log"
# exit 0

# 直接执行（能在弹出的 Terminal 里看到输出）
exec "$start_script"
