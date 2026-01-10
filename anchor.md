# 项目锚点（Anchor）

> 每轮改动的起点与终点。开始动手前先复盘本文件，收尾时确认约定依然成立，如有变化请在此同步。
> 违背锚点将直接影响模型产出的稳定性与交付质量。

## 项目速览
- **定位**：基于 PySide6 的桌面待办事项管理工具，强调现代化视觉、提醒/延迟机制与轻量本地存储。
- **入口**：`main.py` 调用 `todo_app.run()`，由 `ModernTodoAppWindow`（`todo_app/main_window.py`）驱动 UI 与业务流。
- **运行**：开发环境可执行 `python main.py`；GitHub Actions 工作流 `build-exe.yml` 负责生成 Windows 平台单文件可执行程序，并在推送 `v*` 标签时上传到 Release。
- **依赖要点**：PySide6 GUI 组件、`QSoundEffect` 播放提醒、`todos.json` 做本地数据缓存。

## 技术路径
- **启动链路**：`main.py` → `todo_app/app.py::run` → `todo_app/main_window.py::ModernTodoAppWindow`。
- **核心流转**：主窗口负责过滤排序、提醒计时器与托盘交互；数据读写统一通过 `todo_app/storage.py`；主题切换由 `todo_app/theme.py::ThemeManager` 统一管理。
- **技术路径稳定性**：
  - 不随意调整入口文件、主窗口驱动链路与核心职责分配；如必须变更，需同步更新本锚点与 README。
  - 涉及提醒/托盘/存储路径的改动必须在“最近约定变更”登记，并标注影响范围。

### 代码结构速查
- `todo_app/app.py`：应用初始化、消息过滤与窗口展示。
- `todo_app/main_window.py`：主窗口、过滤排序逻辑、系统托盘、提醒计时器、状态保存。
- `todo_app/dialogs.py`：任务编辑对话框与提醒弹窗，负责校验输入、配置提醒与打盹选项。
- `todo_app/widgets.py`：待办卡片视图与交互按钮，响应主题变化、完成状态切换、计时显示。
- `todo_app/storage.py`：JSON 数据的读写与迁移，保证旧数据补全字段。
- `todo_app/theme.py`：主题检测与切换，提供 `ThemeManager` 单例。
- `todo_app/utils.py`：图标加载、声音播放、文本截断等通用工具。
- `todo_app/constants.py`：项目常量、主题色板、资源路径。
- `todo_app/paths.py`：基础路径与 `todos.json` 存放位置。

## 版本控制约定
- 版本号统一遵循 `v主.次.修`（例如 `v1.2.3`）。
- **类型映射**：
  - `refactor` → 提升主版本号。
  - `feature` → 提升次版本号。
  - `bugfix` → 提升修订号。
- 仅文档与注释变更默认不触发版本号递增，除非影响发布说明或行为约定。
- 当前约定版本：`v1.7.4`。

## 数据约束
- 所有待办保存在项目根目录下的 `todos.json`，结构为列表，元素为字典；打包版运行时会改存至用户数据目录（Windows `%APPDATA%\TODOList`，其他平台 `~/.todolist/`）。
- 字段约定：
  - `id`（int）唯一标识；缺失或非法时由 `_migrate_and_validate_todo_item` 重新生成。
  - `text`（str）任务内容，UI 侧以富文本/纯文本显示，需兼容多行但在列表中会截断显示。
  - `createdAt`（ISO8601 str，UTC），缺失时写入当前时间。
  - `completed`（bool）、`priority`（"高"|"中"|"低"）、`dueDate`（ISO8601 str 或 `None`）。
  - `reminderOffset`（int 秒，-1 表示不提醒）、`snoozeUntil`、`lastNotifiedAt`（ISO8601 str 或 `None`）。
  - `notifiedForReminder`、`notifiedForDue`（bool）用于提醒状态去重。
- 修改字段或新增元数据时：同步更新 `storage.py` 的迁移逻辑、`TaskEditDialog` 的表单、`TodoItemWidget` 的展示，以及锚点此处的说明。

## 资源约束
- 所有 SVG/音频资源路径在 `constants.py` 中声明，新增资源需：①放入 `assets` 子目录；②在常量中登记；③如为图标，保证 SVG 可在浅/深色主题下辨识。
- 缺失资源时工具函数会打印警告，需在提交前确认是否属于预期。

## 交互与视觉关键点
- 主题：通过 `ThemeManager` 监听系统配色；新增控件需调用 `apply_palette` 或监听 `theme_changed`。
- 列表交互：
  - 过滤/排序选项在主窗口初始化时定义，新增选项需更新 `update_list_widget` 的分支与文案。
  - 列表项使用 `TodoItemWidget`，按钮图标依赖 `assets/icons`，缺失时 `utils.get_icon` 会自动降级并打印警告。
  - 已完成任务只通过勾选状态、线框及配色区分，编辑按钮始终可用，由主窗口逻辑负责根据任务 ID 处理编辑请求。
- 提醒流程：`master_timer` 每秒触发 `tick_update` 检查到期任务，提醒音通过 `play_sound_effect` 播放，可根据资源情况提供回退字符或系统提示音；提醒唤醒时优先调用原生接口恢复并前置主窗口，若平台不支持则临时添加 `WindowStaysOnTopHint` 保障可见，之后自动回退。
- 托盘行为：系统托盘菜单与最小化逻辑集中在 `main_window.py::_create_tray_icon`，调整时注意多平台兼容；点击窗口最小化按钮会直接隐藏到托盘，提醒触发时会自动还原窗口并置顶。

## 修改日志稳定性
- 任何影响技术路径、数据字段、资源约束、交互流程、版本号的变更必须登记到“最近约定变更”。
- 记录要求：时间倒序、单行摘要、包含变更类型（refactor/feature/bugfix）与版本号（若触发版本变更）。
- 若确认无变更，提交说明需写明“锚点已复盘，无需更新”。

## 最近约定变更
- 2026-01-11：bugfix，修复筛选/排序下拉框宽度计算导致文字截断与空白区问题，版本更新至 `v1.7.4`。
- 2026-01-10：bugfix，Windows 打包流程改用 Runner 临时目录缓存 pip，修复缓存路径不存在告警（不触发版本号）。
- 2026-01-09：refactor，GitHub Actions 打包流程增加 pip 缓存以提升构建速度（不触发版本号）。
- 2026-01-08：bugfix，调整新增任务按钮位置避免窄屏与排序选项重叠，版本更新至 `v1.7.3`。
- 2026-01-08：refactor，锚点流程拆分至协作约定，保持锚点聚焦技术路径与日志稳定性（不触发版本号）。
- 2025-11-07：发布 `v1.7.2` 标签，确认允许已完成任务继续编辑并准备触发打包工作流。
- 2025-11-06：新增版本控制约定，明确版本号递增策略，当前版本更新至 `v1.7.1`。
- 2025-11-04：首版锚点，确立数据字段、主题管理与工作流检查表。
