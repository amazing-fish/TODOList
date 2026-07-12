# 简化截止时间编辑 Implementation Plan

> **For AI:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以低频日期下拉和高频滚轮时间控件替代独立模态日历流程。

**Architecture:** 改动限定在 `TaskEditDialog` 的截止时间表单边界；存储仍使用现有 `dueDate` UTC 字段，调度模块不变。

**Tech Stack:** Python 3、PySide6、`unittest`。

---

### Task 1: 写失败的控件契约测试

**Files:**
- Modify: `tests/test_dialogs.py`

1. 断言时间控件是 `QTimeEdit` 且格式为 `HH:mm`。
2. 断言日期控件是启用 `calendarPopup` 的 `QDateEdit`。
3. 断言启用截止时间后可组合指定日期与时间，关闭后返回 `dueDate=None`。
4. 运行目标测试并确认因旧控件结构失败。

### Task 2: 最小替换截止时间控件

**Files:**
- Modify: `todo_app/dialogs.py`

1. 用内联 `QDateEdit` 和 `QTimeEdit` 替换日期标签、图标和自定义日历窗口。
2. 更新新增默认值、编辑回显、切换显示、保存与校验逻辑。
3. 运行目标测试和完整测试。

### Task 3: 删除旧路径并同步主题/资源

**Files:**
- Modify: `todo_app/dialogs.py`
- Modify: `todo_app/constants.py`
- Delete: `assets/icons/calendar_icon.svg`

1. 删除旧弹窗方法、内部日期镜像状态和无用样式。
2. 为日期下拉和时间控件补齐主题样式。
3. 搜索并确认无旧符号或资源引用。

### Task 4: 文档、版本与完整验证

**Files:**
- Modify: `README.md`
- Modify: `anchor.md`
- Modify: `todo_app/constants.py`

1. 按 bugfix 约定更新版本至 `1.7.10`，同步 README 与锚点。
2. 运行完整自动化测试、`python -m compileall todo_app` 和 `git diff --check`。
3. 实际运行 GUI，验证新增、编辑、日期下拉、滚轮调时、取消、提醒设置与主题。
4. 中文提交、推送并创建关联 `#38` 的 ready PR。
