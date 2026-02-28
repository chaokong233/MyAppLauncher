# MyAppLauncher

> 一个轻量级的 Windows GUI 工具，用于分组管理并一键启动您常用的应用程序。

![MyAppLauncher 界面截图](https://github.com/user-attachments/assets/d35f5138-ea6c-4a20-969b-1267d817dede)

## 功能特性

| 功能 | 说明 |
|------|------|
| **拖放注册** | 将 `.exe`、`.lnk`、`.bat`、`.cmd`、`.ps1` 文件拖入注册区，自动添加到当前分组 |
| **分组管理** | 创建、重命名、删除分组；同一应用可出现在多个组（每组唯一） |
| **图标展示** | 自动读取并显示应用程序的原生图标 |
| **拖动排序** | 在列表中拖拽条目即可调整启动顺序 |
| **启用 / 禁用** | 右键菜单单独启用或禁用某个应用 |
| **重命名** | 右键菜单修改应用显示名称（全组同步） |
| **跨组添加** | 右键菜单可将应用快速添加到其他分组 |
| **双击启动** | 双击列表中的应用立即单独启动 |
| **启动当前组** | 按顺序启动当前分组内所有已启用应用（快捷键 **F5**） |
| **全部启动** | 启动所有分组内已启用应用，跨组自动去重 |
| **本地持久化** | 数据保存在程序同级目录 `apps_data.json`，无需写入系统盘，重启后自动加载 |

## 数据存储位置

数据文件保存在**可执行文件的同级目录**，不写入系统盘用户目录：

```
<程序目录>\apps_data.json
```

## 环境要求

- Python 3.10+
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
# 生成的 .exe 位于 dist\ 目录下，数据文件也保存在 dist\ 同级
```

## 数据格式

```json
{
  "apps": {
    "C:\\Programs\\notepad++.exe": { "path": "...", "name": "Notepad++" }
  },
  "groups": [
    {
      "id": "uuid",
      "name": "工作",
      "entries": [
        { "path": "C:\\Programs\\notepad++.exe", "enabled": true }
      ]
    }
  ],
  "active_group_id": "uuid"
}
```
