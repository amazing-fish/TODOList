# 内容编辑保留延后状态 Implementation Plan

> **For AI:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复语义相同的截止时间因字符串格式和 Qt 精度差异被误判为调度修改的问题。

**Architecture:** 在 `todo_app/scheduling.py` 的调度边界完成时间语义比较。内容编辑复用已有截止时间原值；真正的调度编辑继续走现有重置路径。

**Tech Stack:** Python 3、`datetime`、`unittest`、PySide6 GUI 手工验证。

---

### Task 1: 添加失败回归测试

**Files:**
- Modify: `tests/test_scheduling.py`

1. 添加 Qt 往返后时区改变、微秒截断但时刻相同的内容编辑用例。
2. 断言结果保留原始 `dueDate`，且不返回任何调度重置字段。
3. 运行目标测试并确认因字符串比较而失败。

### Task 2: 最小修复时间比较边界

**Files:**
- Modify: `todo_app/scheduling.py`

1. 使用现有解析函数把两个合法时间统一为 UTC 并截断到毫秒精度。
2. 语义相同时保留 existing `dueDate`；语义不同时写入新值并重置调度状态。
3. 运行目标测试与完整测试套件。

### Task 3: 覆盖真实调度变化并同步文档

**Files:**
- Modify: `tests/test_scheduling.py`
- Modify: `README.md`
- Modify: `anchor.md`
- Modify: `todo_app/constants.py`

1. 补充真实分钟变化、提醒偏移变化仍重置的测试。
2. 按 bugfix 约定更新版本至 `1.7.9`，同步 README 与锚点。
3. 运行 `python -m unittest discover -s tests -v`、`python -m compileall todo_app` 和 `git diff --check`。

### Task 4: GUI 验证与交付

1. 在隔离数据中延后任务，记录新截止时间。
2. 仅编辑内容并保存，确认新截止时间、延后倒计时和通知状态保持。
3. 提交中文 commit，推送并创建关联 `#36` 的 ready-for-review PR。
