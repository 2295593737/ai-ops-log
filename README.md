# ai-ops-log

AI 操作日志的私有归档。每天 22:00 自动生成一份 `logs/YYYY-MM-DD.md` 并推送。

**只记录工作痕迹**：git 提交、当日修改的文件名、工作区记忆笔记。不包含对话原文。

## 结构

```
logs/
  2026-10-30.md        # 按天一个文件
tools/
  daily_log.py         # 生成器：采集 -> 渲染 -> 提交 -> 推送
README.md
```

## 手动用法

```bash
python tools/daily_log.py                 # 生成今天并推送
python tools/daily_log.py --no-push       # 只生成本地文件
python tools/daily_log.py --date 2026-10-29
python tools/daily_log.py --dry-run       # 只打印，不落盘
```

当天没有任何提交、文件改动或笔记时，脚本直接跳过，**不会产生空提交**。

## 采集范围

- 根目录：`C:\Users\74246\WorkBuddy`（可用环境变量 `AI_LOG_ROOT` 覆盖）
- 向下最多 3 层查找含 `.git` 的仓库，统计当天提交
- 各工作区 `.workbuddy/memory/YYYY-MM-DD.md` 作为当日笔记
- 跳过 `.git`、`node_modules`、`__pycache__`、`venv`、`dist` 等目录

## 为什么不放进公开档案仓

`ai-personal-profile` 是公开仓库，而操作日志会暴露具体文件路径、提交内容和项目线索。所以单独放这里，保持 private。
