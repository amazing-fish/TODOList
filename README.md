# 桌面待办事项应用

本仓库包含一个基于 PySide6 的桌面待办事项管理工具。当前已对项目结构进行拆分，便于维护与后续扩展。

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

应用会默认在根目录创建/读取 `todos.json`，并支持系统托盘、提醒、推迟等功能。
