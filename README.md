# 桌面待办事项

一个基于 PySide6 的轻量桌面待办工具，提供任务管理、截止时间、提醒与推迟、系统托盘、深浅色主题和本地数据保护。

当前版本为 **v2.1.1**，版本号的唯一来源是 `todo_app/constants.py` 中的 `APP_VERSION`。

## 功能概览

- 创建、编辑、删除和完成待办，支持高/中/低优先级、筛选与排序。
- 为任务设置截止时间和提前提醒；到期任务集中显示在一个软件内提醒窗口，可逐项完成、推迟或忽略。
- “忽略”会清除任务的时间约束但保留任务和提醒偏好，不会删除任务或将其标记为完成。
- 系统托盘支持显示/隐藏窗口、快速添加和退出；最小化或关闭到托盘时不发送系统气泡。
- 自动跟随系统深浅色主题，使用内置 HarmonyOS Sans SC 字体并在资源不可用时安全回退。
- 适配 320px 最小窗口宽度；任务正文保留原始换行，省略或多行内容可通过悬停浮层完整查看。
- 待办数据使用原子替换和单份有效备份，损坏主文件不会被静默覆盖。

## v2.x 近期变化

- **v2.1.1**：拆分用户可见名称与稳定的 `QSettings` 命名空间，界面不再显示过期的 v1 标识，已有窗口几何和状态继续兼容。
- **v2.1.0**：到期通知收敛为逐项“完成”“推迟”“忽略”，明确忽略任务的时间约束语义。
- **v2.0.0**：将任务卡片和详情浮层的关键布局规则收敛为可独立测试的纯函数模型，保持既有界面行为。

完整的 1.x 演进记录见 [`docs/history-v1.md`](docs/history-v1.md)。

## 快速开始

项目使用 Python 3.11 进行持续集成验证。

### Windows PowerShell

```powershell
git clone https://github.com/amazing-fish/TODOList.git
Set-Location TODOList
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

### macOS / Linux

```bash
git clone https://github.com/amazing-fish/TODOList.git
cd TODOList
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

## 数据存储与安全

- 源码运行时，数据保存在仓库根目录的 `todos.json`；该运行时文件及其备份已被 Git 忽略。
- PyInstaller 打包版本在 Windows 使用 `%APPDATA%\TODOList\todos.json`，其他平台使用 `~/.todolist/todos.json`，避免向只读程序目录写入。
- 保存时先在同目录写入临时文件，执行 `flush` 与 `os.fsync` 后再通过 `os.replace` 原子替换主文件。
- 覆盖有效主文件前，原内容会原子更新到 `todos.json.bak`；首次保存不会制造空备份。
- 主文件损坏或顶层不是 JSON 列表时，应用只读尝试加载备份，不删除、改名或覆盖损坏文件。
- 只要损坏主文件仍在原位置，后续保存会拒绝覆盖。请先复制并人工检查，再移走或修复该文件。

## 项目结构

```text
.
├── .github/workflows/       # 自动化测试与 Windows 打包工作流
├── assets/
│   ├── fonts/               # 内置字体及许可证
│   └── icons/               # 应用与操作图标
├── docs/
│   ├── history-v1.md        # 1.x 历史归档，不作为当前规范
│   └── plans/               # 已实施功能的历史设计与实施计划
├── tests/                   # unittest 自动化测试
├── todo_app/
│   ├── app.py               # QApplication 初始化与窗口启动
│   ├── constants.py         # 应用身份、版本、资源与主题常量
│   ├── dialogs.py           # 任务编辑与软件内提醒窗口
│   ├── fonts.py             # 字体注册与回退
│   ├── layout.py            # 卡片与详情浮层的纯函数布局模型
│   ├── main_window.py       # 主窗口、列表、提醒与托盘流程
│   ├── paths.py             # 开发/打包环境路径解析
│   ├── scheduling.py        # 编辑、提醒与推迟规则
│   ├── storage.py           # 数据迁移、原子保存与备份恢复
│   ├── theme.py             # 系统主题检测与调色板管理
│   ├── utils.py             # 图标、声音等通用工具
│   └── widgets.py           # 待办卡片与详情浮层组件
├── AGENTS.md                # 仓库协作与验证要求
├── anchor.md                # 当前有效的技术与行为约束
├── main.py                  # 程序入口
├── requirements.txt         # 精确锁定的运行依赖
└── requirements-dev.txt     # 运行依赖与 PyInstaller
```

## 开发与测试

安装运行依赖后，在仓库根目录执行：

```powershell
python -m compileall todo_app
python -m unittest discover -s tests -v
git diff --check
```

GitHub Actions 的 `tests.yml` 会在所有 pull request 和推送到 `main` 时，使用 Python 3.11 与 Qt offscreen 环境执行源码编译检查和完整测试。涉及 GUI 的改动还应按 [`AGENTS.md`](AGENTS.md) 完成对应手工验证。

## 打包与发布

本地 Windows 打包：

```powershell
python -m pip install -r requirements-dev.txt
pyinstaller main.py `
  --name TODOList `
  --noconsole `
  --clean `
  --onefile `
  --add-data "assets;assets" `
  --hidden-import PySide6.QtSvg `
  --hidden-import PySide6.QtMultimedia
```

macOS/Linux 使用 PyInstaller 时，需要将 `--add-data` 的分隔符从 `;` 改为 `:`。

`.github/workflows/build-exe.yml` 的当前规则：

- 手动触发、推送到 `main` 或推送 `v*` 标签时，在 Windows Runner 生成单文件 `TODOList.exe`。
- 所有构建都会上传名称包含来源和短提交 SHA、保留 7 天的 Actions Artifact。
- `main` 的最新构建会按 `APP_VERSION` 更新可移动的预发布标签，例如 `2.1.1` 对应 `pre2.1.1`，并更新不作为 Latest 的 Pre-release。
- 手动构建只产生临时 Artifact，不修改标签或 Release。
- 只有发布者显式推送、保持不可变的 `v*` 标签才创建或更新正式 Release；同一标签的工作流重跑可以覆盖同名资产以恢复失败发布。

图标、字体和字体许可证通过 `--add-data "assets;assets"` 一并打包，运行时由 `resource_path` 统一解析源码目录与 PyInstaller `_MEIPASS` 路径。

## 应用身份与版本兼容

- `APP_NAME` 仅表示用户可见名称“桌面待办事项”，`APP_VERSION` 独立表示当前版本。
- `QSettings` 继续使用历史命名空间 `MyProductiveApp / 桌面待办事项 v1`。其中的 v1 只是兼容键，不会显示在当前界面；修改该键必须提供明确的数据迁移方案。
- 项目的版本递增规则、当前技术约束和交互约定以 [`anchor.md`](anchor.md) 为准。
- 1.x 的功能与工程演进已归档到 [`docs/history-v1.md`](docs/history-v1.md)，历史设计材料保留在 [`docs/plans/`](docs/plans/)。

## 第三方资源

本软件随程序捆绑 **HarmonyOS Sans SC Regular** 字体。字体版权归 Huawei Device Co., Ltd. 所有，原始字体包来自[华为开发者联盟 HarmonyOS 设计资源](https://developer.huawei.com/consumer/cn/design/resource-V1/)，许可协议保存在 `assets/fonts/LICENSE_HarmonyOS_Sans.txt`。字体文件保持未修改，不作为独立字体产品分发。

![Repobeats analytics](https://repobeats.axiom.co/api/embed/c7140913b7a7578ef239a8c8e869a2e700537ba1.svg "Repobeats analytics image")
