#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyAppLauncher - 注册并一键启动您常用的 Windows 应用程序。

用法:
    python app_launcher.py

依赖:
    PyQt5
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QFileInfo, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 在 Windows 上持久化到 %APPDATA%\MyAppLauncher\apps.json
if sys.platform == "win32":
    _base = Path(os.environ.get("APPDATA", Path.home()))
else:
    _base = Path.home() / ".config"

DATA_DIR: Path = _base / "MyAppLauncher"
DATA_FILE: Path = DATA_DIR / "apps.json"

# 支持的文件后缀（Windows 可执行文件及快捷方式）
SUPPORTED_EXTENSIONS: frozenset = frozenset(
    {".exe", ".lnk", ".bat", ".cmd", ".ps1"}
)

_icon_provider = QFileIconProvider()


# ---------------------------------------------------------------------------
# 持久化辅助函数
# ---------------------------------------------------------------------------


def load_apps() -> list:
    """从磁盘加载已注册的应用列表；文件不存在时返回空列表。"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_apps(apps: list) -> None:
    """将应用列表持久化到磁盘。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(apps, fh, ensure_ascii=False, indent=2)


def get_file_icon(path: str):
    """利用 Qt 的文件图标提供器获取指定文件的图标。"""
    return _icon_provider.icon(QFileInfo(path))


# ---------------------------------------------------------------------------
# 注册拖放区控件
# ---------------------------------------------------------------------------


class DropZone(QLabel):
    """接受文件拖放的区域；拖入有效文件后发出 filesDropped 信号。"""

    filesDropped = pyqtSignal(list)

    _STYLE_NORMAL = """
        QLabel {
            border: 2px dashed #9E9E9E;
            border-radius: 8px;
            background-color: #FAFAFA;
            color: #757575;
            font-size: 13px;
        }
    """
    _STYLE_HOVER = """
        QLabel {
            border: 2px dashed #1976D2;
            border-radius: 8px;
            background-color: #E3F2FD;
            color: #1565C0;
            font-size: 13px;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setText("📂   将 .exe / .lnk / .bat / .cmd / .ps1 文件拖放到此处以注册应用")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(90)
        self.setStyleSheet(self._STYLE_NORMAL)

    # ---- drag-and-drop 事件 ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._STYLE_HOVER)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: ARG002
        self.setStyleSheet(self._STYLE_NORMAL)

    def dropEvent(self, event):
        self.setStyleSheet(self._STYLE_NORMAL)
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyAppLauncher")
        self.setMinimumSize(500, 560)
        self.apps: list = load_apps()
        self._build_ui()
        self._refresh_list()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 标题
        title = QLabel("🚀  MyAppLauncher")
        title.setFont(QFont("", 17, QFont.Bold))
        root.addWidget(title)

        # 拖放注册区
        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self._on_files_dropped)
        root.addWidget(self.drop_zone)

        # 状态提示行
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #555; font-size: 12px;")
        root.addWidget(self.status_label)

        # 应用列表标题
        list_title = QLabel("已注册的应用（可拖动排序，右键可操作）：")
        list_title.setFont(QFont("", 10))
        root.addWidget(list_title)

        # 应用列表
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setIconSize(QSize(32, 32))
        self.list_widget.setSpacing(2)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        # 拖动排序结束后同步内部数据
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        root.addWidget(self.list_widget)

        # 底部按钮
        btn_row = QHBoxLayout()
        self.launch_btn = QPushButton("▶   启动所有已启用的应用")
        self.launch_btn.setMinimumHeight(40)
        self.launch_btn.setFont(QFont("", 11))
        self.launch_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 6px;
                padding: 4px 20px;
            }
            QPushButton:hover  { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
            QPushButton:disabled { background-color: #BDBDBD; }
            """
        )
        self.launch_btn.clicked.connect(self._launch_all)
        btn_row.addWidget(self.launch_btn)
        root.addLayout(btn_row)

    # ---------------------------------------------------------- 列表刷新 --

    def _refresh_list(self):
        """重新渲染整个应用列表。"""
        self.list_widget.clear()

        for app in self.apps:
            item = QListWidgetItem()
            name = app.get("name") or Path(app["path"]).stem
            enabled = app.get("enabled", True)

            display_name = name if enabled else f"[已禁用]  {name}"
            item.setText(display_name)
            item.setData(Qt.UserRole, app)

            path = app.get("path", "")
            if Path(path).exists():
                item.setIcon(get_file_icon(path))

            if not enabled:
                item.setForeground(QColor("#BDBDBD"))

            self.list_widget.addItem(item)

        total = len(self.apps)
        enabled_count = sum(1 for a in self.apps if a.get("enabled", True))
        self.status_label.setText(
            f"已注册 {total} 个应用，其中 {enabled_count} 个已启用"
        )
        self.launch_btn.setEnabled(enabled_count > 0)

    # ----------------------------------------------- 拖放注册回调 --

    def _on_files_dropped(self, paths: list):
        existing = {a["path"] for a in self.apps}
        added = 0
        for path in paths:
            if path not in existing:
                self.apps.append(
                    {
                        "path": path,
                        "name": Path(path).stem,
                        "enabled": True,
                    }
                )
                existing.add(path)
                added += 1

        if added:
            save_apps(self.apps)
            self._refresh_list()
            self.status_label.setText(f"✅  成功注册 {added} 个新应用")
        else:
            self.status_label.setText("ℹ️  所选文件均已注册过，未添加新条目")

    # ----------------------------------------------- 拖动排序回调 --

    def _on_rows_moved(self, *_args):
        """列表内拖动排序后，将新顺序同步回 self.apps 并持久化。"""
        self.apps = [
            self.list_widget.item(i).data(Qt.UserRole)
            for i in range(self.list_widget.count())
        ]
        save_apps(self.apps)

    # ------------------------------------------------ 右键菜单 --

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return

        idx = self.list_widget.row(item)
        app = self.apps[idx]
        enabled = app.get("enabled", True)

        menu = QMenu(self)

        toggle_text = "禁用" if enabled else "启用"
        toggle_action = QAction(toggle_text, self)
        toggle_action.triggered.connect(lambda: self._toggle_app(idx))
        menu.addAction(toggle_action)

        menu.addSeparator()

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self._delete_app(idx))
        menu.addAction(delete_action)

        menu.exec_(self.list_widget.mapToGlobal(pos))

    # ----------------------------------------- 启用 / 禁用 --

    def _toggle_app(self, idx: int):
        self.apps[idx]["enabled"] = not self.apps[idx].get("enabled", True)
        save_apps(self.apps)
        self._refresh_list()

    # ----------------------------------------------- 删除 --

    def _delete_app(self, idx: int):
        name = self.apps[idx].get("name", self.apps[idx]["path"])
        reply = QMessageBox.question(
            self,
            "确认删除",
            f'确定要从列表中删除 "{name}" 吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.apps.pop(idx)
            save_apps(self.apps)
            self._refresh_list()

    # ----------------------------------------------- 一键启动 --

    def _launch_all(self):
        enabled_apps = [a for a in self.apps if a.get("enabled", True)]
        if not enabled_apps:
            QMessageBox.information(self, "提示", "当前没有已启用的应用。")
            return

        launched = 0
        failed = []

        for app in enabled_apps:
            path = app.get("path", "")
            if not Path(path).exists():
                failed.append(f'{app.get("name", path)}  （文件不存在）')
                continue
            try:
                if sys.platform == "win32":
                    os.startfile(path)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", path])
                launched += 1
            except Exception as exc:
                failed.append(f'{app.get("name", path)}: {exc}')

        if failed:
            msg = f"已启动 {launched} 个应用。\n\n以下应用启动失败：\n" + "\n".join(
                failed
            )
            QMessageBox.warning(self, "启动结果", msg)
        else:
            self.status_label.setText(f"✅  已成功启动 {launched} 个应用")


# ---------------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
