"""
ui.py - واجهة مستخدم رسومية احترافية مبنية بـ Tkinter لإدارة وتشغيل مهام Antigravity تفاعلياً.
"""

import os
import sys
import uuid
import subprocess
from pathlib import Path
from typing import Optional, List

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .parser import clean_to_absolute_path, parse_tasks_file, Task
from .runner import DEFAULT_MODEL


class AntigravityTaskRunnerUI:
    """فئة الواجهة الرسومية الرئيسية لـ Antigravity Task Runner."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Antigravity Task Runner - مُشغّل المهام التفاعلي (agy -i)")
        self.root.geometry("900x720")
        self.root.minsize(800, 620)

        # المتغيرات المرتبطة بعناصر التحكم
        self.project_dir_var = tk.StringVar(value=os.getcwd())
        self.tasks_file_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.mode_var = tk.StringVar(value="accept-edits")
        self.effort_var = tk.StringVar(value="from-task")
        self.session_id_var = tk.StringVar(value=f"agy-session-{uuid.uuid4().hex[:10]}")
        self.skip_permissions_var = tk.BooleanVar(value=True)
        self.auto_next_var = tk.BooleanVar(value=True)
        self.exec_engine_var = tk.StringVar(value="agy-i")
        self.status_summary_var = tk.StringVar(value="جاري فحص ملف المهام...")

        self.last_tasks_mtime: float = 0.0
        self.pending_tasks: List[Task] = []
        self.completed_task_ids: List[str] = []

        # محاولة البحث عن TASKS.md في المجلد الحالي افتراضياً
        default_tasks = Path(self.project_dir_var.get()) / "TASKS.md"
        if default_tasks.is_file():
            self.tasks_file_var.set(str(default_tasks))
        else:
            self.tasks_file_var.set("TASKS.md")

        self._configure_styles()
        self._build_ui()
        self._reload_tasks()

        # بدء عملية الاستطلاع الدوري لتحديث حالة المهام تلقائياً عند تعديل الملف
        self.root.after(2000, self._auto_poll_tasks)

    def _configure_styles(self) -> None:
        """تهيئة المظهر والأنماط البصرية باستخدام ttk.Style."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # تخصيص الألوان العامة
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

        # تخصيص الجدول Treeview
        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=26,
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
            text="⚡ Antigravity Task Runner - مُشغّل المهام التفاعلي",
            font=("Segoe UI", 14, "bold"),
            bg="#f8fafc",
            fg="#0f172a"
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="تشغيل مهام Markdown تسلسلياً والمشاهدة الحية عبر واجهة agy -i التفاعلية",
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
            values=["gemini-3.8-flash", "gemini-3.8-pro", "claude-3-7-sonnet", "claude-3-5-sonnet", "gpt-4o"],
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

        # السطر الثاني: معرف الجلسة
        ttk.Label(settings_frame, text="معرف الجلسة:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        session_frame = ttk.Frame(settings_frame)
        session_frame.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4)
        session_frame.columnconfigure(0, weight=1)
        ttk.Entry(session_frame, textvariable=self.session_id_var, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(session_frame, text="🔄 جديد", command=self._generate_new_session, style="Secondary.TButton").grid(row=0, column=1)

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

        # السطر الثالث: خيارات التأكيد وتخطي الأذونات
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
        tasks_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # جدول Treeview مع شريط تمرير
        table_container = ttk.Frame(tasks_group)
        table_container.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "effort", "status", "preview")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="المهمة (#)")
        self.tree.heading("effort", text="الجهد")
        self.tree.heading("status", text="الحالة")
        self.tree.heading("preview", text="معاينة محتوى المهمة")

        self.tree.column("id", width=80, anchor="center")
        self.tree.column("effort", width=100, anchor="center")
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("preview", width=520, anchor="w")

        # تنسيق ألوان أسطر المهام المكتملة والمعلقة
        self.tree.tag_configure("completed", foreground="#16a34a")
        self.tree.tag_configure("pending", foreground="#1e293b")

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

        # 5. شريط الأزرار الرئيسية (Action Buttons)
        actions_frame = ttk.Frame(main_container)
        actions_frame.pack(fill=tk.X, pady=(4, 0))

        # الزر الرئيسي: تشغيل حي في agy -i
        run_all_btn = ttk.Button(
            actions_frame,
            text="▶ بدء تشغيل المهام التفاعلية (agy -i)",
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

    def _browse_project_dir(self) -> None:
        """اختيار مجلد المشروع عبر نافذة التصفح."""
        chosen = filedialog.askdirectory(
            initialdir=self.project_dir_var.get() or os.getcwd(),
            title="اختر مجلد المشروع"
        )
        if chosen:
            self.project_dir_var.set(chosen)
            # فحص تلقائي لملف TASKS.md داخل المجلد الجديد
            candidate = Path(chosen) / "TASKS.md"
            if candidate.is_file():
                self.tasks_file_var.set(str(candidate))
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

    def _generate_new_session(self) -> None:
        """توليد معرف جلسة فريد جديد."""
        new_session = f"agy-session-{uuid.uuid4().hex[:10]}"
        self.session_id_var.set(new_session)

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
                preview = first_line[:90] + ("..." if len(first_line) > 90 else "")
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
            self.status_summary_var.set(
                f"📊 إجمالي المهام: {total}  |  ⏳ قيد الانتظار: {len(pending)}  |  ✔ مكتملة: {len(skipped)}"
            )

        except Exception as err:
            self.status_summary_var.set(f"❌ خطأ أثناء تحليل ملف المهام: {err}")

    def _auto_poll_tasks(self) -> None:
        """استطلاع دوري للملف لتحديث الجدول تلقائياً إذا تغير الملف في الخلفية."""
        _, tasks_path = self._resolve_paths()
        if tasks_path and tasks_path.is_file():
            try:
                current_mtime = tasks_path.stat().st_mtime
                if current_mtime != self.last_tasks_mtime:
                    self._reload_tasks()
            except Exception:
                pass

        self.root.after(2000, self._auto_poll_tasks)

    def _launch_worker_process(self, specific_task_id: Optional[str] = None) -> None:
        """إطلاق معالج المهام التفاعلي في نافذة طرفية مستقلة لعرض agy -i حياً."""
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
        engine = self.exec_engine_var.get()

        # بناء أمر إطلاق العامل التفاعلي
        cmd = [
            sys.executable,
            "-m", "agytask.interactive_worker",
            "--project-dir", str(proj_path),
            "--tasks-file", str(tasks_path),
            "--session", session_id,
            "--model", model,
            "--mode", mode,
            "--effort", effort,
        ]

        if skip_perm:
            cmd.append("--dangerously-skip-permissions")

        if not auto_next:
            cmd.append("--no-auto-next")

        if specific_task_id:
            cmd.extend(["--task-id", str(specific_task_id)])

        # إطلاق نافذة طرفية جديدة حية ومستقلة على نظام ويندوز
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

        try:
            subprocess.Popen(
                cmd,
                cwd=str(proj_path),
                creationflags=creationflags
            )
            target_desc = f"المهمة #{specific_task_id}" if specific_task_id else "جميع المهام المعلقة"
            self.status_summary_var.set(f"🚀 تم إطلاق نافذة الطرفية الحية لـ {target_desc} عبر agy -i.")
        except Exception as e:
            messagebox.showerror("فشل التشغيل", f"تعذر إطلاق نافذة الطرفية:\n{e}")

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
        # استخراج رقم المهمة من المعرف الداخلي task_123
        task_id = item_id.replace("task_", "")
        self._launch_worker_process(specific_task_id=task_id)

    def _open_direct_agy_shell(self) -> None:
        """فتح نافذة طرفية تفاعلية حرة لـ agy في مجلد المشروع."""
        proj_path, _ = self._resolve_paths()
        if not proj_path or not proj_path.is_dir():
            messagebox.showerror("خطأ", "يرجى تحديد مجلد مشروع صالح أولاً.")
            return

        session_id = self.session_id_var.get().strip() or f"agy-session-{uuid.uuid4().hex[:10]}"
        model = self.model_var.get().strip() or DEFAULT_MODEL

        # تشغيل طرفية cmd مع تجهيز الأمر
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            subprocess.Popen(
                ["cmd.exe", "/k", f"chcp 65001 >nul && agy --conversation {session_id} --add-dir \"{proj_path}\" --model {model}"],
                cwd=str(proj_path),
                creationflags=creationflags
            )
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح الطرفية: {e}")


def launch_ui() -> None:
    """نقطة الدخول الرئيسية لتشغيل واجهة المستخدم الرسومية."""
    root = tk.Tk()
    app = AntigravityTaskRunnerUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_ui()
