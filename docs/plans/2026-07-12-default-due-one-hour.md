# Default Due Time One Hour Later Implementation Plan

> **For AI:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让新增任务的默认截止时间始终为当前本地时间一小时后，并按分钟精度保存。

**Architecture:** 在 `todo_app/dialogs.py` 增加模块内纯计算函数，输入当前 `QDateTime`，输出加一小时且秒/毫秒归零的目标值。新增对话框从同一个目标值设置日期与时间；已有任务编辑流程保持不变。

**Tech Stack:** Python、PySide6、`unittest`

---

### Task 1: 用确定性测试锁定默认时间规则

**Files:**
- Modify: `tests/test_dialogs.py`
- Modify: `todo_app/dialogs.py`

**Step 1: Write the failing test**

在 `tests/test_dialogs.py` 导入 `_default_due_datetime`，添加三个子用例：

```python
def test_default_due_datetime_is_exactly_one_visible_hour_later(self) -> None:
    cases = [
        (QDateTime(QDate(2026, 7, 12), QTime(13, 42, 37, 500)), QDateTime(QDate(2026, 7, 12), QTime(14, 42))),
        (QDateTime(QDate(2026, 7, 12), QTime(23, 30)), QDateTime(QDate(2026, 7, 13), QTime(0, 30))),
        (QDateTime(QDate(2026, 7, 12), QTime(5, 30)), QDateTime(QDate(2026, 7, 12), QTime(6, 30))),
    ]
    for now, expected in cases:
        with self.subTest(now=now.toString(Qt.DateFormat.ISODateWithMs)):
            self.assertEqual(_default_due_datetime(now), expected)
```

**Step 2: Run test to verify it fails**

Run:

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest tests.test_dialogs.TaskEditDialogTest.test_default_due_datetime_is_exactly_one_visible_hour_later -v
```

Expected: FAIL because `_default_due_datetime` does not exist.

**Step 3: Write minimal implementation**

在 `todo_app/dialogs.py` 增加：

```python
def _default_due_datetime(now_qdt: QDateTime) -> QDateTime:
    target = now_qdt.addSecs(3600)
    target.setTime(QTime(target.time().hour(), target.time().minute()))
    return target
```

新增对话框中：

```python
default_due = _default_due_datetime(QDateTime.currentDateTime())
self.date_edit.setDate(default_due.date())
self.time_edit.setTime(default_due.time())
```

删除凌晨改为 09:00 和日期强制设为今天的旧逻辑。

**Step 4: Run test to verify it passes**

Run targeted test, then:

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest discover -s tests -v
```

Expected: targeted test and full suite pass.

### Task 2: 同步版本和交互文档

**Files:**
- Modify: `todo_app/constants.py`
- Modify: `README.md`
- Modify: `anchor.md`

**Step 1: Update behavior documentation**

- 将 `APP_VERSION` 更新到 `1.7.11`。
- README 说明新增任务默认截止时间严格为一小时后。
- anchor 更新当前版本、截止时间交互约定和最近变更。

**Step 2: Verify documentation consistency**

Run:

```powershell
rg -n "1\.7\.10|1\.7\.11|一小时" README.md anchor.md todo_app/constants.py
```

Expected: 当前版本只指向 `1.7.11`，历史记录保留 `v1.7.10`。

### Task 3: GUI 与提交前验证

**Files:**
- No new files

**Step 1: Run required automated verification**

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest discover -s tests -v
python -m compileall todo_app
git diff --check
```

Expected: all commands exit 0.

**Step 2: Run GUI verification**

实际运行应用，验证：

- 新增对话框启用截止时间后日期与时间来自同一个一小时后目标；
- 滚轮调时、日期下拉、保存、再次编辑和 Escape 取消正常；
- 深浅主题控件可读；
- 已有任务的提醒/延后字段不因内容编辑而改变。

**Step 3: Commit the implementation**

```powershell
git add README.md anchor.md tests/test_dialogs.py todo_app/constants.py todo_app/dialogs.py
git commit -m "修复：默认截止时间设为一小时后"
```

### Task 4: 推送并创建聚焦 PR

**Files:**
- No new files

**Step 1: Push branch**

```powershell
git push -u origin codex/default-due-one-hour
```

**Step 2: Create ready-for-review PR**

PR 使用中文说明变更、用户价值、验证、风险、非目标，并包含 `Closes #40`。

**Step 3: Follow repository review loop**

创建后等待 10 分钟，检查普通评论、inline comments、unresolved threads、requested changes、checks 与 mergeability；满足条件后按现有方式合并并确认 Issue #40 自动关闭。
