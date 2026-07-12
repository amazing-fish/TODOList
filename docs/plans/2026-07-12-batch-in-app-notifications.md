# Batch In-App Notifications Implementation Plan

> **For AI:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将多个任务到期时层层叠加的模态弹窗改为单一非模态软件内汇总窗口，并支持选择后批量完成或推迟。

**Architecture:** `tick_update` 收集一轮提醒请求并在入队前更新提醒标记；主窗口持有至多一个 `NotificationDialog`，新请求按 ID 追加或升级状态。对话框只维护展示与选择，通过信号把批量操作交回主窗口统一保存。

**Tech Stack:** Python、PySide6、`unittest`

---

### Task 1: 汇总对话框行模型与批量信号

**Files:**
- Create: `tests/test_notifications.py`
- Modify: `todo_app/dialogs.py`

**Step 1: Write failing dialog tests**

测试真实 `NotificationDialog`：

- 构造时加入两个任务，`task_ids()` 返回两个 ID，标题显示数量。
- 再次加入同一 ID 不增加行；`is_due=True` 将状态升级为“已到期”。
- 默认全选；取消一行后，“完成选中”信号只发送仍选中的 ID。
- `remove_tasks` 只移除指定行，空列表时关闭。

**Step 2: Run tests and verify RED**

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest tests.test_notifications.NotificationDialogTest -v
```

Expected: FAIL，因为当前对话框只接受单任务且没有汇总 API。

**Step 3: Implement minimal aggregate dialog**

在 `NotificationDialog` 中增加：

```python
complete_requested = Signal(list)
snooze_requested = Signal(list, object)

def add_or_update_tasks(self, requests: list[tuple[dict, bool]]) -> None: ...
def task_ids(self) -> list[int]: ...
def selected_task_ids(self) -> list[int]: ...
def remove_tasks(self, task_ids: list[int]) -> None: ...
```

用任务 ID 映射复选框、文本和状态标签。保留现有 15 分钟、1 小时、晚上 8 点、明天 9 点计算函数，但改为发出选中 ID 与 duration，不在对话框内关闭整个批次。

**Step 4: Run tests and verify GREEN**

运行 `NotificationDialogTest`，预期全部通过。

### Task 2: 一轮收集只创建一个非模态窗口

**Files:**
- Modify: `tests/test_notifications.py`
- Modify: `todo_app/main_window.py`

**Step 1: Write failing integration test**

离屏实例化 `ModernTodoAppWindow`，停止计时器并替换存储/声音副作用。放入三个同一时刻到期任务后调用 `tick_update()`，断言：

- `_notification_dialog` 只有一个实例；
- 对话框包含三个任务 ID；
- `NotificationDialog.exec` 未调用，`show` 只调用一次；
- 软件提醒音只调用一次；
- 三个任务的提醒标记在返回前已更新。

再加入第四个任务并调用下一轮，断言复用同一窗口并追加第四行。

**Step 2: Run test and verify RED**

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest tests.test_notifications.NotificationBatchIntegrationTest -v
```

Expected: FAIL；当前实现为每个任务调用一次模态 `exec()`。

**Step 3: Implement batch collection**

- 将 `active_notifications` 替换为单一 `_notification_dialog` 引用。
- 提醒扫描遍历完整 `self.todos`，当前可见卡片只负责刷新倒计时，避免筛选隐藏任务后漏检。
- 把 `_check_for_notification` 改为返回可选 `(todo, is_due)` 请求，并在返回前更新 `notifiedForReminder`、`notifiedForDue` 与 `lastNotifiedAt`。
- `tick_update` 收集本轮请求，统一保存并调用 `_show_notification_batch`。
- `_show_notification_batch` 只使用 `show()`；已有窗口则追加。
- 汇总窗口启用 `WA_DeleteOnClose`，关闭后清理主窗口引用并释放 Qt 子对象与主题信号连接。
- 同轮根据最高严重级播放一次软件音，不调用 `QSystemTrayIcon.showMessage`。

**Step 4: Run integration tests and full suite**

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest tests.test_notifications -v
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest discover -s tests -v
```

Expected: targeted and full suite pass。

另验证筛选为“已完成”时隐藏的未完成到期任务仍进入汇总窗口，连续关闭批次后父窗口不残留 `NotificationDialog` 子对象。

### Task 3: 批量完成、推迟与外部状态同步

**Files:**
- Modify: `tests/test_notifications.py`
- Modify: `todo_app/main_window.py`

**Step 1: Write failing action tests**

验证：

- `_handle_notification_complete([1, 2])` 只完成任务 1、2，一次保存和一次刷新，并从对话框移除两行。
- `_handle_notification_snooze([2], duration)` 只调用现有 `build_snooze_update_fields` 更新任务 2，任务 1 不变。
- 编辑、删除或列表完成任务时调用统一移除方法；不存在的 ID 不报错。
- 关闭汇总窗口后主窗口引用清空，提醒标记保持，下一 tick 不立即重弹。

**Step 2: Verify RED**

运行新 action tests，预期因处理方法不存在而失败。

**Step 3: Implement action handlers**

- 信号连接到 `_handle_notification_complete` 与 `_handle_notification_snooze`。
- 每个批量操作只保存和刷新一次。
- 增加 `_remove_notification_task(todo_id)`，供编辑、删除、列表完成和应用关闭复用。
- 对话框 `finished` 后仅清理引用，不重置已写入的提醒标记。
- 主窗口隐藏或关闭到托盘时调用 `hide()` 同步隐藏提醒窗口但保留实例，从托盘恢复时重新 `show/raise/activate`；仅在真正退出时关闭提醒实例。

**Step 4: Verify GREEN**

运行 action tests 与完整测试套件。

### Task 4: 版本、文档与 GUI 验证

**Files:**
- Modify: `todo_app/constants.py`
- Modify: `README.md`
- Modify: `anchor.md`

**Step 1: Update docs**

- `APP_VERSION` 更新到 `1.7.12`。
- README 记录多个到期任务在一个软件内窗口汇总。
- anchor 记录单窗口、不使用系统任务通知、入队先写标记和批量操作不变量。

**Step 2: Required automated verification**

```powershell
& 'D:\Develop\Tool\Miniconda\envs\try\python.exe' -m unittest discover -s tests -v
python -m compileall todo_app
git diff --check
```

**Step 3: Actual GUI verification**

- 两个或三个任务同时到期，只出现一个软件内汇总窗口。
- 默认全选、取消选择、完成选中、推迟选中和忽略全部正常。
- 窗口打开期间新增到期任务追加，不另开窗口。
- 主窗口仍可操作；编辑、删除、列表完成同步移除行。
- 深浅主题和窗口前置正常；无 Windows 系统任务通知。

### Task 5: Review and publish

**Files:**
- No new files

**Step 1: Independent code review**

审查定时器重入、信号生命周期、重复 ID、状态升级、保存次数、关闭应用和主题切换。

**Step 2: Commit and push**

使用中文提交信息，推送 `codex/batch-in-app-notifications`。

**Step 3: Create ready-for-review PR**

PR 使用中文说明用户价值、验证、风险、非目标，并包含 `Closes #42`。

**Step 4: Follow review loop**

等待 10 分钟，检查评论、threads、requested changes、checks 与 mergeability；满足条件后合并并确认 Issue #42 关闭。
