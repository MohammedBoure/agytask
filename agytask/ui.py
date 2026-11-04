"""
ui.py - واجهة مستخدم رسومية احترافية مبنية بـ Tkinter لإدارة وتشغيل مهام Antigravity تفاعلياً.
"""

import os
import sys
import uuid
import shutil
import datetime
import subprocess
from pathlib import Path
from typing import Optional, List

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .parser import clean_to_absolute_path, parse_tasks_file, Task
from .runner import DEFAULT_MODEL
from .interactive_worker import get_agy_brain_dir, resolve_agy_model_and_effort


class AntigravityTaskRunnerUI:
    """فئة الواجهة الرسومية الرئيسية لـ Antigravity Task Runner."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Antigravity Task Runner - مُشغّل المهام التفاعلي (agy -i)")
        self.root.geometry("960x780")
        self.root.minsize(850, 680)

        # المتغيرات المرتبطة بعناصر التحكم
        self.project_dir_var = tk.StringVar(value=os.getcwd())
        self.tasks_file_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.mode_var = tk.StringVar(value="accept-edits")
        self.effort_var = tk.StringVar(value="from-task")
        self.recent_sessions: List[str] = self._discover_recent_sessions()
        default_session = self.recent_sessions[0] if self.recent_sessions else "new"
        self.session_id_var = tk.StringVar(value=default_session)
        self.skip_permissions_var = tk.BooleanVar(value=True)
        self.auto_next_var = tk.BooleanVar(value=True)
        self.exec_engine_var = tk.StringVar(value="agy-i")
        self.status_summary_var = tk.StringVar(value="جاري فحص ملف المهام...")

        self.last_tasks_mtime: float = 0.0
        self.pending_tasks: List[Task] = []
        self.completed_task_ids: List[str] = []

        # محاولة البحث عن TASKS.md أو tasks.md في المجلد الحالي افتراضياً
        cur_dir = Path(self.project_dir_var.get())
        for candidate_name in ("TASKS.md", "tasks.md", "docs/tasks.md", "docs/TASKS.md"):
            cand = cur_dir / candidate_name
            if cand.is_file():
                self.tasks_file_var.set(str(cand))
                break
        if not self.tasks_file_var.get():
            self.tasks_file_var.set("TASKS.md")

        self._configure_styles()
        self._build_ui()
        self._reload_tasks()

        # إضافة رسالة ترحيبية في سجل النشاط
        self._log_message("مرحباً بك في Antigravity Task Runner. حدد مسارات العمل واضغط على بدء التشغيل.")

        # بدء عملية الاستطلاع الدوري لتحديث حالة المهام تلقائياً عند تعديل الملف
        self.root.after(2000, self._auto_poll_tasks)

    def _configure_styles(self) -> None:
        """تهيئة المظهر والأنماط البصرية باستخدام ttk.Style."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.root.configure(bg="#f8fafc")

        style.configure("TFrame", background="#f8fafc")
        style.configure("TLabelframe", background="#f8fafc", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background="#f8fafc", foreground="#1e293b")
        style.configure("TLabel", background="#f8fafc", font=("Segoe UI", 9), foreground="#334155")
        style.configure("TCheckbutton", background="#f8fafc", font=("Segoe UI", 9), foreground="#1e293b")
        style.configure("TRadiobutton", background="#f8fafc", font=("Segoe UI", 9), foreground="#1e293b")

        # تخصيص الأزرار
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#2563eb",
            foreground="#ffffff",
            padding=6
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1d4ed8"), ("pressed", "#1e40af")],
            foreground=[("active", "#ffffff")]
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            background="#e2e8f0",
            foreground="#1e293b",
            padding=5
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#cbd5e1")]
        )

        style.configure(
            "AccentGreen.TButton",
            font=("Segoe UI", 9, "bold"),
            background="#16a34a",
            foreground="#ffffff",
            padding=5
        )
        style.map(
            "AccentGreen.TButton",
            background=[("active", "#15803d")]
        )

        # تخصيص جدول المهام Treeview
        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=28,
            background="#ffffff",
            fieldbackground="#ffffff"
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), foreground="#1e293b")

    def _build_ui(self) -> None:
        """بناء جميع عناصر الواجهة الرسومية."""
        main_container = ttk.Frame(self.root, padding="14")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. الترويسة العليا (Header)
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = tk.Label(
            header_frame,
            text="⚡ Antigravity Task Runner - مُشغّل المهام التفاعلي (agy -i)",
            font=("Segoe UI", 14, "bold"),
            bg="#f8fafc",
            fg="#0f172a"
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="تشغيل مهام Markdown تسلسلياً مع فتح نافذة طرفية مستقلة لمشاهدة الوكيل حياً عبر agy -i",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#64748b"
        )
        subtitle_label.pack(anchor="w")

        # 2. قسم المسارات (Paths Frame)
        paths_frame = ttk.LabelFrame(main_container, text=" مسارات العمل (Paths) ", padding="10")
        paths_frame.pack(fill=tk.X, pady=(0, 10))
        paths_frame.columnconfigure(1, weight=1)

        # مجلد المشروع
        ttk.Label(paths_frame, text="مجلد المشروع:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        proj_entry = ttk.Entry(paths_frame, textvariable=self.project_dir_var, font=("Segoe UI", 9))
        proj_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=4)
        ttk.Button(paths_frame, text="📁 تصفح...", command=self._browse_project_dir, style="Secondary.TButton").grid(row=0, column=2, pady=4)

        # ملف المهام
        ttk.Label(paths_frame, text="ملف المهام (Markdown):").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        tasks_entry = ttk.Entry(paths_frame, textvariable=self.tasks_file_var, font=("Segoe UI", 9))
        tasks_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)
        tasks_entry.bind("<FocusOut>", lambda e: self._reload_tasks())
        tasks_entry.bind("<Return>", lambda e: self._reload_tasks())
        ttk.Button(paths_frame, text="📄 تصفح...", command=self._browse_tasks_file, style="Secondary.TButton").grid(row=1, column=2, pady=4)

        # 3. قسم الإعدادات (Settings Frame)
        settings_frame = ttk.LabelFrame(main_container, text=" إعدادات الجلسة والوكيل (Session & Agent Settings) ", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        for col in (1, 3, 5):
            settings_frame.columnconfigure(col, weight=1)

        # السطر الأول: النموذج، الوضع، الجهد
        ttk.Label(settings_frame, text="النموذج:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        model_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.model_var,
            values=[
                "gemini-3.8-flash",
                "gemini-3.8-flash-medium",
                "gemini-3.8-flash-high",
                "gemini-4-argon-medium",
                "gemini-4-argon-high",
                "claude-sonnet-5-5-medium",
                "claude-sonnet-5-5-high",
                "claude-opus-5-5-medium",
                "claude-opus-5-5-high",
                "gpt-oss-120b-medium",
            ],
            font=("Segoe UI", 9)
        )
        model_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(settings_frame, text="وضع الوكيل:").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        mode_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.mode_var,
            values=["accept-edits", "auto", "plan"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        mode_combo.grid(row=0, column=3, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(settings_frame, text="جهد التفكير:").grid(row=0, column=4, sticky="w", padx=(0, 6), pady=4)
        effort_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.effort_var,
            values=["from-task", "low", "medium", "high", "xhigh", "max"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        effort_combo.grid(row=0, column=5, sticky="ew", pady=4)

        # السطر الثاني: معرف الجلسة (قائمة منسدلة بالجلسات السابقة + إمكانية إدخال أي معرف)
        ttk.Label(settings_frame, text="معرف الجلسة:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        session_frame = ttk.Frame(settings_frame)
        session_frame.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4)
        session_frame.columnconfigure(0, weight=1)
        self.session_combo = ttk.Combobox(
            session_frame,
            textvariable=self.session_id_var,
            values=self.recent_sessions + ["new"],
            font=("Segoe UI", 9)
        )
        self.session_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(session_frame, text="🔄 تحديث", command=self._refresh_sessions_list, style="Secondary.TButton").grid(row=0, column=1, padx=(0, 4))
        ttk.Button(session_frame, text="🆕 جديد", command=self._generate_new_session, style="Secondary.TButton").grid(row=0, column=2)

        # آلية التشغيل
        ttk.Label(settings_frame, text="طريقة العرض:").grid(row=1, column=4, sticky="w", padx=(0, 6), pady=4)
        engine_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.exec_engine_var,
            values=["agy-i", "agy-p"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        engine_combo.grid(row=1, column=5, sticky="ew", pady=4)

        # السطر الثالث: خيارات الأمان والمتابعة التلقائية
        options_frame = ttk.Frame(settings_frame)
        options_frame.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            options_frame,
            text="تخطي طلب الأذونات تلقائياً (--dangerously-skip-permissions)",
            variable=self.skip_permissions_var
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Checkbutton(
            options_frame,
            text="متابعة تلقائية بين المهام مع عد تنازلي (Auto-Next)",
            variable=self.auto_next_var
        ).pack(side=tk.LEFT)

        # 4. قسم استعراض المهام (Tasks Preview Table)
        tasks_group = ttk.LabelFrame(main_container, text=" قائمة المهام المستخرجة (Tasks List) ", padding="10")
        tasks_group.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # جدول Treeview مع شريط تمرير
        table_container = ttk.Frame(tasks_group)
        table_container.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "effort", "status", "preview")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="المهمة (#)")
        self.tree.heading("effort", text="الجهد")
        self.tree.heading("status", text="الحالة")
        self.tree.heading("preview", text="نص المهمة المطلوب تنفيذها")

        self.tree.column("id", width=80, anchor="center")
        self.tree.column("effort", width=95, anchor="center")
        self.tree.column("status", width=140, anchor="center")
        self.tree.column("preview", width=580, anchor="w")

        self.tree.tag_configure("completed", foreground="#16a34a", background="#f0fdf4")
        self.tree.tag_configure("pending", foreground="#0f172a", background="#ffffff")

        scrollbar = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # شريط إحصائيات المهام أسفل الجدول
        stats_frame = ttk.Frame(tasks_group)
        stats_frame.pack(fill=tk.X, pady=(6, 0))
        self.stats_label = tk.Label(
            stats_frame,
            textvariable=self.status_summary_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#2563eb"
        )
        self.stats_label.pack(side=tk.LEFT)

        ttk.Button(
            stats_frame,
            text="🔄 إعادة قراءة الملف",
            command=self._reload_tasks,
            style="Secondary.TButton"
        ).pack(side=tk.RIGHT)

        # 5. شريط أزرار التشغيل والتحكم (Action Buttons)
        actions_frame = ttk.Frame(main_container)
        actions_frame.pack(fill=tk.X, pady=(4, 8))

        # الزر الرئيسي: إطلاق طرفية agy -i التفاعلية الحية
        run_all_btn = ttk.Button(
            actions_frame,
            text="▶ (agy -i) بدء تشغيل المهام التفاعلية",
            command=self._start_all_tasks_interactive,
            style="Primary.TButton"
        )
        run_all_btn.pack(side=tk.LEFT, padx=(0, 8))

        # تشغيل المهمة المحددة فقط
        run_single_btn = ttk.Button(
            actions_frame,
            text="⚡ تشغيل المهمة المحددة فقط",
            command=self._start_selected_task_interactive,
            style="AccentGreen.TButton"
        )
        run_single_btn.pack(side=tk.LEFT, padx=(0, 8))

        # فتح طرفية agy تفاعلية مباشرة
        shell_btn = ttk.Button(
            actions_frame,
            text="💻 فتح طرفية agy تفاعلية",
            command=self._open_direct_agy_shell,
            style="Secondary.TButton"
        )
        shell_btn.pack(side=tk.LEFT, padx=(0, 8))

        # زر إغلاق
        close_btn = ttk.Button(
            actions_frame,
            text="خروج",
            command=self.root.destroy,
            style="Secondary.TButton"
        )
        close_btn.pack(side=tk.RIGHT)

        # 6. قسم سجل النشاط والمتابعة الحية داخل الواجهة (Live Activity Log)
        log_group = ttk.LabelFrame(main_container, text=" سجل النشاط ومتابعة التنفيذ (Live Log) ", padding="6")
        log_group.pack(fill=tk.X, pady=(0, 0))

        log_container = ttk.Frame(log_group)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_container,
            height=4,
            bg="#0f172a",
            fg="#38bdf8",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            wrap=tk.WORD
        )
        log_scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _log_message(self, msg: str) -> None:
        """إضافة سطر جديد إلى سجل النشاط المباشر."""
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{now_str}] {msg}\n")
        self.log_text.see(tk.END)

    def _browse_project_dir(self) -> None:
        """اختيار مجلد المشروع عبر نافذة التصفح."""
        chosen = filedialog.askdirectory(
            initialdir=self.project_dir_var.get() or os.getcwd(),
            title="اختر مجلد المشروع"
        )
        if chosen:
            self.project_dir_var.set(chosen)
            # فحص تلقائي لملفات المهام داخل المجلد الجديد
            cand_paths = [
                Path(chosen) / "TASKS.md",
                Path(chosen) / "tasks.md",
                Path(chosen) / "docs" / "tasks.md",
                Path(chosen) / "docs" / "TASKS.md",
            ]
            for cand in cand_paths:
                if cand.is_file():
                    self.tasks_file_var.set(str(cand))
                    break
            self._reload_tasks()

    def _browse_tasks_file(self) -> None:
        """اختيار ملف المهام بصيغة Markdown عبر نافذة التصفح."""
        initial_dir = self.project_dir_var.get() or os.getcwd()
        chosen = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="اختر ملف المهام",
            filetypes=[
                ("Markdown Files", "*.md"),
                ("Text Files", "*.txt"),
                ("All Files", "*.*")
            ]
        )
        if chosen:
            self.tasks_file_var.set(chosen)
            self._reload_tasks()

    def _discover_recent_sessions(self) -> List[str]:
        """استكشاف أحدث جلسات المحادثات الموجودة في مجلد brain الخاص بـ agy."""
        brain_dir = get_agy_brain_dir()
        if not brain_dir.is_dir():
            return []

        sessions_with_mtime: List[tuple[float, str]] = []
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

    def _refresh_sessions_list(self) -> None:
        """تحديث قائمة الجلسات السابقة من مجلد محادثات agy."""
        self.recent_sessions = self._discover_recent_sessions()
        if hasattr(self, "session_combo"):
            self.session_combo["values"] = self.recent_sessions + ["new"]
        self._log_message(f"تم تحديث قائمة الجلسات المتاحة ({len(self.recent_sessions)} جلسة).")

    def _generate_new_session(self) -> None:
        """تحديد بدء جلسة جديدة موحدة."""
        self.session_id_var.set("new")
        self._log_message("تم ضبط الجلسة على (new) لإنشاء جلسة حية جديدة موحدة عند بدء التنفيذ.")

    def _resolve_paths(self) -> tuple[Optional[Path], Optional[Path]]:
        """التحقق من المسارات وإرجاع كائنات Path صالحة."""
        p_dir_str = self.project_dir_var.get().strip()
        t_file_str = self.tasks_file_var.get().strip()

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
        """قراءة ملف المهام وتحديث جدول العرض والإحصائيات."""
        proj_path, tasks_path = self._resolve_paths()

        # مسح العناصر الحالية من الجدول
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not tasks_path or not tasks_path.is_file():
            self.status_summary_var.set("⚠️ ملف المهام غير موجود أو لم يتم تحديده بعد.")
            self.pending_tasks = []
            self.completed_task_ids = []
            return

        try:
            self.last_tasks_mtime = tasks_path.stat().st_mtime
            pending, skipped = parse_tasks_file(tasks_path)
            self.pending_tasks = pending
            self.completed_task_ids = skipped

            # إضافة المهام المعلقة
            for t in pending:
                first_line = t["content"].splitlines()[0] if t["content"] else ""
                preview = first_line[:95] + ("..." if len(first_line) > 95 else "")
                self.tree.insert(
                    "",
                    tk.END,
                    iid=f"task_{t['id']}",
                    values=(f"#{t['id']}", t["effort"].upper(), "⏳ قيد الانتظار", preview),
                    tags=("pending",)
                )

            # إضافة المهام المكتملة
            for cid in skipped:
                self.tree.insert(
                    "",
                    tk.END,
                    iid=f"task_{cid}",
                    values=(f"#{cid}", "-", "✔ مكتملة [COMPLETED]", "(تم إنجازها مسبقاً)"),
                    tags=("completed",)
                )

            total = len(pending) + len(skipped)
            summary_msg = f"📊 إجمالي المهام: {total}  |  ⏳ قيد الانتظار: {len(pending)}  |  ✔ مكتملة: {len(skipped)}"
            self.status_summary_var.set(summary_msg)

        except Exception as err:
            self.status_summary_var.set(f"❌ خطأ أثناء تحليل ملف المهام: {err}")
            self._log_message(f"خطأ في تحليل ملف المهام: {err}")

    def _auto_poll_tasks(self) -> None:
        """استطلاع دوري للملف لتحديث الجدول تلقائياً إذا تغير الملف في الخلفية."""
        _, tasks_path = self._resolve_paths()
        if tasks_path and tasks_path.is_file():
            try:
                current_mtime = tasks_path.stat().st_mtime
                if current_mtime != self.last_tasks_mtime:
                    self._log_message(f"تم رصد تحديث في ملف المهام ({tasks_path.name})، جاري تحديث الجدول...")
                    self._reload_tasks()
            except Exception:
                pass

        self.root.after(2000, self._auto_poll_tasks)

    def _launch_worker_process(self, specific_task_id: Optional[str] = None) -> None:
        """
        إطلاق معالج المهام التفاعلي في نافذة طرفية مستقلة وظاهرة في المقدمة لعرض agy -i حياً.
        """
        proj_path, tasks_path = self._resolve_paths()

        if not proj_path or not proj_path.is_dir():
            messagebox.showerror("خطأ في المسار", f"مجلد المشروع غير موجود:\n{proj_path}")
            return

        if not tasks_path or not tasks_path.is_file():
            messagebox.showerror("خطأ في الملف", f"ملف المهام غير موجود:\n{tasks_path}")
            return

        session_id = self.session_id_var.get().strip() or f"agy-session-{uuid.uuid4().hex[:10]}"
        model = self.model_var.get().strip() or DEFAULT_MODEL
        mode = self.mode_var.get().strip() or "accept-edits"
        effort = self.effort_var.get().strip() or "from-task"
        skip_perm = self.skip_permissions_var.get()
        auto_next = self.auto_next_var.get()

        target_desc = f"المهمة #{specific_task_id}" if specific_task_id else "جميع المهام المعلقة"

        # الحصول على المسار المطلق الدقيق لسكربت interactive_worker.py ومجلد المستودع
        worker_script = Path(__file__).resolve().parent / "interactive_worker.py"
        repo_root = Path(__file__).resolve().parent.parent

        # بناء معاملات تشغيل سكربت العامل التفاعلي مباشرة عبر مساره لضمان عمله في أي بيئة ومجلد
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

        if skip_perm:
            worker_args.append("--dangerously-skip-permissions")

        if not auto_next:
            worker_args.append("--no-auto-next")

        if specific_task_id:
            worker_args.extend(["--task-id", f'"{specific_task_id}"'])

        try:
            if sys.platform == "win32":
                # استخدام start cmd.exe /k لضمان فتح نافذة طرفية Command Prompt مستقلة ومرئية في المقدمة وبقائها مفتوحة
                win_title = f"Antigravity Live Runner - {target_desc} [{session_id}]"
                inner_cmd = f'chcp 65001 >nul && set "PYTHONPATH={repo_root};%PYTHONPATH%" && ' + " ".join(worker_args)
                spawn_cmd = f'start "{win_title}" cmd.exe /k "{inner_cmd}"'

                subprocess.Popen(
                    spawn_cmd,
                    shell=True,
                    cwd=str(proj_path)
                )
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
                if skip_perm:
                    cmd_list.append("--dangerously-skip-permissions")
                if not auto_next:
                    cmd_list.append("--no-auto-next")
                if specific_task_id:
                    cmd_list.extend(["--task-id", str(specific_task_id)])

                env = os.environ.copy()
                env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{env.get('PYTHONPATH', '')}"

                subprocess.Popen(
                    cmd_list,
                    cwd=str(proj_path),
                    env=env,
                    creationflags=creationflags
                )

            self.status_summary_var.set(f"🚀 تم فتح نافذة الطرفية الحية لـ {target_desc} عبر agy -i.")
            self._log_message(f"تم إطلاق نافذة طرفية مستقلة لـ {target_desc}.")
            self._log_message(f"شاهد عمل الوكيل مباشرة في نافذة الطرفية المفتوحة أمامك الآن.")

        except Exception as e:
            messagebox.showerror("فشل التشغيل", f"تعذر إطلاق نافذة الطرفية:\n{e}")
            self._log_message(f"خطأ أثناء إطلاق الطرفية: {e}")

    def _start_all_tasks_interactive(self) -> None:
        """بدء تنفيذ جميع المهام المعلقة تفاعلياً."""
        if not self.pending_tasks:
            messagebox.showinfo("تنبيه", "لا توجد مهام معلقة للتنفيذ في الملف الحالي!")
            return
        self._launch_worker_process(specific_task_id=None)

    def _start_selected_task_interactive(self) -> None:
        """بدء تنفيذ المهمة المحددة فقط من الجدول."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("تنبيه", "يرجى تحديد مهمة من الجدول أولاً بالنقر عليها.")
            return

        item_id = selected[0]
        task_id = item_id.replace("task_", "")
        self._launch_worker_process(specific_task_id=task_id)

    def _open_direct_agy_shell(self) -> None:
        """فتح نافذة طرفية تفاعلية حرة لـ agy في مجلد المشروع."""
        proj_path, _ = self._resolve_paths()
        if not proj_path or not proj_path.is_dir():
            messagebox.showerror("خطأ", "يرجى تحديد مجلد مشروع صالح أولاً.")
            return

        session_id = self.session_id_var.get().strip()
        raw_model = self.model_var.get().strip() or DEFAULT_MODEL
        raw_effort = self.effort_var.get().strip() or "medium"
        resolved_model, _ = resolve_agy_model_and_effort(raw_model, raw_effort)
        mode = self.mode_var.get().strip() or "accept-edits"
        agy_executable = shutil.which("agy") or "agy"
        session_exists = bool(session_id and session_id != "new" and (get_agy_brain_dir() / session_id).is_dir())

        try:
            if sys.platform == "win32":
                win_title = f"Antigravity Interactive Shell [{session_id or 'new'}]"
                conv_arg = f"--conversation {session_id} " if session_exists else ""
                perm_arg = " --dangerously-skip-permissions" if self.skip_permissions_var.get() else ""
                inner_cmd = (
                    f'chcp 65001 >nul && "{agy_executable}" {conv_arg}'
                    f'--add-dir "{proj_path}" --model {resolved_model} --mode {mode}{perm_arg}'
                )
                spawn_cmd = f'start "{win_title}" cmd.exe /k "{inner_cmd}"'
                subprocess.Popen(spawn_cmd, shell=True, cwd=str(proj_path))
            else:
                creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                cmd_list = [agy_executable]
                if session_exists:
                    cmd_list.extend(["--conversation", session_id])
                cmd_list.extend(["--add-dir", str(proj_path), "--model", resolved_model, "--mode", mode])
                if self.skip_permissions_var.get():
                    cmd_list.append("--dangerously-skip-permissions")
                subprocess.Popen(
                    cmd_list,
                    cwd=str(proj_path),
                    creationflags=creationflags
                )

            self._log_message(f"تم فتح طرفية agy تفاعلية حرة في: {proj_path}")

        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح الطرفية: {e}")
            self._log_message(f"خطأ في فتح طرفية agy: {e}")


def launch_ui() -> None:
    """نقطة الدخول الرئيسية لتشغيل واجهة المستخدم الرسومية."""
    root = tk.Tk()
    app = AntigravityTaskRunnerUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_ui()
