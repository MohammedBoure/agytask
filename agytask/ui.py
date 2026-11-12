"""
ui.py - Modern PySide6 desktop interface for Antigravity Task Runner.
"""

import os
import sys
import uuid
import shutil
import datetime
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .icons import get_icon, get_pixmap
from .interactive_worker import get_agy_brain_dir
from .models import (
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    ModelInfo,
    fetch_available_models,
    resolve_agy_model_and_effort,
)
from .parser import Task, clean_to_absolute_path, parse_tasks_file


APP_STYLESHEET = """
QMainWindow, QWidget#CentralRoot {
    background-color: #F8FAFC;
    color: #0F172A;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}

QFrame#CardPanel {
    background-color: #FFFFFF;
    border: 1px solid #DDE3EA;
    border-radius: 8px;
}

QFrame#CardPanel QLabel {
    border: none;
    background: transparent;
}

QLabel#PageTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0F172A;
}

QLabel#PageSubtitle {
    font-size: 12px;
    color: #64748B;
}

QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
}

QLabel#FieldLabel {
    font-size: 12px;
    font-weight: 600;
    color: #334155;
}

QLabel#StatusSummary {
    font-size: 12px;
    font-weight: 600;
    color: #0E7471;
}

QLabel#RuntimeBadge {
    background-color: #E6F4F1;
    color: #0E7471;
    border: 1px solid #B8E1DC;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

QLineEdit, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 0 10px;
    color: #0F172A;
    font-size: 13px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1.5px solid #0E7471;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    selection-background-color: #E6F4F1;
    selection-color: #0F172A;
    outline: 0;
}

QPushButton#PrimaryBtn {
    background-color: #0E7471;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 0 16px;
    font-weight: 700;
    font-size: 13px;
}

QPushButton#PrimaryBtn:hover {
    background-color: #0A5C59;
}

QPushButton#PrimaryBtn:pressed {
    background-color: #084846;
}

QPushButton#TealOutlineBtn {
    background-color: #FFFFFF;
    color: #0E7471;
    border: 1.5px solid #0E7471;
    border-radius: 6px;
    padding: 0 14px;
    font-weight: 600;
    font-size: 13px;
}

QPushButton#TealOutlineBtn:hover {
    background-color: #E6F4F1;
}

QPushButton#SecondaryBtn {
    background-color: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 0 12px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#SecondaryBtn:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}

QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    gridline-color: #F1F5F9;
    color: #0F172A;
    selection-background-color: #E6F4F1;
    selection-color: #0F172A;
    outline: 0;
}

QHeaderView::section {
    background-color: #F1F5F9;
    color: #334155;
    font-weight: 700;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid #DDE3EA;
    border-right: 1px solid #E2E8F0;
    padding: 0 10px;
}

QHeaderView::section:last {
    border-right: none;
}

QPlainTextEdit#ActivityLog {
    background-color: #0F172A;
    color: #E2E8F0;
    border: 1px solid #1E293B;
    border-radius: 6px;
    padding: 8px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
}
"""


class ModelLoaderThread(QThread):
    """Background worker that queries `agy models` without blocking the UI."""

    models_loaded = Signal(list, bool)

    def run(self) -> None:
        models, is_live = fetch_available_models(timeout=12.0)
        self.models_loaded.emit(models, is_live)


class AntigravityTaskRunnerUI(QMainWindow):
    """Main PySide6 window for Antigravity Task Runner."""

    def __init__(self) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LeftToRight)
        self.setWindowTitle("Antigravity Task Runner")
        self.resize(1020, 800)
        self.setMinimumSize(880, 680)
        self.setWindowIcon(get_icon("layers", size=24, color="#0E7471"))

        self.last_tasks_mtime: float = 0.0
        self.pending_tasks: List[Task] = []
        self.completed_task_ids: List[str] = []
        self.recent_sessions: List[str] = self._discover_recent_sessions()
        self._model_thread: Optional[ModelLoaderThread] = None

        self._build_ui()
        self._initialize_defaults()
        self._reload_tasks()
        self._refresh_models_async()

        self._log_message("Antigravity Task Runner ready. Auto-approve permissions and auto-continue are enabled.")

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._auto_poll_tasks)
        self._poll_timer.start()

    def _create_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CardPanel")
        return card

    def _make_button(
        self,
        text: str,
        object_name: str,
        icon_name: Optional[str] = None,
        icon_color: str = "#334155",
        height: int = 36,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFixedHeight(height)
        btn.setCursor(Qt.PointingHandCursor)
        if icon_name:
            btn.setIcon(get_icon(icon_name, size=16, color=icon_color))
            btn.setIconSize(QSize(16, 16))
        return btn

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("CentralRoot")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # 1. Header
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        logo_label = QLabel()
        logo_label.setPixmap(get_pixmap("layers", size=28, color="#0E7471"))
        header_row.addWidget(logo_label, alignment=Qt.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("Antigravity Task Runner")
        title_lbl.setObjectName("PageTitle")
        subtitle_lbl = QLabel("Sequential Markdown task execution in live interactive agy sessions")
        subtitle_lbl.setObjectName("PageSubtitle")
        title_col.addWidget(title_lbl)
        title_col.addWidget(subtitle_lbl)
        header_row.addLayout(title_col)
        header_row.addStretch(1)

        runtime_badge = QLabel("Auto-Approve & Auto-Continue Active")
        runtime_badge.setObjectName("RuntimeBadge")
        header_row.addWidget(runtime_badge, alignment=Qt.AlignVCenter)

        root_layout.addLayout(header_row)

        # 2. Workspace & Files Card
        paths_card = self._create_card()
        paths_layout = QGridLayout(paths_card)
        paths_layout.setContentsMargins(14, 12, 14, 12)
        paths_layout.setHorizontalSpacing(10)
        paths_layout.setVerticalSpacing(8)
        paths_layout.setColumnStretch(1, 1)

        paths_title = QLabel("Workspace & Task Source")
        paths_title.setObjectName("SectionTitle")
        paths_layout.addWidget(paths_title, 0, 0, 1, 3)

        proj_lbl = QLabel("Project Directory")
        proj_lbl.setObjectName("FieldLabel")
        self.project_dir_edit = QLineEdit()
        self.project_dir_edit.setFixedHeight(36)
        self.project_dir_edit.setPlaceholderText("Select project root directory...")
        browse_proj_btn = self._make_button("Browse...", "SecondaryBtn", "folder", "#334155")
        browse_proj_btn.clicked.connect(self._browse_project_dir)

        paths_layout.addWidget(proj_lbl, 1, 0)
        paths_layout.addWidget(self.project_dir_edit, 1, 1)
        paths_layout.addWidget(browse_proj_btn, 1, 2)

        tasks_lbl = QLabel("Tasks File (.md)")
        tasks_lbl.setObjectName("FieldLabel")
        self.tasks_file_edit = QLineEdit()
        self.tasks_file_edit.setFixedHeight(36)
        self.tasks_file_edit.setPlaceholderText("TASKS.md")
        self.tasks_file_edit.editingFinished.connect(self._reload_tasks)
        browse_tasks_btn = self._make_button("Browse...", "SecondaryBtn", "file", "#334155")
        browse_tasks_btn.clicked.connect(self._browse_tasks_file)

        paths_layout.addWidget(tasks_lbl, 2, 0)
        paths_layout.addWidget(self.tasks_file_edit, 2, 1)
        paths_layout.addWidget(browse_tasks_btn, 2, 2)

        root_layout.addWidget(paths_card)

        # 3. Agent & Session Configuration Card
        config_card = self._create_card()
        config_layout = QGridLayout(config_card)
        config_layout.setContentsMargins(14, 12, 14, 12)
        config_layout.setHorizontalSpacing(12)
        config_layout.setVerticalSpacing(8)
        config_layout.setColumnStretch(1, 2)
        config_layout.setColumnStretch(3, 1)
        config_layout.setColumnStretch(5, 1)

        config_title = QLabel("Agent & Session Configuration")
        config_title.setObjectName("SectionTitle")
        config_layout.addWidget(config_title, 0, 0, 1, 6)

        # Model row with live refresh
        model_lbl = QLabel("Model")
        model_lbl.setObjectName("FieldLabel")
        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        self.model_combo = QComboBox()
        self.model_combo.setFixedHeight(36)
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.NoInsert)
        self.refresh_models_btn = self._make_button("", "SecondaryBtn", "refresh", "#334155")
        self.refresh_models_btn.setFixedWidth(36)
        self.refresh_models_btn.setToolTip("Refresh live models from `agy models`")
        self.refresh_models_btn.clicked.connect(self._refresh_models_async)
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.refresh_models_btn)

        mode_lbl = QLabel("Agent Mode")
        mode_lbl.setObjectName("FieldLabel")
        self.mode_combo = QComboBox()
        self.mode_combo.setFixedHeight(36)
        self.mode_combo.addItems(["accept-edits", "auto", "plan"])

        effort_lbl = QLabel("Effort")
        effort_lbl.setObjectName("FieldLabel")
        self.effort_combo = QComboBox()
        self.effort_combo.setFixedHeight(36)
        self.effort_combo.addItems(["from-task", "low", "medium", "high", "xhigh", "max"])

        config_layout.addWidget(model_lbl, 1, 0)
        config_layout.addLayout(model_row, 1, 1)
        config_layout.addWidget(mode_lbl, 1, 2)
        config_layout.addWidget(self.mode_combo, 1, 3)
        config_layout.addWidget(effort_lbl, 1, 4)
        config_layout.addWidget(self.effort_combo, 1, 5)

        # Session row
        session_lbl = QLabel("Session ID")
        session_lbl.setObjectName("FieldLabel")
        session_row = QHBoxLayout()
        session_row.setSpacing(6)
        self.session_combo = QComboBox()
        self.session_combo.setFixedHeight(36)
        self.session_combo.setEditable(True)
        self.session_combo.setInsertPolicy(QComboBox.NoInsert)

        refresh_sess_btn = self._make_button("Refresh", "SecondaryBtn", "refresh", "#334155")
        refresh_sess_btn.clicked.connect(self._refresh_sessions_list)
        new_sess_btn = self._make_button("New", "SecondaryBtn", "plus", "#0E7471")
        new_sess_btn.clicked.connect(self._generate_new_session)

        session_row.addWidget(self.session_combo, 1)
        session_row.addWidget(refresh_sess_btn)
        session_row.addWidget(new_sess_btn)

        config_layout.addWidget(session_lbl, 2, 0)
        config_layout.addLayout(session_row, 2, 1, 1, 5)

        root_layout.addWidget(config_card)

        # 4. Tasks Table Card
        tasks_card = self._create_card()
        tasks_layout = QVBoxLayout(tasks_card)
        tasks_layout.setContentsMargins(14, 12, 14, 12)
        tasks_layout.setSpacing(8)

        tasks_header = QHBoxLayout()
        tasks_title = QLabel("Tasks Queue")
        tasks_title.setObjectName("SectionTitle")
        tasks_header.addWidget(tasks_title)
        tasks_header.addStretch(1)
        reload_btn = self._make_button("Reload Tasks", "SecondaryBtn", "refresh", "#334155", height=32)
        reload_btn.clicked.connect(self._reload_tasks)
        tasks_header.addWidget(reload_btn)
        tasks_layout.addLayout(tasks_header)

        self.tasks_table = QTableWidget(0, 4)
        self.tasks_table.setHorizontalHeaderLabels(["Task #", "Effort", "Status", "Task Description"])
        self.tasks_table.verticalHeader().setVisible(False)
        self.tasks_table.verticalHeader().setDefaultSectionSize(38)
        self.tasks_table.horizontalHeader().setFixedHeight(38)
        self.tasks_table.horizontalHeader().setMinimumSectionSize(80)
        self.tasks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tasks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tasks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tasks_table.setAlternatingRowColors(True)
        self.tasks_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tasks_table.setSelectionMode(QTableWidget.SingleSelection)
        self.tasks_table.setEditTriggers(QTableWidget.NoEditTriggers)
        tasks_layout.addWidget(self.tasks_table, 1)

        self.status_summary_label = QLabel("Scanning tasks file...")
        self.status_summary_label.setObjectName("StatusSummary")
        tasks_layout.addWidget(self.status_summary_label)

        root_layout.addWidget(tasks_card, 1)

        # 5. Primary Action Bar
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self.run_all_btn = self._make_button(
            "Run All Pending Tasks",
            "PrimaryBtn",
            "play",
            "#FFFFFF",
            height=38,
        )
        self.run_all_btn.clicked.connect(self._start_all_tasks_interactive)

        self.run_selected_btn = self._make_button(
            "Run Selected Task",
            "TealOutlineBtn",
            "zap",
            "#0E7471",
            height=38,
        )
        self.run_selected_btn.clicked.connect(self._start_selected_task_interactive)

        self.open_shell_btn = self._make_button(
            "Open Interactive agy Shell",
            "SecondaryBtn",
            "terminal",
            "#334155",
            height=38,
        )
        self.open_shell_btn.clicked.connect(self._open_direct_agy_shell)

        exit_btn = self._make_button("Exit", "SecondaryBtn", height=38)
        exit_btn.clicked.connect(self.close)

        actions_row.addWidget(self.run_all_btn)
        actions_row.addWidget(self.run_selected_btn)
        actions_row.addWidget(self.open_shell_btn)
        actions_row.addStretch(1)
        actions_row.addWidget(exit_btn)

        root_layout.addLayout(actions_row)

        # 6. Activity Log Card
        log_card = self._create_card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(14, 10, 14, 12)
        log_layout.setSpacing(6)

        log_title = QLabel("Activity Log")
        log_title.setObjectName("SectionTitle")
        log_layout.addWidget(log_title)

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("ActivityLog")
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(105)
        log_layout.addWidget(self.log_output)

        root_layout.addWidget(log_card)

    def _initialize_defaults(self) -> None:
        cwd = Path(os.getcwd())
        self.project_dir_edit.setText(str(cwd))

        tasks_path = "TASKS.md"
        for candidate_name in ("TASKS.md", "tasks.md", "docs/tasks.md", "docs/TASKS.md"):
            cand = cwd / candidate_name
            if cand.is_file():
                tasks_path = str(cand)
                break
        self.tasks_file_edit.setText(tasks_path)

        self._populate_models_combo(FALLBACK_MODELS)
        self._populate_sessions_combo()

    def _populate_models_combo(self, models: List[ModelInfo]) -> None:
        current_id = self._get_selected_model_id() or DEFAULT_MODEL
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        selected_idx = -1
        for idx, m in enumerate(models):
            label = f"{m['display_name']}  [{m['id']}]"
            self.model_combo.addItem(label, userData=m["id"])
            if m["id"] == current_id:
                selected_idx = idx
        if selected_idx >= 0:
            self.model_combo.setCurrentIndex(selected_idx)
        elif self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _get_selected_model_id(self) -> str:
        idx = self.model_combo.currentIndex()
        if idx >= 0:
            item_data = self.model_combo.itemData(idx, Qt.UserRole)
            item_text = self.model_combo.itemText(idx)
            if item_data and self.model_combo.currentText() == item_text:
                return str(item_data).strip()
        raw = self.model_combo.currentText().strip()
        if raw.endswith("]") and "[" in raw:
            return raw.rsplit("[", 1)[-1].rstrip("]").strip()
        return raw or DEFAULT_MODEL

    def _refresh_models_async(self) -> None:
        if self._model_thread is not None and self._model_thread.isRunning():
            return
        self.refresh_models_btn.setEnabled(False)
        self.refresh_models_btn.setToolTip("Fetching models from `agy models`...")
        self._model_thread = ModelLoaderThread(self)
        self._model_thread.models_loaded.connect(self._on_models_loaded)
        self._model_thread.start()

    def _on_models_loaded(self, models: list, is_live: bool) -> None:
        self.refresh_models_btn.setEnabled(True)
        self.refresh_models_btn.setToolTip("Refresh live models from `agy models`")
        if models:
            self._populate_models_combo(models)
        if is_live:
            self._log_message(f"Loaded {len(models)} live model(s) from `agy models`.")
        else:
            self._log_message("Could not reach `agy models`; using built-in fallback model list.")

    def _discover_recent_sessions(self) -> List[str]:
        brain_dir = get_agy_brain_dir()
        if not brain_dir.is_dir():
            return []

        sessions_with_mtime: List[Tuple[float, str]] = []
        try:
            for child in brain_dir.iterdir():
                if not child.is_dir():
                    continue
                transcript = child / ".system_generated" / "logs" / "transcript.jsonl"
                if transcript.is_file():
                    sessions_with_mtime.append((transcript.stat().st_mtime, child.name))
                else:
                    sessions_with_mtime.append((child.stat().st_mtime, child.name))
        except Exception:
            pass

        sessions_with_mtime.sort(key=lambda item: item[0], reverse=True)
        return [sid for _, sid in sessions_with_mtime[:25]]

    def _populate_sessions_combo(self) -> None:
        current = self.session_combo.currentText().strip()
        self.session_combo.clear()
        items = self.recent_sessions + ["new"]
        self.session_combo.addItems(items)
        if current:
            self.session_combo.setCurrentText(current)
        elif items:
            self.session_combo.setCurrentIndex(0)

    def _refresh_sessions_list(self) -> None:
        self.recent_sessions = self._discover_recent_sessions()
        self._populate_sessions_combo()
        self._log_message(f"Refreshed session list ({len(self.recent_sessions)} session(s) found).")

    def _generate_new_session(self) -> None:
        self.session_combo.setCurrentText("new")
        self._log_message("Session set to 'new' — a unified live session will be created on launch.")

    def _log_message(self, msg: str) -> None:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{now_str}] {msg}")

    def _browse_project_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Project Directory",
            self.project_dir_edit.text().strip() or os.getcwd(),
        )
        if chosen:
            self.project_dir_edit.setText(chosen)
            for rel in ("TASKS.md", "tasks.md", "docs/tasks.md", "docs/TASKS.md"):
                cand = Path(chosen) / rel
                if cand.is_file():
                    self.tasks_file_edit.setText(str(cand))
                    break
            self._reload_tasks()

    def _browse_tasks_file(self) -> None:
        initial_dir = self.project_dir_edit.text().strip() or os.getcwd()
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Tasks File",
            initial_dir,
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*.*)",
        )
        if chosen:
            self.tasks_file_edit.setText(chosen)
            self._reload_tasks()

    def _resolve_paths(self) -> Tuple[Optional[Path], Optional[Path]]:
        p_dir_str = self.project_dir_edit.text().strip()
        t_file_str = self.tasks_file_edit.text().strip()

        if not p_dir_str:
            return None, None
        proj_path = clean_to_absolute_path(p_dir_str)

        if not t_file_str:
            return proj_path, None

        tasks_candidate = Path(t_file_str)
        if tasks_candidate.is_absolute() or tasks_candidate.is_file():
            tasks_path = clean_to_absolute_path(tasks_candidate)
        else:
            tasks_path = clean_to_absolute_path(proj_path / t_file_str)

        return proj_path, tasks_path

    def _reload_tasks(self) -> None:
        _, tasks_path = self._resolve_paths()
        self.tasks_table.setRowCount(0)

        if not tasks_path or not tasks_path.is_file():
            self.status_summary_label.setText("Tasks file not found or not selected.")
            self.pending_tasks = []
            self.completed_task_ids = []
            return

        try:
            self.last_tasks_mtime = tasks_path.stat().st_mtime
            pending, skipped = parse_tasks_file(tasks_path)
            self.pending_tasks = pending
            self.completed_task_ids = skipped

            total_rows = len(pending) + len(skipped)
            self.tasks_table.setRowCount(total_rows)

            row = 0
            for t in pending:
                first_line = t["content"].splitlines()[0] if t["content"] else ""
                preview = first_line[:110] + ("..." if len(first_line) > 110 else "")

                id_item = QTableWidgetItem(f"#{t['id']}")
                id_item.setTextAlignment(Qt.AlignCenter)
                id_item.setData(Qt.UserRole, t["id"])

                effort_item = QTableWidgetItem(t["effort"].upper())
                effort_item.setTextAlignment(Qt.AlignCenter)

                status_item = QTableWidgetItem(get_icon("clock", size=14, color="#D97706"), "Pending")
                status_item.setForeground(QColor("#B45309"))

                desc_item = QTableWidgetItem(preview)

                self.tasks_table.setItem(row, 0, id_item)
                self.tasks_table.setItem(row, 1, effort_item)
                self.tasks_table.setItem(row, 2, status_item)
                self.tasks_table.setItem(row, 3, desc_item)
                row += 1

            completed_bg = QColor("#F0FDF4")
            completed_fg = QColor("#15803D")
            bold_font = QFont()
            bold_font.setBold(True)

            for cid in skipped:
                id_item = QTableWidgetItem(f"#{cid}")
                id_item.setTextAlignment(Qt.AlignCenter)
                id_item.setData(Qt.UserRole, cid)

                effort_item = QTableWidgetItem("-")
                effort_item.setTextAlignment(Qt.AlignCenter)

                status_item = QTableWidgetItem(get_icon("check_circle", size=14, color="#16A34A"), "Completed")
                status_item.setForeground(completed_fg)
                status_item.setFont(bold_font)

                desc_item = QTableWidgetItem("(Previously completed)")
                desc_item.setForeground(QColor("#64748B"))

                for col_idx, item in enumerate((id_item, effort_item, status_item, desc_item)):
                    item.setBackground(completed_bg)
                    self.tasks_table.setItem(row, col_idx, item)
                row += 1

            self.status_summary_label.setText(
                f"Total: {total_rows}  |  Pending: {len(pending)}  |  Completed: {len(skipped)}"
            )
        except Exception as err:
            self.status_summary_label.setText(f"Error parsing tasks file: {err}")
            self._log_message(f"Error parsing tasks file: {err}")

    def _auto_poll_tasks(self) -> None:
        _, tasks_path = self._resolve_paths()
        if tasks_path and tasks_path.is_file():
            try:
                current_mtime = tasks_path.stat().st_mtime
                if current_mtime != self.last_tasks_mtime:
                    self._log_message(f"Detected changes in {tasks_path.name}; reloading tasks...")
                    self._reload_tasks()
            except Exception:
                pass

    def _launch_worker_process(self, specific_task_id: Optional[str] = None) -> None:
        proj_path, tasks_path = self._resolve_paths()

        if not proj_path or not proj_path.is_dir():
            QMessageBox.critical(self, "Invalid Directory", f"Project directory not found:\n{proj_path}")
            return

        if not tasks_path or not tasks_path.is_file():
            QMessageBox.critical(self, "Invalid File", f"Tasks file not found:\n{tasks_path}")
            return

        session_id = self.session_combo.currentText().strip() or f"agy-session-{uuid.uuid4().hex[:10]}"
        model = self._get_selected_model_id()
        mode = self.mode_combo.currentText().strip() or "accept-edits"
        effort = self.effort_combo.currentText().strip() or "from-task"

        target_desc = f"Task #{specific_task_id}" if specific_task_id else "all pending tasks"

        worker_script = Path(__file__).resolve().parent / "interactive_worker.py"
        repo_root = Path(__file__).resolve().parent.parent

        worker_args = [
            f'"{sys.executable}"',
            f'"{worker_script}"',
            "--project-dir", f'"{proj_path}"',
            "--tasks-file", f'"{tasks_path}"',
            "--session", f'"{session_id}"',
            "--model", f'"{model}"',
            "--mode", f'"{mode}"',
            "--effort", f'"{effort}"',
        ]
        if specific_task_id:
            worker_args.extend(["--task-id", f'"{specific_task_id}"'])

        try:
            if sys.platform == "win32":
                win_title = f"Antigravity Live Runner - {target_desc} [{session_id}]"
                inner_cmd = (
                    f'chcp 65001 >nul && set "PYTHONPATH={repo_root};%PYTHONPATH%" && '
                    + " ".join(worker_args)
                )
                spawn_cmd = f'start "{win_title}" cmd.exe /k "{inner_cmd}"'
                subprocess.Popen(spawn_cmd, shell=True, cwd=str(proj_path))
            else:
                creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                cmd_list = [
                    sys.executable,
                    str(worker_script),
                    "--project-dir", str(proj_path),
                    "--tasks-file", str(tasks_path),
                    "--session", session_id,
                    "--model", model,
                    "--mode", mode,
                    "--effort", effort,
                ]
                if specific_task_id:
                    cmd_list.extend(["--task-id", str(specific_task_id)])

                env = os.environ.copy()
                env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
                subprocess.Popen(cmd_list, cwd=str(proj_path), env=env, creationflags=creationflags)

            self.status_summary_label.setText(f"Launched live terminal for {target_desc}.")
            self._log_message(f"Launched live agy runner for {target_desc} (Model: {model}, Session: {session_id}).")

        except Exception as e:
            QMessageBox.critical(self, "Launch Failed", f"Could not launch terminal:\n{e}")
            self._log_message(f"Failed to launch terminal: {e}")

    def _start_all_tasks_interactive(self) -> None:
        if not self.pending_tasks:
            QMessageBox.information(self, "No Pending Tasks", "All tasks in the current file are already completed.")
            return
        self._launch_worker_process(specific_task_id=None)

    def _start_selected_task_interactive(self) -> None:
        row = self.tasks_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a task row from the table first.")
            return
        id_item = self.tasks_table.item(row, 0)
        if not id_item:
            return
        task_id = str(id_item.data(Qt.UserRole) or id_item.text().lstrip("#"))
        self._launch_worker_process(specific_task_id=task_id)

    def _open_direct_agy_shell(self) -> None:
        proj_path, _ = self._resolve_paths()
        if not proj_path or not proj_path.is_dir():
            QMessageBox.critical(self, "Invalid Directory", "Please select a valid project directory first.")
            return

        session_id = self.session_combo.currentText().strip()
        raw_model = self._get_selected_model_id()
        raw_effort = self.effort_combo.currentText().strip() or "medium"
        resolved_model, _ = resolve_agy_model_and_effort(raw_model, raw_effort)
        mode = self.mode_combo.currentText().strip() or "accept-edits"
        agy_executable = shutil.which("agy") or "agy"
        session_exists = bool(
            session_id and session_id != "new" and (get_agy_brain_dir() / session_id).is_dir()
        )

        try:
            if sys.platform == "win32":
                win_title = f"Antigravity Interactive Shell [{session_id or 'new'}]"
                conv_arg = f"--conversation {session_id} " if session_exists else ""
                inner_cmd = (
                    f'chcp 65001 >nul && "{agy_executable}" {conv_arg}'
                    f'--add-dir "{proj_path}" --model {resolved_model} --mode {mode} '
                    f'--dangerously-skip-permissions'
                )
                spawn_cmd = f'start "{win_title}" cmd.exe /k "{inner_cmd}"'
                subprocess.Popen(spawn_cmd, shell=True, cwd=str(proj_path))
            else:
                creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                cmd_list = [agy_executable]
                if session_exists:
                    cmd_list.extend(["--conversation", session_id])
                cmd_list.extend([
                    "--add-dir", str(proj_path),
                    "--model", resolved_model,
                    "--mode", mode,
                    "--dangerously-skip-permissions",
                ])
                subprocess.Popen(cmd_list, cwd=str(proj_path), creationflags=creationflags)

            self._log_message(f"Opened interactive agy shell in: {proj_path} (Model: {resolved_model})")
        except Exception as e:
            QMessageBox.critical(self, "Launch Failed", f"Could not open agy shell:\n{e}")
            self._log_message(f"Failed to open agy shell: {e}")


def launch_ui() -> None:
    """Launch the PySide6 desktop GUI."""
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    window = AntigravityTaskRunnerUI()
    window.show()

    if owns_app:
        sys.exit(app.exec())


if __name__ == "__main__":
    launch_ui()
