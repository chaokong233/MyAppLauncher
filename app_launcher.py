#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyAppLauncher - 分组管理并一键启动您常用的 Windows 应用程序。

用法:
    python app_launcher.py

依赖:
    PyQt5
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from PyQt5.QtCore import QFileInfo, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileIconProvider,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 数据文件保存在脚本 / 可执行文件的同级目录，不占用系统盘用户目录
DATA_FILE: Path = (
    Path(sys.executable if getattr(sys, "frozen", False) else __file__)
    .resolve()
    .parent
    / "apps_data.json"
)

# 支持的文件后缀（Windows 可执行文件及快捷方式）
SUPPORTED_EXTENSIONS: frozenset = frozenset(
    {".exe", ".lnk", ".bat", ".cmd", ".ps1"}
)

DEFAULT_GROUP_NAME = "默认"

# Lazy-initialized after QApplication is created; creating QFileIconProvider
# before QApplication leaves the Windows Shell COM binding uninitialized,
# causing icon() to silently return null icons for the entire session.
_icon_provider: "QFileIconProvider | None" = None


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
#
# 文件格式：
# {
#   "apps": {
#       "<path>": {"path": "...", "name": "显示名称"}
#   },
#   "groups": [
#       {
#           "id": "uuid",
#           "name": "组名",
#           "entries": [{"path": "...", "enabled": true}, ...]
#       }
#   ],
#   "active_group_id": "uuid"
# }


def _new_group(name: str) -> dict:
    return {"id": str(uuid.uuid4()), "name": name, "entries": []}


def load_data() -> dict:
    """从磁盘加载数据；文件不存在或格式错误时返回默认初始数据。"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "groups" in data:
                # 向后兼容：确保 apps 字段为 dict
                if not isinstance(data.get("apps"), dict):
                    data["apps"] = {}
                return data
        except Exception:
            pass
    g = _new_group(DEFAULT_GROUP_NAME)
    return {"apps": {}, "groups": [g], "active_group_id": g["id"]}


def save_data(data: dict) -> None:
    """将数据持久化到磁盘。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def get_file_icon(path: str):
    """利用 Qt 的文件图标提供器获取文件的原生图标。

    延迟初始化 _icon_provider，确保其在 QApplication 创建之后才被实例化；
    否则 Windows Shell COM 绑定未就绪，icon() 会静默返回空图标。
    """
    global _icon_provider
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    return _icon_provider.icon(QFileInfo(path))


def launch_path(path: str) -> str | None:
    """启动指定文件。成功返回 None，失败返回错误字符串。"""
    if not Path(path).exists():
        return "文件不存在"
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
        return None
    except Exception as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# 拖放区控件
# ---------------------------------------------------------------------------


class DropZone(QLabel):
    """接受文件拖放的标签区域；拖入有效文件后发出 filesDropped 信号。"""

    filesDropped = pyqtSignal(list)

    _STYLE_NORMAL = """
        QLabel {
            border: 2px dashed #9E9E9E; border-radius: 8px;
            background: #FAFAFA; color: #757575; font-size: 12px;
        }
    """
    _STYLE_HOVER = """
        QLabel {
            border: 2px dashed #1976D2; border-radius: 8px;
            background: #E3F2FD; color: #1565C0; font-size: 12px;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setText(
            "📂  将 .exe / .lnk / .bat / .cmd / .ps1 文件拖放到此处，注册到当前分组"
        )
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(62)
        self.setStyleSheet(self._STYLE_NORMAL)

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
# 分组应用列表控件
# ---------------------------------------------------------------------------


class GroupAppList(QListWidget):
    """单个分组的应用列表，支持内部拖动排序。"""

    orderChanged = pyqtSignal()

    _EMPTY_HINT = (
        "📂  将应用文件拖放到上方注册区\n"
        "或点击上方「添加」按钮从已注册应用中选取"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(32, 32))
        self.setSpacing(2)
        self.model().rowsMoved.connect(self.orderChanged)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            try:
                painter.setPen(QColor("#BDBDBD"))
                painter.setFont(QFont("", 11))
                painter.drawText(
                    self.viewport().rect(),
                    Qt.AlignCenter | Qt.TextWordWrap,
                    self._EMPTY_HINT,
                )
            finally:
                painter.end()

    def populate(self, entries: list, apps_registry: dict) -> None:
        """根据 entries 与全局注册表重新渲染列表。"""
        self.clear()
        for entry in entries:
            path = entry.get("path", "")
            name = apps_registry.get(path, {}).get("name") or Path(path).stem
            enabled = entry.get("enabled", True)

            item = QListWidgetItem()
            item.setText(name if enabled else f"[禁用]  {name}")
            item.setData(Qt.UserRole, {"path": path, "enabled": enabled})
            item.setToolTip(path)

            if Path(path).exists():
                item.setIcon(get_file_icon(path))

            if not enabled:
                item.setForeground(QColor("#BDBDBD"))

            self.addItem(item)

    def current_entries(self) -> list:
        """返回列表当前顺序的 entry 列表（保留 enabled 状态）。"""
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyAppLauncher")
        self.setMinimumSize(600, 640)
        self.data = load_data()
        self._build_ui()
        self._restore_active_group()
        # 快捷键：F5 启动当前组
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        QShortcut(QKeySequence("F5"), self, self._launch_current_group)

    # ================================================================== UI ==

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("🚀  MyAppLauncher")
        title.setFont(QFont("", 16, QFont.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        root.addLayout(title_row)

        # 拖放区
        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self._on_files_dropped)
        root.addWidget(self.drop_zone)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#555; font-size:12px;")
        root.addWidget(self.status_label)

        # ── 分组管理工具栏 ──────────────────────────────────────────────────
        group_bar_label = QLabel("📁  分组：")
        group_bar_label.setFont(QFont("", 10, QFont.Bold))

        self.new_group_btn = QPushButton("＋ 新建分组")
        self.new_group_btn.setToolTip("新建一个应用分组")
        self.new_group_btn.setFixedHeight(28)
        self.new_group_btn.setStyleSheet(
            "QPushButton{border:1px solid #90CAF9;border-radius:4px;"
            "background:#E3F2FD;color:#1565C0;padding:0 10px;}"
            "QPushButton:hover{background:#BBDEFB;}"
        )
        self.new_group_btn.clicked.connect(self._add_group)

        self.rename_group_btn = QPushButton("✏ 重命名")
        self.rename_group_btn.setToolTip("重命名当前选中的分组")
        self.rename_group_btn.setFixedHeight(28)
        self.rename_group_btn.setStyleSheet(
            "QPushButton{border:1px solid #C8E6C9;border-radius:4px;"
            "background:#F1F8E9;color:#2E7D32;padding:0 10px;}"
            "QPushButton:hover{background:#DCEDC8;}"
        )
        self.rename_group_btn.clicked.connect(
            lambda: self._rename_group(self.tab_widget.currentIndex())
        )

        self.del_group_btn = QPushButton("🗑 删除组")
        self.del_group_btn.setToolTip("删除当前选中的分组（应用不会被删除）")
        self.del_group_btn.setFixedHeight(28)
        self.del_group_btn.setStyleSheet(
            "QPushButton{border:1px solid #FFCDD2;border-radius:4px;"
            "background:#FFEBEE;color:#C62828;padding:0 10px;}"
            "QPushButton:hover{background:#FFCDD2;}"
            "QPushButton:disabled{background:#F5F5F5;color:#BDBDBD;border-color:#E0E0E0;}"
        )
        self.del_group_btn.clicked.connect(
            lambda: self._delete_group(self.tab_widget.currentIndex())
        )

        group_toolbar = QHBoxLayout()
        group_toolbar.setSpacing(6)
        group_toolbar.addWidget(group_bar_label)
        group_toolbar.addWidget(self.new_group_btn)
        group_toolbar.addWidget(self.rename_group_btn)
        group_toolbar.addWidget(self.del_group_btn)
        group_toolbar.addStretch()
        root.addLayout(group_toolbar)

        # 提示行
        hint = QLabel(
            "💡  点击下方标签切换分组 · 右键标签也可重命名或删除"
        )
        hint.setStyleSheet("color:#9E9E9E; font-size:11px;")
        root.addWidget(hint)

        # ── 分组标签页 ──────────────────────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)
        tab_bar: QTabBar = self.tab_widget.tabBar()
        tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._tab_context_menu)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tab_widget)

        # 底部按钮行
        btn_row = QHBoxLayout()

        self.launch_group_btn = QPushButton("▶  启动当前组  [F5]")
        self.launch_group_btn.setMinimumHeight(40)
        self.launch_group_btn.setFont(QFont("", 11))
        self.launch_group_btn.setStyleSheet(
            """
            QPushButton {
                background:#1976D2; color:white;
                border-radius:6px; padding:4px 20px;
            }
            QPushButton:hover   { background:#1565C0; }
            QPushButton:pressed { background:#0D47A1; }
            QPushButton:disabled { background:#BDBDBD; }
            """
        )
        self.launch_group_btn.clicked.connect(self._launch_current_group)

        self.launch_all_btn = QPushButton("⏩ 全部启动")
        self.launch_all_btn.setMinimumHeight(34)
        self.launch_all_btn.setFont(QFont("", 9))
        self.launch_all_btn.setToolTip("去重后启动所有分组的已启用应用")
        self.launch_all_btn.setStyleSheet(
            """
            QPushButton {
                background:#37474F; color:white;
                border-radius:6px; padding:4px 14px;
            }
            QPushButton:hover   { background:#263238; }
            QPushButton:pressed { background:#1C2830; }
            QPushButton:disabled { background:#BDBDBD; }
            """
        )
        self.launch_all_btn.clicked.connect(self._launch_all_groups)

        btn_row.addWidget(self.launch_group_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.launch_all_btn)
        root.addLayout(btn_row)

        # 构建分组标签页
        self._rebuild_tabs()

    def _rebuild_tabs(self):
        """根据 self.data 重建所有分组标签页。"""
        self.tab_widget.blockSignals(True)
        self.tab_widget.clear()
        for group in self.data["groups"]:
            self._create_tab_for_group(group)
        self.tab_widget.blockSignals(False)

    def _create_tab_for_group(self, group: dict) -> GroupAppList:
        # Each tab is a container widget: [add-from-registry button] + [list]
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 4, 0, 0)
        vbox.setSpacing(4)

        # "从已注册应用添加" button row
        add_row = QHBoxLayout()
        add_btn = QPushButton("＋  从已注册应用中添加到本组")
        add_btn.setFixedHeight(28)
        add_btn.setToolTip(
            "从全局已注册应用中勾选要添加到本组的应用\n"
            "（也可直接将文件拖放到上方注册区）"
        )
        add_btn.setStyleSheet(
            "QPushButton{border:1px solid #B0BEC5;border-radius:4px;"
            "background:#ECEFF1;color:#37474F;padding:0 10px;}"
            "QPushButton:hover{background:#CFD8DC;}"
        )
        add_btn.clicked.connect(
            lambda checked=False, gid=group["id"]: self._open_add_dialog(gid)
        )
        add_row.addWidget(add_btn)
        add_row.addStretch()
        vbox.addLayout(add_row)

        lw = GroupAppList()
        lw.setProperty("group_id", group["id"])
        lw.populate(group["entries"], self.data["apps"])
        lw.orderChanged.connect(
            lambda gid=group["id"]: self._on_order_changed(gid)
        )
        lw.setContextMenuPolicy(Qt.CustomContextMenu)
        lw.customContextMenuRequested.connect(
            lambda pos, _lw=lw: self._app_context_menu(pos, _lw)
        )
        lw.itemDoubleClicked.connect(
            lambda item: self._launch_single(item.data(Qt.UserRole)["path"])
        )
        vbox.addWidget(lw)

        self.tab_widget.addTab(container, group["name"])
        return lw

    def _get_list_at(self, tab_idx: int) -> GroupAppList | None:
        """Return the GroupAppList widget at the given tab index."""
        w = self.tab_widget.widget(tab_idx)
        if isinstance(w, GroupAppList):
            return w
        if isinstance(w, QWidget):
            children = w.findChildren(GroupAppList)
            return children[0] if children else None
        return None

    def _restore_active_group(self):
        active_id = self.data.get("active_group_id", "")
        for i, g in enumerate(self.data["groups"]):
            if g["id"] == active_id:
                self.tab_widget.setCurrentIndex(i)
                break
        self._update_status()

    # ======================================================== HELPERS ==

    def _current_group(self) -> dict | None:
        idx = self.tab_widget.currentIndex()
        if 0 <= idx < len(self.data["groups"]):
            return self.data["groups"][idx]
        return None

    def _current_list(self) -> GroupAppList | None:
        return self._get_list_at(self.tab_widget.currentIndex())

    def _update_status(self):
        group = self._current_group()
        only_one = len(self.data["groups"]) <= 1
        self.del_group_btn.setEnabled(not only_one)
        self.del_group_btn.setToolTip(
            "删除当前分组（应用不会被删除）"
            if not only_one
            else "至少保留一个分组，无法删除"
        )
        if not group:
            self.status_label.setText("")
            self.launch_group_btn.setEnabled(False)
            self.launch_all_btn.setEnabled(False)
            return

        total = len(group["entries"])
        enabled = sum(1 for e in group["entries"] if e.get("enabled", True))
        self.status_label.setText(
            f'分组 "{group["name"]}"：共 {total} 个应用，{enabled} 个已启用'
        )
        self.launch_group_btn.setEnabled(enabled > 0)

        any_enabled = any(
            any(e.get("enabled", True) for e in g["entries"])
            for g in self.data["groups"]
        )
        self.launch_all_btn.setEnabled(any_enabled)

    # ======================================================== GROUPS ==

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "请输入分组名称：")
        if not ok or not name.strip():
            return
        group = _new_group(name.strip())
        self.data["groups"].append(group)
        self.data["active_group_id"] = group["id"]
        save_data(self.data)
        self._create_tab_for_group(group)
        self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
        self._update_status()

    def _tab_context_menu(self, pos):
        tab_bar: QTabBar = self.tab_widget.tabBar()
        idx = tab_bar.tabAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)

        rename_act = QAction("重命名分组", self)
        rename_act.triggered.connect(lambda: self._rename_group(idx))
        menu.addAction(rename_act)

        if len(self.data["groups"]) > 1:
            del_act = QAction("删除此分组", self)
            del_act.triggered.connect(lambda: self._delete_group(idx))
            menu.addAction(del_act)

        menu.exec_(tab_bar.mapToGlobal(pos))

    def _rename_group(self, idx: int):
        current = self.data["groups"][idx]["name"]
        name, ok = QInputDialog.getText(
            self, "重命名分组", "请输入新的分组名称：", text=current
        )
        if ok and name.strip():
            self.data["groups"][idx]["name"] = name.strip()
            self.tab_widget.setTabText(idx, name.strip())
            save_data(self.data)
            self._update_status()

    def _delete_group(self, idx: int):
        name = self.data["groups"][idx]["name"]
        reply = QMessageBox.question(
            self,
            "确认删除",
            f'确定删除分组 "{name}"？\n（组内应用仍保留在全局注册表中）',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.data["groups"].pop(idx)
            if self.data["groups"]:
                self.data["active_group_id"] = self.data["groups"][0]["id"]
            save_data(self.data)
            self.tab_widget.removeTab(idx)
            self._update_status()

    def _on_tab_changed(self, idx: int):
        if 0 <= idx < len(self.data["groups"]):
            self.data["active_group_id"] = self.data["groups"][idx]["id"]
            save_data(self.data)
        self._update_status()

    # ======================================================== DROP ==

    def _on_files_dropped(self, paths: list):
        group = self._current_group()
        if not group:
            return
        existing_in_group = {e["path"] for e in group["entries"]}
        added = 0
        for path in paths:
            # 注册到全局表
            if path not in self.data["apps"]:
                self.data["apps"][path] = {
                    "path": path,
                    "name": Path(path).stem,
                }
            # 添加到当前组（每组唯一）
            if path not in existing_in_group:
                group["entries"].append({"path": path, "enabled": True})
                existing_in_group.add(path)
                added += 1

        if added:
            save_data(self.data)
            lw = self._current_list()
            if lw is not None:
                lw.populate(group["entries"], self.data["apps"])
            self._update_status()
            self.status_label.setText(f"✅  已向当前组添加 {added} 个应用")
        else:
            self.status_label.setText("ℹ️  所选文件均已在当前组中，未重复添加")

    # ======================================================== APP CONTEXT MENU ==

    def _app_context_menu(self, pos, lw: GroupAppList):
        item = lw.itemAt(pos)
        if not item:
            return
        idx = lw.row(item)
        entry = item.data(Qt.UserRole)
        path = entry["path"]
        enabled = entry.get("enabled", True)
        group = self._current_group()
        if not group:
            return

        menu = QMenu(self)

        launch_act = QAction("▶  立即启动", self)
        launch_act.triggered.connect(lambda: self._launch_single(path))
        menu.addAction(launch_act)

        menu.addSeparator()

        toggle_act = QAction("禁用" if enabled else "启用", self)
        toggle_act.triggered.connect(lambda: self._toggle_entry(group, idx, lw))
        menu.addAction(toggle_act)

        rename_act = QAction("重命名显示", self)
        rename_act.triggered.connect(lambda: self._rename_app(path))
        menu.addAction(rename_act)

        # 添加到其他分组
        other_groups = [g for g in self.data["groups"] if g["id"] != group["id"]]
        if other_groups:
            add_menu = QMenu("添加到其他分组", self)
            for g in other_groups:
                already = any(e["path"] == path for e in g["entries"])
                act = QAction(g["name"] + ("  ✓" if already else ""), self)
                if not already:
                    act.triggered.connect(
                        lambda checked=False, tg=g: self._add_to_group(path, tg)
                    )
                else:
                    act.setEnabled(False)
                add_menu.addAction(act)
            menu.addMenu(add_menu)

        menu.addSeparator()

        remove_act = QAction("从当前组移除", self)
        remove_act.triggered.connect(
            lambda: self._remove_from_group(group, idx, lw)
        )
        menu.addAction(remove_act)

        menu.exec_(lw.mapToGlobal(pos))

    def _toggle_entry(self, group: dict, idx: int, lw: GroupAppList):
        group["entries"][idx]["enabled"] = not group["entries"][idx].get(
            "enabled", True
        )
        save_data(self.data)
        lw.populate(group["entries"], self.data["apps"])
        self._update_status()

    def _rename_app(self, path: str):
        current = self.data["apps"].get(path, {}).get("name") or Path(path).stem
        name, ok = QInputDialog.getText(
            self, "重命名应用", "显示名称：", text=current
        )
        if ok and name.strip():
            if path not in self.data["apps"]:
                self.data["apps"][path] = {"path": path, "name": name.strip()}
            else:
                self.data["apps"][path]["name"] = name.strip()
            save_data(self.data)
            # 刷新所有标签页（改名影响所有组）
            for i, g in enumerate(self.data["groups"]):
                lw = self._get_list_at(i)
                if lw is not None:
                    lw.populate(g["entries"], self.data["apps"])

    def _add_to_group(self, path: str, target_group: dict):
        target_group["entries"].append({"path": path, "enabled": True})
        save_data(self.data)
        for i, g in enumerate(self.data["groups"]):
            if g["id"] == target_group["id"]:
                lw = self._get_list_at(i)
                if lw is not None:
                    lw.populate(g["entries"], self.data["apps"])
                break
        self.status_label.setText(f'✅  已添加到分组 "{target_group["name"]}"')
        self._update_status()

    def _remove_from_group(self, group: dict, idx: int, lw: GroupAppList):
        path = group["entries"][idx]["path"]
        name = self.data["apps"].get(path, {}).get("name") or Path(path).stem
        group["entries"].pop(idx)
        save_data(self.data)
        lw.populate(group["entries"], self.data["apps"])
        self._update_status()
        self.status_label.setText(f'已从当前组移除 "{name}"')

    def _open_add_dialog(self, group_id: str):
        """打开对话框，从全局注册表中勾选应用添加到指定分组。"""
        # Find the target group
        target_group = next(
            (g for g in self.data["groups"] if g["id"] == group_id), None
        )
        if target_group is None:
            return

        already = {e["path"] for e in target_group["entries"]}
        candidates = [
            info
            for path, info in self.data["apps"].items()
            if path not in already
        ]

        if not candidates:
            QMessageBox.information(
                self,
                "没有可添加的应用",
                "全局注册表中的应用已全部在本组中。\n\n"
                "请先将新的应用文件拖放到上方注册区以注册。",
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f'向分组 "{target_group["name"]}" 添加应用')
        dlg.setMinimumSize(380, 380)
        dlg_layout = QVBoxLayout(dlg)

        hint_lbl = QLabel("勾选要添加到本组的应用（可多选）：")
        hint_lbl.setStyleSheet("font-size:12px;")
        dlg_layout.addWidget(hint_lbl)

        lst = QListWidget()
        lst.setIconSize(QSize(24, 24))
        lst.setSpacing(2)
        for info in candidates:
            path = info.get("path", "")
            name = info.get("name") or Path(path).stem
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setCheckState(Qt.Unchecked)
            if Path(path).exists():
                item.setIcon(get_file_icon(path))
            lst.addItem(item)
        dlg_layout.addWidget(lst)

        # Select-all / deselect-all row
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("全选")
        sel_all_btn.setFixedHeight(24)

        def _select_all():
            for i in range(lst.count()):
                lst.item(i).setCheckState(Qt.Checked)

        def _deselect_all():
            for i in range(lst.count()):
                lst.item(i).setCheckState(Qt.Unchecked)

        sel_all_btn.clicked.connect(_select_all)
        desel_btn = QPushButton("取消全选")
        desel_btn.setFixedHeight(24)
        desel_btn.clicked.connect(_deselect_all)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(desel_btn)
        sel_row.addStretch()
        dlg_layout.addLayout(sel_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("添加所选")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        added = 0
        for i in range(lst.count()):
            item = lst.item(i)
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                target_group["entries"].append({"path": path, "enabled": True})
                added += 1

        if added:
            save_data(self.data)
            # Refresh the target group's list widget
            for idx, g in enumerate(self.data["groups"]):
                if g["id"] == group_id:
                    lw = self._get_list_at(idx)
                    if lw is not None:
                        lw.populate(g["entries"], self.data["apps"])
                    break
            self._update_status()
            self.status_label.setText(
                f'✅  已向分组 "{target_group["name"]}" 添加 {added} 个应用'
            )

    # ======================================================== ORDER ==

    def _on_order_changed(self, group_id: str):
        for i, g in enumerate(self.data["groups"]):
            if g["id"] == group_id:
                lw = self._get_list_at(i)
                if lw is not None:
                    g["entries"] = lw.current_entries()
                break
        save_data(self.data)

    # ======================================================== LAUNCH ==

    def _launch_single(self, path: str):
        err = launch_path(path)
        name = self.data["apps"].get(path, {}).get("name") or Path(path).stem
        if err:
            QMessageBox.warning(self, "启动失败", f'"{name}" 启动失败：{err}')
        else:
            self.status_label.setText(f'✅  已启动 "{name}"')

    def _do_launch(self, paths: list) -> tuple:
        """按序、去重地启动一批路径。返回 (launched_count, failed_msgs)。"""
        launched, failed, seen = 0, [], set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            err = launch_path(path)
            if err:
                name = self.data["apps"].get(path, {}).get("name") or path
                failed.append(f"{name}: {err}")
            else:
                launched += 1
        return launched, failed

    def _launch_current_group(self):
        group = self._current_group()
        if not group:
            return
        paths = [e["path"] for e in group["entries"] if e.get("enabled", True)]
        if not paths:
            QMessageBox.information(self, "提示", "当前组没有已启用的应用。")
            return
        launched, failed = self._do_launch(paths)
        if failed:
            QMessageBox.warning(
                self,
                "启动结果",
                f"已启动 {launched} 个，{len(failed)} 个失败：\n"
                + "\n".join(failed),
            )
        else:
            self.status_label.setText(f"✅  已启动当前组 {launched} 个应用")

    def _launch_all_groups(self):
        paths, seen = [], set()
        for g in self.data["groups"]:
            for e in g["entries"]:
                if e.get("enabled", True) and e["path"] not in seen:
                    paths.append(e["path"])
                    seen.add(e["path"])
        if not paths:
            QMessageBox.information(self, "提示", "所有组中没有已启用的应用。")
            return
        launched, failed = self._do_launch(paths)
        if failed:
            QMessageBox.warning(
                self,
                "启动结果",
                f"已启动 {launched} 个，{len(failed)} 个失败：\n"
                + "\n".join(failed),
            )
        else:
            self.status_label.setText(
                f"✅  已启动全部 {launched} 个应用（已跨组去重）"
            )


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
