#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFIC 版本快照（在 NAS 上以 root 执行，只读采集 + 复制，不改动运行目录）

用法：
  sudo GFIC_SNAPSHOT_NAME=GFIC_V2.1 GFIC_SNAPSHOT_LABEL=GFIC_V2.1_升级完成版本 \
       python3 /vol1/1000/docker/finance-radar/scripts/snapshot.py

默认生成 /vol1/1000/docker/GFIC/backups/snapshots/GFIC_V2.1/，
包含：完整源码/前端/后端、凭据隔离、数据卷逐文件 + 独立 tar 备份与恢复演练、
容器/端口/网络/compose/环境变量/路由/API/版本信息、全文件 SHA256 清单、
以及一键回滚脚本。V2.0 升级前快照由同样逻辑生成，回滚脚本互不覆盖。
"""
import os, re, json, shutil, hashlib, subprocess, tarfile, time, sys

SRC = "/vol1/1000/docker/finance-radar"
ROOT = "/vol1/1000/docker/GFIC/backups"
SNAP_NAME = os.environ.get("GFIC_SNAPSHOT_NAME", "GFIC_V2.1")
DST = os.path.join(ROOT, "snapshots", SNAP_NAME)
NAME = os.environ.get("GFIC_SNAPSHOT_LABEL", SNAP_NAME + "_版本快照")
EXPECT_VERSION = os.environ.get("GFIC_EXPECT_VERSION", "GFIC 2.1")
GIT_COMMIT = os.environ.get("GFIC_GIT_COMMIT", "")
GIT_BRANCH = os.environ.get("GFIC_GIT_BRANCH", "")
GIT_TAG = os.environ.get("GFIC_GIT_TAG", "")

ROOT_FILES = ["server.py", "gfic_sources.py", "gfic_research.py", "gfic_i18n.py",
              "sources_catalog.json", "Dockerfile", "docker-compose.yml",
              ".dockerignore", ".env.example", "README.md", "CHANGELOG.md",
              "AUDIT_V2.0.md", "TEST_REPORT_V2.1.md"]
STATIC_FILES = ["index.html", "style.css", "app.js", "v21.css", "v21.js"]
EXTRA_FILES = ["scripts/backup.sh", "scripts/restore.sh", "scripts/snapshot.py",
               "tests/smoke_test.py", "tests/browser_test.py"]
SECRET_FILES = ["config.json"]
DATA_DIR = "data"

REPORT = {"snapshot": NAME, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
          "source_dir": SRC, "target_dir": DST,
          "git": {"commit": GIT_COMMIT, "branch": GIT_BRANCH, "tag": GIT_TAG},
          "files": {}, "checks": [], "errors": []}


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, "", str(e)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def check(name, cond, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)[:300]})
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (" · " + str(detail)[:160] if detail else ""))
    return bool(cond)


def redact(s):
    s = re.sub(r'((?:FR_LLM_KEY|API_KEY|TOKEN|PASSWORD|PASSWD|SECRET|AUTH)[A-Z_]*\s*[:=]\s*)(["\']?)([^\s"\',}]+)(\2)',
               r'\1\2***REDACTED***\4', s, flags=re.I)
    s = re.sub(r'([A-Za-z0-9_\-]{28,})',
               lambda m: "***REDACTED***" if re.search(r'[0-9]', m.group(0))
               and re.search(r'[a-z]', m.group(0), re.I) else m.group(0), s)
    return s


def write(p, text, mode=0o644):
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(p, mode)


def main():
    print("=" * 72)
    print("  " + NAME)
    print("  源: %s  →  快照: %s" % (SRC, DST))
    print("=" * 72)
    if os.path.exists(DST):
        REPORT["errors"].append("快照目录已存在，拒绝覆盖：" + DST)
        print("!! 快照目录已存在，拒绝覆盖（防止破坏旧快照）")
        return 2
    for d in ("", "source", "source/static", "source/scripts", "source/tests",
              "secrets", "data", "inspect"):
        os.makedirs(os.path.join(DST, d), exist_ok=True)
        # NAS 上 root 的 umask 曾把新建目录变成 000，导致非 root 无法遍历快照
        os.chmod(os.path.join(DST, d), 0o755)
    for parent in (ROOT, os.path.join(ROOT, "snapshots")):
        os.makedirs(parent, exist_ok=True)
        os.chmod(parent, 0o755)
    os.chmod(os.path.join(DST, "secrets"), 0o700)

    # ---- 1 源码 / 前端 / 脚本 / 测试 ----
    print("\n[1] 源码与静态资源")
    for f in ROOT_FILES:
        s = os.path.join(SRC, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(DST, "source", f))
    for f in STATIC_FILES:
        s = os.path.join(SRC, "static", f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(DST, "source", "static", f))
    for f in EXTRA_FILES:
        s = os.path.join(SRC, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(DST, "source", f))
    core = ["server.py", "gfic_sources.py", "gfic_research.py", "gfic_i18n.py",
            "Dockerfile", "docker-compose.yml", "sources_catalog.json"]
    check("后端四个模块 + 容器配置齐全",
          all(os.path.isfile(os.path.join(DST, "source", f)) for f in core), "%d 个" % len(core))
    check("前端五件套齐全（含 V2.1 扩展层）",
          all(os.path.isfile(os.path.join(DST, "source", "static", f)) for f in STATIC_FILES),
          ",".join(STATIC_FILES))
    check("测试与快照脚本已纳入",
          all(os.path.isfile(os.path.join(DST, "source", f)) for f in
              ("tests/smoke_test.py", "tests/browser_test.py", "scripts/snapshot.py")))

    # ---- 2 凭据隔离 ----
    print("\n[2] 凭据隔离与配置结构")
    for f in SECRET_FILES:
        s = os.path.join(SRC, f)
        if os.path.isfile(s):
            d = os.path.join(DST, "secrets", f)
            shutil.copy2(s, d)
            os.chmod(d, 0o600)
    cfg = json.load(open(os.path.join(SRC, "config.json"), encoding="utf-8"))

    def structure(o):
        if isinstance(o, dict):
            return {k: structure(v) for k, v in o.items()}
        if isinstance(o, list):
            return ["<%d items, type=%s>" % (len(o), type(o[0]).__name__ if o else "empty")]
        return type(o).__name__

    write(os.path.join(DST, "inspect", "config_structure.json"),
          json.dumps({"note": "仅配置结构，值（含 API Key）只在 secrets/ 中，权限 600",
                      "structure": structure(cfg)}, ensure_ascii=False, indent=2))
    check("凭据文件隔离且权限 600",
          os.path.isfile(os.path.join(DST, "secrets", "config.json")) and
          (os.stat(os.path.join(DST, "secrets", "config.json")).st_mode & 0o777) == 0o600)

    # ---- 3 环境变量 / 容器 / 端口 / compose ----
    print("\n[3] 容器 / 端口 / 网络 / 版本")
    code, out, _ = run("docker inspect finance-radar --format '{{range .Config.Env}}{{println .}}{{end}}'")
    env_keys = [l.split("=", 1)[0] for l in out.splitlines() if "=" in l]
    write(os.path.join(DST, "inspect", "env_structure.json"),
          json.dumps({"env_keys": env_keys, "note": "仅键名；值见 env_masked.txt（已脱敏）"},
                     ensure_ascii=False, indent=2))
    write(os.path.join(DST, "inspect", "env_masked.txt"),
          "\n".join(redact(l) for l in out.splitlines() if l.strip()) + "\n")
    check("环境变量结构已保存（值脱敏）", len(env_keys) > 5, "%d 个键" % len(env_keys))
    code, insp, err = run("docker inspect finance-radar")
    check("docker inspect 成功", code == 0 and insp.strip().startswith("["), err[:120])
    write(os.path.join(DST, "inspect", "container_inspect.json"), redact(insp))
    _, ports, _ = run("docker port finance-radar")
    _, ps, _ = run("docker ps --filter name=finance-radar --format '{{.Names}} | {{.Status}} | {{.Ports}} | {{.Image}}'")
    _, compose_cfg, _ = run("cd %s && docker compose config" % SRC)
    write(os.path.join(DST, "inspect", "ports_network.txt"),
          "=== docker port ===\n" + ports + "\n=== docker ps ===\n" + ps +
          "\n=== compose config（已脱敏） ===\n" + redact(compose_cfg))
    check("端口 6789 已记录", "6789" in ports, ports.strip())
    check("compose 配置已记录", "finance-radar" in compose_cfg)

    # ---- 4 路由 / API / 版本 ----
    appjs = open(os.path.join(SRC, "static", "app.js"), encoding="utf-8").read()
    v21js = open(os.path.join(SRC, "static", "v21.js"), encoding="utf-8").read()
    serverpy = open(os.path.join(SRC, "server.py"), encoding="utf-8").read()
    routes = re.findall(r"\{id:'([a-z0-9_]+)',\s*t:'([^']+)'", appjs)
    extra_views = sorted(set(re.findall(r"V\.([a-z0-9_]+)\s*=\s*async", v21js)))
    api_routes = sorted(set(re.findall(r'p\.path\s*==\s*["\'](/api/[^"\']+)', serverpy) +
                            re.findall(r'route\s*==\s*["\'](/api/[^"\']+)', serverpy)))
    detail_routes = sorted(set(re.findall(r'["\'](/api/detail|/stocks/|/news/)[^"\']*', v21js)))
    write(os.path.join(DST, "inspect", "routes.json"), json.dumps({
        "router": "hash SPA（NAV[] + V[view]）；V2.1 增加 detail/<type>/<id> 与 pathname 直达",
        "views": [{"id": a, "title": b} for a, b in routes],
        "view_count": len(routes), "v21_views": extra_views,
        "api_routes": api_routes, "api_route_count": len(api_routes),
        "detail_routes": detail_routes,
        "note": "V2.1 新增 /api/daily|research|detail|i18n 系列与 SPA fallback"
    }, ensure_ascii=False, indent=2))
    check("路由与 API 清单已记录", len(routes) >= 20 and len(api_routes) >= 20,
          "%d 视图 / %d API / V2.1 视图 %s" % (len(routes), len(api_routes), extra_views))
    _, status_txt, _ = run("curl -s --max-time 8 http://127.0.0.1:6789/api/status")
    try:
        live = json.loads(status_txt)
    except Exception:
        live = {"raw": status_txt[:200]}
    ver = {"snapshot_name": NAME, "captured_at": REPORT["created"],
           "git_commit": GIT_COMMIT, "git_branch": GIT_BRANCH, "git_tag": GIT_TAG,
           "service_version": live.get("version"), "capabilities": live.get("capabilities"),
           "news_count": live.get("news_count"), "quotes_count": live.get("quotes_count"),
           "sources": live.get("sources"), "container": "finance-radar",
           "image": "finance-radar:latest", "base_image": "python:3.12-alpine",
           "port": 6789, "network_mode": "bridge", "project_dir": SRC,
           "worker": "无独立 Worker；后台线程 _bg_loop / _warm_official / _warm_research",
           "database": "无关系型数据库；持久化数据为 data/*.json（JSON 文件卷）",
           "migrations": "无数据库迁移记录（文件型持久化）"}
    write(os.path.join(DST, "inspect", "version_info.json"), json.dumps(ver, ensure_ascii=False, indent=2))
    check("线上版本信息已记录", live.get("version") == EXPECT_VERSION,
          "%s（期望 %s）" % (live.get("version"), EXPECT_VERSION))

    # ---- 5 数据卷 + 独立数据库备份 + 恢复演练 ----
    print("\n[4] 数据卷 / 数据库备份（独立执行并验证）")
    data_src = os.path.join(SRC, DATA_DIR)
    data_files = sorted(f for f in os.listdir(data_src) if os.path.isfile(os.path.join(data_src, f)))
    for f in data_files:
        shutil.copy2(os.path.join(data_src, f), os.path.join(DST, "data", f))
    check("数据文件逐个复制", len(data_files) >= 8, "%d 个文件" % len(data_files))
    db_tar = os.path.join(DST, "database_backup.tar.gz")
    with tarfile.open(db_tar, "w:gz") as t:
        for f in data_files:
            t.add(os.path.join(data_src, f), arcname="data/" + f)
    os.chmod(db_tar, 0o600)
    check("独立数据库备份文件存在", os.path.isfile(db_tar) and os.path.getsize(db_tar) > 100,
          "%d B" % os.path.getsize(db_tar))
    with tarfile.open(db_tar, "r:gz") as t:
        names = t.getnames()
    check("备份可正常读取（tar 校验）", len(names) == len(data_files), "%d 项" % len(names))
    dry = "/tmp/gfic_%s_restore_dryrun" % SNAP_NAME.lower()
    shutil.rmtree(dry, ignore_errors=True)
    os.makedirs(dry)
    with tarfile.open(db_tar, "r:gz") as t:
        t.extractall(dry)
    same = all(sha(os.path.join(data_src, f)) == sha(os.path.join(dry, "data", f)) for f in data_files)
    check("恢复演练逐文件 SHA256 一致", same)
    json_ok = True
    for f in data_files:
        if f.endswith(".json"):
            try:
                json.load(open(os.path.join(dry, "data", f), encoding="utf-8"))
            except Exception as e:
                json_ok = False
                REPORT["errors"].append("恢复后 JSON 不可解析: %s %s" % (f, e))
    check("恢复后全部 JSON 可解析", json_ok)
    shutil.rmtree(dry, ignore_errors=True)

    # ---- 6 源码整包（不含凭据）----
    src_tar = os.path.join(DST, "source_backup.tar.gz")
    with tarfile.open(src_tar, "w:gz") as t:
        t.add(os.path.join(DST, "source"), arcname="source")
    os.chmod(src_tar, 0o644)
    check("源码整包可生成并读取", os.path.getsize(src_tar) > 1000 and
          len(tarfile.open(src_tar, "r:gz").getnames()) >= 15,
          "%d B" % os.path.getsize(src_tar))
    check("源码整包不含 config.json 明文",
          "config.json" not in "\n".join(tarfile.open(src_tar, "r:gz").getnames()))

    # ---- 7 回滚脚本 ----
    print("\n[5] 生成回滚 / 恢复脚本")
    # 回滚脚本后缀与交付文档保持一致：GFIC_V2.1 -> v2_1（而不是 gfic_v2_1）
    suffix = os.environ.get("GFIC_SNAPSHOT_SUFFIX") or \
             SNAP_NAME.lower().replace("gfic_", "").replace(".", "_")
    rollback = """#!/usr/bin/env bash
# GFIC 一键回滚到 %s
# 用法: sudo bash %s/rollback_to_%s.sh
set -euo pipefail
SNAP="%s"
APP="%s"
STAMP=$(date +%%Y%%m%%d-%%H%%M%%S)
PRE="%s/pre-rollback-$STAMP"
echo "== 0. 回滚前先自保：把当前状态另存 $PRE =="
mkdir -p "$PRE"
cp -a "$APP" "$PRE/app" 2>/dev/null || true
docker inspect finance-radar > "$PRE/container_inspect.json" 2>/dev/null || true
echo "== 1. 停止服务 =="
cd "$APP" && docker compose down 2>/dev/null || docker stop finance-radar || true
echo "== 2. 恢复代码（保留目录与 inode）=="
mkdir -p "$APP/static" "$APP/scripts" "$APP/tests" "$APP/data"
tar -xzf "$SNAP/source_backup.tar.gz" -C /tmp
cp -a /tmp/source/. "$APP"/
rm -rf /tmp/source
echo "== 3. 恢复凭据（600）=="
cp "$SNAP/secrets/config.json" "$APP/config.json" && chmod 600 "$APP/config.json"
echo "== 4. 恢复数据卷 =="
tar -xzf "$SNAP/database_backup.tar.gz" -C "$APP"
chown -R Peng "$APP"
find "$APP" -type d -exec chmod 755 {} +
find "$APP" -type f -exec chmod 644 {} +
chmod 600 "$APP/config.json"
chmod 755 "$APP/scripts"/*.sh
echo "== 5. 重建并启动容器 =="
cd "$APP" && docker compose up -d --build
echo "== 6. 健康检查 =="
for i in $(seq 1 30); do
  C=$(curl -s --max-time 3 -o /dev/null -w '%%{http_code}' http://127.0.0.1:6789/api/status || true)
  [ "$C" = "200" ] && break
  sleep 2
done
curl -s --max-time 5 http://127.0.0.1:6789/api/status
echo
docker ps --filter name=finance-radar --format '{{.Names}} | {{.Status}} | {{.Ports}}'
echo "== 回滚完成；回滚前现场保存在 $PRE =="
""" % (NAME, ROOT, suffix, DST, SRC, ROOT)
    write(os.path.join(DST, "rollback_to_%s.sh" % suffix), rollback, 0o755)
    write(os.path.join(ROOT, "rollback_to_%s.sh" % suffix), rollback, 0o755)
    write(os.path.join(ROOT, "restore_db_%s.sh" % suffix), """#!/usr/bin/env bash
# 仅恢复数据卷（恢复前先备份当前数据）
set -euo pipefail
SNAP="%s"
APP="%s"
STAMP=$(date +%%Y%%m%%d-%%H%%M%%S)
cp -a "$APP/data" "%s/data-before-db-restore-$STAMP"
tar -xzf "$SNAP/database_backup.tar.gz" -C "$APP"
chown -R Peng "$APP/data"
docker restart finance-radar
echo "数据卷已恢复；恢复前数据：%s/data-before-db-restore-$STAMP"
""" % (DST, SRC, ROOT, ROOT), 0o755)
    check("一键回滚脚本已生成",
          os.path.isfile(os.path.join(ROOT, "rollback_to_%s.sh" % suffix)))

    # ---- 8 清单 / 说明 ----
    print("\n[6] 清单与说明")
    filelist = {}
    for base, _, fs in os.walk(DST):
        for f in fs:
            p = os.path.join(base, f)
            filelist[os.path.relpath(p, DST)] = {"size": os.path.getsize(p), "sha256": sha(p)}
    REPORT["files"] = filelist
    REPORT["total_files"] = len(filelist)
    REPORT["total_bytes"] = sum(v["size"] for v in filelist.values())
    manifest = dict(REPORT)
    manifest["security"] = {
        "secrets_dir": "secrets/ (0700), config.json (0600)",
        "source_backup_tar": "不含 config.json",
        "container_inspect": "已脱敏 KEY/TOKEN/PASS/SECRET",
        "git": "本快照目录不得加入任何 Git 仓库；含凭据",
        "restore": "sudo bash %s/rollback_to_%s.sh" % (ROOT, suffix),
        "rollback_to_v2.0": "sudo bash %s/rollback_to_v2.0.sh" % ROOT,
    }
    write(os.path.join(DST, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
    readme = """# %s

- 创建时间：%s
- 源目录：`%s`（采集过程不修改运行目录）
- 快照目录：`%s`
- Git：`%s` @ `%s`（tag `%s`）
- 线上版本：%s · %d 视图 · %d 个 API 路由
- 文件数：%d，总字节：%d

## 一键回滚

```bash
sudo bash %s/rollback_to_%s.sh     # 回到本快照
sudo bash %s/rollback_to_v2.0.sh   # 回到升级前 V2.0
```

回滚脚本会**先把当前现场另存** `backups/pre-rollback-<时间戳>/`，再停服 → 还原代码 →
还原凭据 → 还原数据 → 重建容器 → 健康检查。

## 目录

| 路径 | 内容 |
|---|---|
| `source/` | 完整源码：后端 4 个模块、前端 5 文件、脚本、测试、Dockerfile、compose、文档 |
| `source_backup.tar.gz` | 源码整包（不含凭据） |
| `secrets/config.json` | 真实配置，权限 600，**绝不入库** |
| `data/` + `database_backup.tar.gz` | 持久化数据逐文件副本与独立备份（已做恢复演练 + SHA256 校验） |
| `inspect/` | 容器/端口/网络/compose/环境变量/路由/API/版本信息（脱敏） |
| `manifest.json` | 全文件 SHA256 清单 + 校验结果（600） |

> 本系统无关系型数据库、无 Redis、无独立 Worker；持久化 = `data/*.json`。
""" % (NAME, REPORT["created"], SRC, DST, GIT_BRANCH, GIT_COMMIT, GIT_TAG,
       ver.get("service_version"), len(routes), len(api_routes),
       len(filelist), REPORT["total_bytes"], ROOT, suffix, ROOT)
    write(os.path.join(DST, "README.md"), readme)
    check("manifest 不含明文密钥",
          "api_key\": \"" not in open(os.path.join(DST, "manifest.json"), encoding="utf-8").read())

    ok = all(c["ok"] for c in REPORT["checks"])
    REPORT["verified"] = ok
    print("\n" + "=" * 72)
    print("  快照校验： %d 项通过 / %d 项失败 · %d 文件 / %d B" %
          (sum(1 for c in REPORT["checks"] if c["ok"]),
           sum(1 for c in REPORT["checks"] if not c["ok"]),
           REPORT["total_files"], REPORT["total_bytes"]))
    print("=" * 72)
    print("SNAPSHOT_JSON=" + json.dumps({k: REPORT[k] for k in
          ("verified", "total_files", "total_bytes", "errors", "git")}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
