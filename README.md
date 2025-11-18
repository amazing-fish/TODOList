# 桌面待办事项应用

本仓库包含一个基于 PySide6 的桌面待办事项管理工具。当前已对项目结构进行拆分，便于维护与后续扩展。

## 最新更新

- 🌗 应用会自动检测系统深/浅色主题并切换配色方案，支持运行时动态刷新窗口、对话框与卡片组件颜色。
- 🎯 首次启动采用 320×640 px 的默认窗口尺寸，并在小屏设备上自动调整以保持可视区域。
- 📐 “暂无待办事项”占位信息在初次打开和窗口调整时都会保持居中，无需额外刷新。
- 🪟 托盘图标的快速添加操作会复用已有对话框窗口，防止重复弹出多个无法交互的窗口。

## 项目进展

- ✅ 待办事项列表采用卡片式展示，并提供完成状态、优先级、定时器等信息。
- ✅ 已完成任务显示填充勾选图标，未完成任务改为展示空心圆，同时保留编辑按钮，随时可修改内容。
- ✅ 添加按钮改用独立图标并保持居中，便于快速创建任务。
- 🔄 后续计划：继续完善提醒与筛选策略，补充更多示例数据与使用说明，并持续打磨桌面端体验。

## 目录结构

```
.
├── main.py              # 程序入口脚本
├── todo_app/            # 应用源码包
│   ├── __init__.py
│   ├── app.py           # 启动封装
│   ├── constants.py     # 常量、颜色、路径配置
│   ├── dialogs.py       # 任务通知及编辑对话框
│   ├── main_window.py   # 主窗口逻辑
│   ├── paths.py         # 基础路径与数据文件位置
│   ├── storage.py       # 数据加载与保存
│   ├── utils.py         # 工具函数（图标、声音等）
│   └── widgets.py       # 自定义任务卡片组件
└── todos.json           # 待办数据文件（程序运行时自动生成）
```

## 快速开始

1. 安装依赖：
   ```bash
   pip install PySide6
   ```
2. 运行应用：
   ```bash
   python main.py
   ```

应用会默认在根目录创建/读取 `todos.json`，并支持系统托盘、提醒、推迟等功能。界面配色会根据当前系统主题在浅色与深色方案之间自动切换，确保可读性。

## 打包与发布

- 仓库提供的 GitHub Actions 工作流 `.github/workflows/build-exe.yml` 会在手动触发或推送 `v*` 标签时使用 PyInstaller 打包 Windows 平台的单文件可执行程序，构建结果会作为工作流附件保存；当以标签触发时还会自动更新 GitHub Release。
- 若需本地验证，可执行：
  ```bash
  pyinstaller main.py --name TODOList --noconsole --clean -onefile --add-data "assets;assets" --hidden-import PySide6.QtSvg --hidden-import PySide6.QtMultimedia
  ```
  请将 `"assets;assets"` 中的分隔符替换为当前系统要求（Windows 使用 `;`，macOS/Linux 使用 `:`）。
- 打包版本会将 `todos.json` 存放在用户数据目录（Windows 为 `%APPDATA%\TODOList`，其他平台为 `~/.todolist/`），以避免写入只读的程序目录。
