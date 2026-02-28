# MyAppLauncher

> 一个轻量级的 Windows GUI 工具，用于注册和一键启动您常用的应用程序。

![MyAppLauncher 界面截图](https://github.com/user-attachments/assets/c62b1f03-d4e0-4e1f-9097-075ff7f97d4c)

## 功能特性

| 功能 | 说明 |
|------|------|
| **拖放注册** | 将 `.exe`、`.lnk`、`.bat`、`.cmd`、`.ps1` 文件拖入注册区即可添加 |
| **图标展示** | 自动读取并显示应用程序的原始图标 |
| **拖动排序** | 在列表中拖拽条目即可调整启动顺序 |
| **启用 / 禁用** | 右键菜单可单独启用或禁用某个应用 |
| **删除** | 右键菜单可将应用从列表中移除 |
| **一键启动** | 点击"启动所有已启用的应用"按钮，按顺序打开全部已启用应用 |
| **持久化** | 注册信息自动保存至 `%APPDATA%\MyAppLauncher\apps.json`，重启后自动加载 |

## 环境要求

- Python 3.9+
- Windows 10 / 11（也可在 Linux/macOS 上运行，图标及启动行为略有差异）

## 安装与运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动程序
python app_launcher.py
```

## 打包为独立可执行文件（可选）

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name MyAppLauncher app_launcher.py
# 生成的 .exe 位于 dist\ 目录下
```

## 数据存储位置

```
%APPDATA%\MyAppLauncher\apps.json
```

每条记录格式示例：

```json
[
  {
    "path": "C:\\Program Files\\Notepad++\\notepad++.exe",
    "name": "notepad++",
    "enabled": true
  }
]
```
