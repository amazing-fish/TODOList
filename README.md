# 桌面待办事项应用

本仓库包含一个基于 PySide6 的桌面待办事项管理工具。当前已对项目结构进行拆分，便于维护与后续扩展。

## 最新更新

- 💾 待办保存改为同目录临时文件写入并原子替换；覆盖有效主文件前会保留 `todos.json.bak`。主文件损坏时应用只读加载备份，不删除或覆盖损坏文件。
- 📝 任务正文会保留原始换行，每个用户输入行固定占一个视觉行并各自从末尾省略；短任务会按自然宽度释放空间，优先让可容纳的截止时间完整显示。悬停被省略或包含换行的正文区域，可通过不抢焦点的主题化浮层查看完整纯文本内容；详情宽高会限制在可用屏幕内，超长内容可在正文区域使用滚轮浏览。
- 🎛️ 320px 最小窗口下，筛选框按实际字体、内边距、边框和箭头测量，所有四字筛选项均完整显示；排序框仍可在空间不足时从末尾省略。
- ➕ 添加按钮改用主题化程序加号，圆形背景仅由按钮状态样式绘制；应用启动时注册内置 HarmonyOS Sans SC，使中英文控件共享同一字体来源并在资源失败时安全回退系统字体。
- 📐 任务较少或为空时，列表会在滚动条位置保留等宽 viewport gutter，使卡片左右外边距继续对称；滚动条出现后仍保持 8px 紧凑样式且不裁切卡片。
- 🪄 任务卡片在窄窗口下会从计时文本末尾省略并保留状态前缀，省略时可悬停查看完整内容；多卡片之间保留真实 8px 间距，深浅主题下的优先级与编辑/删除浮层也采用更克制、清晰的交互配色。
- ↕️ 待办列表使用 8px 紧凑滚动条；默认窄窗口下，滚动条与其右侧空白之和等于左侧留白，并随深浅主题切换颜色。
- 🔔 多个任务同时到期时会汇总到一个软件内提醒窗口；每条任务只在自己的行内提供“完成”“推迟”“忽略”，没有复选框或底部批量操作。“忽略”会清除该任务的截止时间并保留任务，不会把任务标记为完成或删除；应用不会创建 Windows 系统通知，最小化或关闭到托盘时也不会显示系统气泡。
- ⏱️ 新增任务的默认截止时间严格取当前时间一小时后，日期会自然跨到次日，并按界面可见分钟保存。
- 🕒 截止时间改为内联日期下拉与滚轮时间控件；常见任务可直接滚轮调时，跨日期时才展开日历，无需独立确认窗口。
- ⏳ 任务延后后只编辑内容或优先级会保留新的截止时间与提醒状态；只有实际修改时间或提醒选项才会重置调度。
- 🌗 应用会自动检测系统深/浅色主题并切换配色方案，支持运行时动态刷新窗口、对话框与卡片组件颜色。
- ⏰ 推迟提醒后会同步更新再次编辑时的默认截止时间；编辑时仅在截止时间或提醒偏移变化后自动重置旧提醒状态。
- 🎯 首次启动采用 320×640 px 的默认窗口尺寸，并在小屏设备上自动调整以保持可视区域。
- 📐 “暂无待办事项”占位信息在初次打开和窗口调整时都会保持居中，无需额外刷新。
- 🪟 托盘图标的快速添加操作会复用已有对话框窗口，防止重复弹出多个无法交互的窗口。

## 项目进展

- ✅ 待办事项列表采用卡片式展示，并提供完成状态、优先级、定时器等信息。
- ✅ 已完成任务显示填充勾选图标，未完成任务改为展示空心圆，同时保留编辑按钮，随时可修改内容。
- ✅ 添加按钮使用透明背景的程序化加号并保持居中，圆形背景统一由主题按钮样式控制。
- 🔄 后续计划：继续完善提醒与筛选策略，补充更多示例数据与使用说明，并持续打磨桌面端体验。

## 目录结构

```
.
├── main.py              # 程序入口脚本
├── assets/fonts/        # 内置字体及其许可证
├── todo_app/            # 应用源码包
│   ├── __init__.py
│   ├── app.py           # 启动封装
│   ├── constants.py     # 常量、颜色、路径配置
│   ├── dialogs.py       # 任务通知及编辑对话框
│   ├── fonts.py         # 应用字体注册与系统字体回退
│   ├── main_window.py   # 主窗口逻辑
│   ├── paths.py         # 基础路径与数据文件位置
│   ├── scheduling.py    # 提醒、推迟与编辑调度规则
│   ├── storage.py       # 数据加载与保存
│   ├── utils.py         # 工具函数（图标、声音等）
│   └── widgets.py       # 自定义任务卡片组件
├── todos.json           # 待办数据文件（程序运行时自动生成）
└── todos.json.bak       # 上一次有效主文件的单份备份（首次写入后尚不存在）
```

## 快速开始

1. 安装依赖：
   ```bash
   python -m pip install -r requirements.txt
   ```
2. 运行应用：
   ```bash
   python main.py
   ```

应用会默认在根目录创建/读取 `todos.json`，并支持系统托盘、提醒、推迟等功能。界面配色会根据当前系统主题在浅色与深色方案之间自动切换，确保可读性。

## 本地数据安全

- 保存时先在 `todos.json` 同目录写入临时文件，执行 `flush` 与 `os.fsync`，关闭后通过 `os.replace` 原子替换主文件；写入失败会清理临时文件并保留原主文件。
- 主文件已经存在且是有效 JSON 列表时，替换前会将其原始内容原子更新到单份备份 `todos.json.bak`。首次写入不会创建空备份。
- 主文件存在但 JSON 损坏或顶层不是列表时，应用只读尝试加载备份；备份也不可用则返回空列表。恢复不会删除、改名或覆盖损坏主文件。
- 为保留人工抢救价值，只要损坏主文件仍在原位置，后续保存也会拒绝覆盖并通过日志报告。请先复制并人工检查损坏文件，再将其移走或修复后重新保存。

## 第三方字体

本软件使用并随程序捆绑 **HarmonyOS Sans SC Regular** 字体。字体版权归 Huawei Device Co., Ltd. 所有，原始字体包来自[华为开发者联盟 HarmonyOS 设计资源](https://developer.huawei.com/consumer/cn/design/resource-V1/)，许可协议完整保存在 `assets/fonts/LICENSE_HarmonyOS_Sans.txt`。字体文件保持未修改，不作为独立字体产品分发；若资源缺失或 Qt 注册失败，应用会回退到操作系统通用 UI 字体。

## 打包与发布

- `requirements.txt` 以精确版本提供应用运行依赖；需要本地打包时执行 `python -m pip install -r requirements-dev.txt`，该文件会同时安装运行依赖与锁定版本的 PyInstaller。
- GitHub Actions 工作流 `.github/workflows/tests.yml` 会在所有 pull request 以及推送到 `main` 时，使用 Python 3.11 和 Qt offscreen 环境依次执行 `python -m compileall todo_app` 与 `python -m unittest discover -s tests -v`。
- GitHub Actions 工作流 `.github/workflows/build-exe.yml` 会在手动触发、推送到 `main` 分支或推送 `v*` 标签时，使用 PyInstaller 打包 Windows 单文件可执行程序；所有构建都会上传名称含来源与短提交 SHA、保留 7 天的临时 Actions Artifact。
- `--add-data "assets;assets"` 会把图标与 `assets/fonts` 中的 HarmonyOS Sans SC 字体/许可证一并加入单文件构建，运行时由统一的 `resource_path` 解析开发环境与 PyInstaller `_MEIPASS` 路径。
- 推送到 `main` 时会读取 `todo_app/constants.py` 中的 `APP_VERSION`，将 `pre` 与版本号组合成预发布标签（例如 `1.7.14` 对应 `pre1.7.14`），并创建或更新不会成为 Latest Release 的 Pre-release，其中包含 `TODOList.exe`。同一版本号下，该 `pre<版本号>` 标签可随新的 `main` 提交更新。
- 手动运行仅上传临时 Artifact，不创建或更新任何 Release，也不修改标签；即使手动选择标签 ref，仍保持临时构建语义。
- 推送 `v*` 标签才会创建或更新对应的正式 Release，并上传 `TODOList.exe` 作为长期正式下载入口。所有 `v*` 版本标签均由发布者显式推送且保持不可变；同一标签的工作流重跑允许覆盖该标签的同名资产以恢复失败发布。
- 若需本地验证，可执行：
  ```bash
  pyinstaller main.py --name TODOList --noconsole --clean --onefile --add-data "assets;assets" --hidden-import PySide6.QtSvg --hidden-import PySide6.QtMultimedia
  ```
  请将 `"assets;assets"` 中的分隔符替换为当前系统要求（Windows 使用 `;`，macOS/Linux 使用 `:`）。
- 打包版本会将 `todos.json` 存放在用户数据目录（Windows 为 `%APPDATA%\TODOList`，其他平台为 `~/.todolist/`），以避免写入只读的程序目录。

![Alt](https://repobeats.axiom.co/api/embed/c7140913b7a7578ef239a8c8e869a2e700537ba1.svg "Repobeats analytics image")
