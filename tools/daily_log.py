#!/usr/bin/env python3
"""生成并推送当天的 AI 操作日志。

只采集「工作痕迹」：git 提交、当日修改的文件、工作区记忆笔记。
不读取、不写入任何对话原文。

用法：
    python tools/daily_log.py                # 生成今天并推送
    python tools/daily_log.py --no-push      # 只生成，不推送
    python tools/daily_log.py --date 2026-10-29
    python tools/daily_log.py --dry-run      # 打印到终端，不写文件

退出码：0 成功（含「当天无记录」）；1 出错。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent

# 采集范围：这些目录下一层的文件夹里，含 .git 的算一个仓库，含 .workbuddy 的算一个工作区
ROOTS = [
    Path(os.environ.get("AI_LOG_ROOT", r"C:\Users\74246\WorkBuddy")),
]

# 不采集的目录名（任意层级）
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".idea", ".vscode", ".next", "target"}

# 不采集的仓库（自身日志仓 + 只读的上游克隆）
SKIP_REPOS = {"ai-ops-log"}

GIT_NAME = "2295593737"
GIT_EMAIL = "2295593737@users.noreply.github.com"

MAX_FILES_LISTED = 20
MAX_NOTE_LINES = 40


def run(cmd: list[str], cwd: Path) -> str:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return p.stdout.strip()
    except Exception:
        return ""


def discover(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def discover_repos() -> list[Path]:
    """向下最多 3 层找含 .git 的目录；命中后不再深入。"""
    repos: list[Path] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            p = Path(dirpath)
            if p == root:
                depth = 0
            else:
                depth = len(p.relative_to(root).parts)
            if depth >= 3:
                dirnames[:] = []
                continue
            if (p / ".git").exists():
                repos.append(p)
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    return [r for r in repos if r.name not in SKIP_REPOS and r.resolve() != REPO_DIR]


def collect_commits(day: str) -> dict[str, list[dict]]:
    """返回 {仓库名: [提交信息]}，只统计指定日期（本地时区）。"""
    result: dict[str, list[dict]] = {}
    since = f"{day} 00:00:00"
    until = f"{day} 23:59:59"
    for d in discover_repos():
        raw = run(["git", "log", f"--since={since}", f"--until={until}",
                   "--pretty=format:%h%x1f%s%x1f%ad", "--date=format:%H:%M",
                   "--shortstat"], d)
        if not raw:
            continue
        entries: list[dict] = []
        current = None
        for line in raw.splitlines():
            if "\x1f" in line:
                sha, subject, tm = line.split("\x1f", 2)
                current = {"sha": sha.strip(), "subject": subject.strip(), "time": tm.strip(), "stat": ""}
                entries.append(current)
            elif line.strip() and current is not None:
                stat = line.strip()
                parts = []
                for frag in stat.split(","):
                    frag = frag.strip()
                    if not frag:
                        continue
                    num = frag.split()[0]
                    if "file" in frag:
                        parts.append(f"{num} 个文件")
                    elif "insertion" in frag:
                        parts.append(f"+{num}")
                    elif "deletion" in frag:
                        parts.append(f"-{num}")
                current["stat"] = " ".join(parts)
        if entries:
            result[d.name] = entries
    return result


def collect_files(day: str) -> list[tuple[str, str, str]]:
    """返回 [(相对路径, 时间, 所属工作区)]，按修改时间倒序。"""
    target = dt.date.fromisoformat(day)
    found: list[tuple[str, str, str]] = []
    for root in ROOTS:
        for ws in discover(root):
            for dirpath, dirnames, filenames in os.walk(ws):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".workbuddy")]
                for name in filenames:
                    if name.endswith((".pyc", ".log", ".tmp")):
                        continue
                    fp = Path(dirpath) / name
                    try:
                        mtime = dt.datetime.fromtimestamp(fp.stat().st_mtime)
                    except OSError:
                        continue
                    if mtime.date() != target:
                        continue
                    try:
                        rel = fp.relative_to(ws).as_posix()
                    except ValueError:
                        rel = fp.as_posix()
                    found.append((rel, mtime.strftime("%H:%M"), ws.name))
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def collect_notes(day: str) -> dict[str, str]:
    """收集各工作区当天的记忆笔记。"""
    notes: dict[str, str] = {}
    for root in ROOTS:
        for ws in discover(root):
            f = ws / ".workbuddy" / "memory" / f"{day}.md"
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not text:
                continue
            lines = text.splitlines()
            if len(lines) > MAX_NOTE_LINES:
                text = "\n".join(lines[:MAX_NOTE_LINES]) + f"\n\n…（已截断，全文 {len(lines)} 行）"
            notes[ws.name] = text
    return notes


def render(day: str, commits: dict, files: list, notes: dict) -> str:
    n_commits = sum(len(v) for v in commits.values())
    out: list[str] = [
        f"# AI 操作日志 · {day}",
        "",
        "> 由 `tools/daily_log.py` 自动生成，只记录工作痕迹，不含对话原文。",
        "",
        "## 概览",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 提交 | {n_commits} 个（{len(commits)} 个仓库） |",
        f"| 当日修改文件 | {len(files)} 个 |",
        f"| 工作区笔记 | {len(notes)} 份 |",
        "",
    ]

    if commits:
        out += ["## 提交明细", ""]
        for repo, entries in commits.items():
            out.append(f"### {repo}")
            out.append("")
            for e in entries:
                stat = f"｜{e['stat']}" if e["stat"] else ""
                out.append(f"- `{e['sha']}` {e['time']} {e['subject']}{stat}")
            out.append("")

    if notes:
        out += ["## 工作区笔记", ""]
        for ws, text in notes.items():
            out.append(f"### {ws}")
            out.append("")
            out.append(text)
            out.append("")

    if files:
        out += ["## 当日修改的文件", ""]
        for rel, tm, ws in files[:MAX_FILES_LISTED]:
            out.append(f"- `{tm}` {ws}/{rel}")
        if len(files) > MAX_FILES_LISTED:
            out.append(f"- …另有 {len(files) - MAX_FILES_LISTED} 个文件未列出")
        out.append("")

    if not (commits or files or notes):
        out += ["## 记录", "", "当天没有可追溯的工作痕迹。", ""]

    return "\n".join(out)


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}", *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = args.date
    dt.date.fromisoformat(day)  # 校验格式

    commits = collect_commits(day)
    files = collect_files(day)
    notes = collect_notes(day)

    if not (commits or files or notes):
        print(f"{day}: 当天无工作痕迹，跳过（不产生空提交）")
        return 0

    content = render(day, commits, files, notes)

    if args.dry_run:
        print(content)
        return 0

    target = REPO_DIR / "logs" / f"{day}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"已写入 {target.relative_to(REPO_DIR)}")

    if args.no_push:
        return 0

    rel = target.relative_to(REPO_DIR).as_posix()
    add = git(["add", rel], REPO_DIR)
    if add.returncode != 0:
        print(f"git add 失败：{add.stderr}", file=sys.stderr)
        return 1

    commit = git(["commit", "-m", f"log({day}): 每日 AI 操作日志"], REPO_DIR)
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            print("内容与上次一致，跳过提交")
            return 0
        print(f"git commit 失败：{commit.stderr}", file=sys.stderr)
        return 1

    push = git(["push"], REPO_DIR)
    if push.returncode != 0:
        print(f"git push 失败：{push.stderr}", file=sys.stderr)
        return 1
    print(f"已推送：{day} 日志")
    return 0


if __name__ == "__main__":
    sys.exit(main())
