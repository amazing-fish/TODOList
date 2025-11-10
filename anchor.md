# 项目锚点（Anchor）

> 每轮改动的起点与终点。开始动手前先复盘本文件，收尾时确认约定依然成立，如有变化请在此同步。
> 违背锚点将直接影响模型产出的稳定性与交付质量。

## 使用方式
- **开工前 3 步**：①阅读需求和变更背景；②通读本锚点，划线本次相关的约束；③在心里预演改动对存储、UI、资源和文档的影响。
- **交付后检查**：功能落地或约定发生变化时，必须回写锚点；若锚点未变更，请在提交说明中确认“锚点已复盘，无需更新”。
- **复盘频率**：涉及多轮讨论或多人协作的任务，每轮进入实现前都要重新检查锚点，避免上下文漂移。

## 项目速览
- **定位**：基于 PySide6 的桌面待办事项管理工具，强调现代化视觉、提醒/延迟机制与轻量本地存储。
- **入口**：`main.py` 调用 `todo_app.run()`，由 `ModernTodoAppWindow`（`todo_app/main_window.py`）驱动 UI 与业务流。
- **运行**：开发环境可执行 `python main.py`；GitHub Actions 工作流 `build-exe.yml` 负责生成 Windows 平台单文件可执行程序，并在推送 `v*` 标签
  时上传到 Release。
- **依赖要点**：PySide6 GUI 组件、`QSoundEffect` 播放提醒、`todos.json` 做本地数据缓存。

## 代码结构速查
- `todo_app/app.py`：应用初始化、消息过滤与窗口展示。
- `todo_app/main_window.py`：主窗口、过滤排序逻辑、系统托盘、提醒计时器、状态保存。
- `todo_app/dialogs.py`：任务编辑对话框与提醒弹窗，负责校验输入、配置提醒与打盹选项。
- `todo_app/widgets.py`：待办卡片视图与交互按钮，响应主题变化、完成状态切换、计时显示。
- `todo_app/storage.py`：JSON 数据的读写与迁移，保证旧数据补全字段。
- `todo_app/theme.py`：主题检测与切换，提供 `ThemeManager` 单例。
- `todo_app/utils.py`：图标加载、声音播放、文本截断等通用工具。
- `todo_app/constants.py`：项目常量、主题色板、资源路径。
- `todo_app/paths.py`：基础路径与 `todos.json` 存放位置。

## 数据约束
- 所有待办保存在项目根目录下的 `todos.json`，结构为列表，元素为字典；打包版运行时会改存至用户数据目录（Windows `%APPDATA%\TODOList`，
  其他平台 `~/.todolist/`）。
- 字段约定：
  - `id`（int）唯一标识；缺失或非法时由 `_migrate_and_validate_todo_item` 重新生成。
  - `text`（str）任务内容，UI 侧以富文本/纯文本显示，需兼容多行但在列表中会截断显示。
  - `createdAt`（ISO8601 str，UTC），缺失时写入当前时间。
  - `completed`（bool）、`priority`（"高"|"中"|"低"）、`dueDate`（ISO8601 str 或 `None`）。
  - `reminderOffset`（int 秒，-1 表示不提醒）、`snoozeUntil`、`lastNotifiedAt`（ISO8601 str 或 `None`）。
  - `notifiedForReminder`、`notifiedForDue`（bool）用于提醒状态去重。
- 修改字段或新增元数据时：同步更新 `storage.py` 的迁移逻辑、`TaskEditDialog` 的表单、`TodoItemWidget` 的展示，以及锚点此处的说明。

## 交互与视觉关键点
- 主题：通过 `ThemeManager` 监听系统配色；新增控件需调用 `apply_palette` 或监听 `theme_changed`。
- 列表交互：
  - 过滤/排序选项在主窗口初始化时定义，新增选项需更新 `update_list_widget` 的分支与文案。
  - 列表项使用 `TodoItemWidget`，按钮图标依赖 `assets/icons`，缺失时 `utils.get_icon` 会自动降级并打印警告。
- 提醒流程：`master_timer` 每秒触发 `tick_update` 检查到期任务，提醒音通过 `play_sound_effect` 播放，可根据资源情况提供回退字符或系统提示音。
- 托盘行为：系统托盘菜单与最小化逻辑集中在 `main_window.py::_create_tray_icon`，调整时注意多平台兼容；点击窗口最小化按钮会直接隐藏到托盘，提醒触发时会自动还原窗口并置顶。

## 资源约束
- 所有 SVG/音频资源路径在 `constants.py` 中声明，新增资源需：①放入 `assets` 子目录；②在常量中登记；③如为图标，保证 SVG 可在浅/深色主题下辨识。
- 缺失资源时工具函数会打印警告，需在提交前确认是否属于预期。

## 工作流检查表
### 开始前
1. 复盘需求与本锚点，确认涉及模块与数据字段。
2. 明确是否需要调整 UI 资源或提醒逻辑，提前定位相关文件。
3. 规划测试路径（GUI 场景至少包含新增/编辑/提醒/主题切换）。

### 提交前
1. 确认 `todos.json` 结构未被意外覆盖（如需示例数据请另行提供脚本）。
2. 若调整了常量或资源，手动运行应用至少一次确认 UI 正常。
3. 执行 `python -m compileall todo_app` 进行语法检查（或更高层级测试），并在提交说明中记录。
4. 检查文档与注释是否同步更新，尤其是锚点与 README。

## 最近约定变更
- 2025-11-04：首版锚点，确立数据字段、主题管理与工作流检查表。后续改动请在此按时间倒序补充。
