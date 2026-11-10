#!/usr/bin/env bash
# GFIC 恢复：从备份包恢复业务数据与配置
# 用法：sudo bash scripts/restore.sh gfic-20261110-213000.tgz
# 注意：恢复会覆盖 data/ 与配置，请先确认；脚本会先把当前状态另存为 pre-restore 备份。
set -euo pipefail
APP_DIR="${GFIC_DIR:-/vol1/1000/docker/finance-radar}"
BK_DIR="$APP_DIR/backups"
FILE="${1:-}"
if [[ -z "$FILE" ]]; then
  echo "用法: sudo bash scripts/restore.sh <备份文件名，位于 $BK_DIR>"; exit 1
fi
SRC="$BK_DIR/$FILE"; [[ -f "$SRC" ]] || SRC="$FILE"
[[ -f "$SRC" ]] || { echo "找不到备份: $SRC"; exit 1; }

PRE="$BK_DIR/pre-restore-$(date +%Y%m%d-%H%M%S).tgz"
tar -czf "$PRE" -C "$APP_DIR" ./data ./config.json ./docker-compose.yml ./static 2>/dev/null || true
echo "[GFIC] 恢复前状态已另存: $PRE"

tar -xzf "$SRC" -C "$APP_DIR"
echo "[GFIC] 已恢复。请重启容器使配置生效："
echo "  cd $APP_DIR && sudo docker compose restart"
echo "[GFIC] 建议执行冒烟测试确认：python3 tests/smoke_test.py --base http://127.0.0.1:6789"
