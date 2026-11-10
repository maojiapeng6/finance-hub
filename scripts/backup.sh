#!/usr/bin/env bash
# GFIC 备份：在 NAS 上执行（可加入定时任务）
# 备份内容：业务数据 data/、配置、compose、源目录、静态资源
# 用法：sudo bash /vol1/1000/docker/finance-radar/scripts/backup.sh
set -euo pipefail
APP_DIR="${GFIC_DIR:-/vol1/1000/docker/finance-radar}"
BK_DIR="$APP_DIR/backups"
TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK_DIR"
OUT="$BK_DIR/gfic-$TS.tgz"
tar -czf "$OUT" \
  -C "$APP_DIR" \
  --exclude='./backups' --exclude='./_tmp' --exclude='*.pyc' \
  ./data ./config.json ./sources_catalog.json ./docker-compose.yml ./Dockerfile ./static 2>/dev/null || \
tar -czf "$OUT" -C "$APP_DIR" ./data ./config.json ./docker-compose.yml ./static
# 只保留最近 14 份
ls -1t "$BK_DIR"/gfic-*.tgz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "[GFIC] 备份完成: $OUT ($(du -h "$OUT" | cut -f1))"
echo "[GFIC] 现有备份:"; ls -1t "$BK_DIR"/gfic-*.tgz 2>/dev/null | head -5
