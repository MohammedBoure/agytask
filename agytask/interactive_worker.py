"""
interactive_worker.py - تشغيل مهام Antigravity تسلسلياً داخل جلسة agy التفاعلية الحية.

يقوم هذا السكربت بفتح واجهة agy التفاعلية (TUI) في الجلسة المحددة دون استخدام الراية (-i)
التي كانت تتسبب في إنشاء جلسة جديدة، ثم يقوم خيط تحكم خلفي (Orchestrator Thread) بضخ
المهام واحدة تلو الأخرى مباشرة داخل حقل الإدخال الحي عبر WriteConsoleInputW، ومراقبة
ملف سجل المحادثة (transcript.jsonl) لاكتشاف انتهاء كل مهمة تلقائياً، وتحديث ملف المهام
بوسم [COMPLETED]، وإرسال المهمة التالية تلقائياً في نفس الجلسة دون توقف.
"""

import os
import re
import sys
import json
import time
import uuid
import shutil
import ctypes
import tempfile
import argparse
import threading
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Optional, List, Tuple

# ضمان تواجد مجلد الحزمة في sys.path حتى لو تم التشغيل من مجلد عمل خارجي (مثل StockLamPlus)
_current_dir = Path(__file__).resolve().parent
_repo_root = _current_dir.parent
for _p in (str(_repo_root), str(_current_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from agytask.parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task
except (ImportError, ModuleNotFoundError):
    try:
        from parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task
    except (ImportError, ModuleNotFoundError):
        from .parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task


# نماذج agy التي تستخدم لاحقة الجهد (-low / -medium / -high) بدلاً من راية --effort المنفصلة
TIERED_MODEL_BASES = (
    "gemini-3.8-flash",
    "gemini-4-argon",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
)


def set_console_title(title: str) -> None:
    """تعيين عنوان نافذة الطرفية بشكل آمن في ويندوز."""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def get_agy_brain_dir() -> Path:
    """الحصول على مسار مجلد المحادثات (brain) الخاص بـ Antigravity CLI."""
    return Path.home() / ".gemini" / "antigravity-cli" / "brain"


def resolve_agy_model_and_effort(model: str, effort: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    مواءمة اسم النموذج ومستوى الجهد مع متطلبات agy CLI.
    النماذج القياسية في agy مثل gemini-3.8-flash لا تقبل الراية --effort منفصلة،
    بل تتطلب تمرير الاسم المدمج مثل gemini-3.8-flash-medium أو gemini-3.8-flash-high.
    """
    clean_model = (model or "gemini-3.8-flash").strip()
    eff = (effort or "medium").strip().lower()
    if eff in ("from-task", ""):
        eff = "medium"
    if eff in ("xhigh", "max"):
        eff_tier = "high"
    elif eff in ("low", "medium", "high"):
        eff_tier = eff
    else:
        eff_tier = "medium"

    # إذا كان النموذج من عائلة النماذج متعددة المستويات (أو ينتهي بـ -low/-medium/-high)
    for base in TIERED_MODEL_BASES:
        if clean_model == base or clean_model.startswith(f"{base}-"):
            # إذا حدد المستخدم نموذجاً بلاحقة صريحة ولم يطلب تجاوز الجهد، نحترم اللاحقة أو ندمج الجهد
            if clean_model == base:
                return f"{base}-{eff_tier}", None
            else:
                return clean_model, None

    if clean_model == "gpt-oss-120b":
        return "gpt-oss-120b-medium", None
    if clean_model == "gpt-oss-120b-medium":
        return clean_model, None

    return clean_model, None


# ==============================================================================
# حقن الإدخال المباشر في طرفية ويندوز (Windows Console Input Injection)
# ==============================================================================

if sys.platform == "win32":
    KEY_EVENT = 0x0001
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3

    class CHAR_UNION(ctypes.Union):
        _fields_ = [
            ("UnicodeChar", wintypes.WCHAR),
            ("AsciiChar", ctypes.c_char),
        ]

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", CHAR_UNION),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class EVENT_UNION(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [
            ("EventType", wintypes.WORD),
            ("Event", EVENT_UNION),
        ]


def _make_key_record(ch: str, key_down: bool, vk: int = 0, scan: int = 0) -> "INPUT_RECORD":
    """إنشاء سجل حدث ضغطة مفتاح لويندوز."""
    rec = INPUT_RECORD()
    rec.EventType = KEY_EVENT
    rec.Event.KeyEvent.bKeyDown = 1 if key_down else 0
    rec.Event.KeyEvent.wRepeatCount = 1
    rec.Event.KeyEvent.wVirtualKeyCode = vk
    rec.Event.KeyEvent.wVirtualScanCode = scan
    rec.Event.KeyEvent.uChar.UnicodeChar = ch
    rec.Event.KeyEvent.dwControlKeyState = 0
    return rec


def send_console_key_enter() -> bool:
    """إرسال ضغطة مفتاح Enter (VK_RETURN) إلى حقل الإدخال في الطرفية التفاعلية."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        h_conin = kernel32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_conin in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return False
        try:
            records = [
                _make_key_record("\r", True, vk=0x0D, scan=0x1C),
                _make_key_record("\r", False, vk=0x0D, scan=0x1C),
            ]
            arr = (INPUT_RECORD * len(records))(*records)
            written = wintypes.DWORD(0)
            kernel32.WriteConsoleInputW(h_conin, ctypes.byref(arr), len(records), ctypes.byref(written))
            return written.value > 0
        finally:
            kernel32.CloseHandle(h_conin)
    except Exception:
        return False


def send_console_text(text: str, press_enter: bool = True) -> bool:
    """
    كتابة نص كامل (مع دعم العربية واليونيكود) مباشرة داخل حقل إدخال واجهة agy التفاعلية
    على دفعات متوازنة تمنع فقدان أي حرف في BubbleTea TUI، ثم ضغط مفتاح Enter لإرساله.
    """
    if sys.platform != "win32":
        return False

    try:
        kernel32 = ctypes.windll.kernel32
        h_conin = kernel32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_conin in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return False

        try:
            # إرسال النص على دفعات صغيرة (48 حرفاً في كل دفعة) لضمان استيعاب كامل في واجهة TUI
            chunk_size = 48
            for i in range(0, len(text), chunk_size):
                chunk = text[i : i + chunk_size]
                records = []
                for ch in chunk:
                    records.append(_make_key_record(ch, True, vk=0, scan=0))
                    records.append(_make_key_record(ch, False, vk=0, scan=0))
                arr = (INPUT_RECORD * len(records))(*records)
                written = wintypes.DWORD(0)
                kernel32.WriteConsoleInputW(h_conin, ctypes.byref(arr), len(records), ctypes.byref(written))
                time.sleep(0.015)

            if press_enter:
                time.sleep(0.25)
                enter_records = [
                    _make_key_record("\r", True, vk=0x0D, scan=0x1C),
                    _make_key_record("\r", False, vk=0x0D, scan=0x1C),
                ]
                arr_enter = (INPUT_RECORD * len(enter_records))(*enter_records)
                written = wintypes.DWORD(0)
                kernel32.WriteConsoleInputW(h_conin, ctypes.byref(arr_enter), len(enter_records), ctypes.byref(written))

            return True
        finally:
            kernel32.CloseHandle(h_conin)
    except Exception:
        return False


def build_single_line_task_prompt(task: Task, project_dir: Path, tasks_file_path: Path) -> str:
    """
    بناء نص المهمة في سطر واحد متكامل لإدخاله في مربع نص agy التفاعلي دون أن يؤدي وجود
    سطر جديد (Newline) إلى إرسال مبكر للرسالة قبل اكتمال نصها.
    """
    task_id = task["id"]
    raw_lines = [line.strip() for line in task["content"].splitlines() if line.strip()]
    compact_body = " | ".join(raw_lines)

    prompt = (
        f"[Task #{task_id}] Project Root: {project_dir} | Tasks File: {tasks_file_path} | "
        f"Execute Task #{task_id}: {compact_body} | "
        f"Requirements: 1. Read relevant README.md and docs if referenced. "
        f"2. Apply the requested code modifications cleanly. "
        f"3. Update Task #{task_id} header in {tasks_file_path.name} to [COMPLETED]. "
        f"4. Commit changes with Conventional Commits and provide a concise summary in Arabic."
    )
    return prompt


# ==============================================================================
# مراقبة جاهزية agy واكتمال المهام عبر ملفات السجل و transcript.jsonl
# ==============================================================================

def get_transcript_path(conv_id: str) -> Path:
    """إرجاع مسار ملف transcript.jsonl الخاص بالجلسة."""
    return get_agy_brain_dir() / conv_id / ".system_generated" / "logs" / "transcript.jsonl"


def read_transcript_steps(transcript_path: Path) -> List[dict]:
    """قراءة كافة خطوات transcript.jsonl بأمان."""
    if not transcript_path.is_file():
        return []
    steps: List[dict] = []
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return steps


def is_turn_complete(new_steps: List[dict]) -> bool:
    """
    التحقق مما إذا كان الوكيل قد أنهى تنفيذ المهمة الحالية بالكامل:
    1. وجود خطوة USER_INPUT جديدة تمثل المهمة المرسلة.
    2. عدم وجود أمر خلفي (RUNNING) لم ترد له رسالة SYSTEM_MESSAGE بانتهائه بعد.
    3. أن تكون آخر خطوة في السجل من نوع PLANNER_RESPONSE وبحالة DONE وبدون استدعاءات أدوات (tool_calls).
    """
    if not new_steps:
        return False

    last_user_idx = -1
    for i, step in enumerate(new_steps):
        if step.get("type") == "USER_INPUT":
            last_user_idx = i

    if last_user_idx == -1:
        return False

    turn_steps = new_steps[last_user_idx + 1 :]
    if not turn_steps:
        return False

    # التحقق من عدم وجود مهمة خلفية جارية لم تنتهِ بعد
    for i, step in enumerate(turn_steps):
        if step.get("status") == "RUNNING":
            # يجب أن توجد خطوة SYSTEM_MESSAGE لاحقة تؤكد انتهاء المهمة الخلفية
            has_completion_msg = any(
                s.get("type") == "SYSTEM_MESSAGE" for s in turn_steps[i + 1 :]
            )
            if not has_completion_msg:
                return False

    last_step = turn_steps[-1]
    if (
        last_step.get("type") == "PLANNER_RESPONSE"
        and last_step.get("status") == "DONE"
        and not last_step.get("tool_calls")
        and bool(str(last_step.get("content", "")).strip())
    ):
        return True

    return False


def detect_active_conversation_from_log(log_file: Path, fallback_conv_id: Optional[str] = None) -> Optional[str]:
    """استخراج معرف المحادثة الفعلي النشط من ملف سجل agy."""
    if not log_file.is_file():
        return fallback_conv_id
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
        # الأولوية لآخر رسالة تم توجيهها للمحادثة
        m_fwd = re.findall(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})", text)
        if m_fwd:
            return m_fwd[-1]
        m_created = re.findall(r"Created conversation ([0-9a-fA-F-]{36})", text)
        if m_created:
            return m_created[-1]
        m_resumed = re.findall(r"Resuming conversation ([0-9a-fA-F-]{36})", text)
        if m_resumed:
            return m_resumed[-1]
    except Exception:
        pass
    return fallback_conv_id


def wait_for_agy_ready(log_file: Path, proc: subprocess.Popen, timeout: float = 35.0) -> bool:
    """
    الانتظار حتى تكتمل تهيئة واجهة agy التفاعلية وتسجيل الدخول الصامت وتحديث التجارب،
    لضمان عدم ضياع النص المحقون أو إعادة تعيين المحادثة.
    """
    start = time.time()
    ready_input_seen_at: Optional[float] = None

    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False

        if log_file.is_file():
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
                if "Experiments refreshed after login" in text or "Timed out waiting for experiments" in text:
                    time.sleep(1.0)
                    return True
                if "CLI ready for user input" in text:
                    if ready_input_seen_at is None:
                        ready_input_seen_at = time.time()
                    elif time.time() - ready_input_seen_at >= 6.0:
                        return True
            except Exception:
                pass

        time.sleep(0.25)

    return proc.poll() is None


def orchestrate_tasks_in_live_session(
    proc: subprocess.Popen,
    target_tasks: List[Task],
    project_dir: Path,
    tasks_file: Path,
    initial_conv_id: Optional[str],
    log_file: Path,
    auto_next_delay: float = 3.5,
) -> None:
    """
    خيط التحكم الخلفي الذي يرسل المهام تباعاً إلى جلسة agy التفاعلية المفتوحة،
    ويراقب إنجاز كل مهمة عبر transcript.jsonl ليحدث ملف المهام ويرسل المهمة التالية تلقائياً.
    """
    if not wait_for_agy_ready(log_file, proc):
        return

    active_conv_id = detect_active_conversation_from_log(log_file, initial_conv_id)

    for idx, task in enumerate(target_tasks):
        if proc.poll() is not None:
            return

        task_id = task["id"]
        total = len(target_tasks)
        conv_label = active_conv_id or "New-Session"
        set_console_title(
            f"Antigravity Live Runner [Session: {conv_label}] - جاري تنفيذ المهمة #{task_id} ({idx + 1}/{total})"
        )

        # حساب عدد الخطوات الحالية في transcript.jsonl قبل إرسال المهمة
        baseline_steps_count = 0
        if active_conv_id:
            t_path = get_transcript_path(active_conv_id)
            baseline_steps_count = len(read_transcript_steps(t_path))

        log_size_before = log_file.stat().st_size if log_file.is_file() else 0

        # بناء نص المهمة وإرساله مباشرة في حقل الإدخال الحي
        prompt_text = build_single_line_task_prompt(task, project_dir, tasks_file)
        send_console_text(prompt_text, press_enter=True)

        # التحقق من استلام agy للرسالة وتحديد معرف المحادثة الفعلي
        submitted = False
        wait_submit_start = time.time()
        while time.time() - wait_submit_start < 9.0:
            if proc.poll() is not None:
                return
            if log_file.is_file():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
                        lf.seek(log_size_before)
                        recent_log = lf.read()
                    m_fwd = re.findall(r"Forwarding user message to conversation ([0-9a-fA-F-]{36})", recent_log)
                    if m_fwd:
                        new_conv = m_fwd[-1]
                        if new_conv != active_conv_id:
                            active_conv_id = new_conv
                            # إذا كانت محادثة جديدة، نضبط خط الأساس على 0 لتتبع أول USER_INPUT فيها
                            baseline_steps_count = 0
                        submitted = True
                        break
                except Exception:
                    pass

            if active_conv_id:
                curr_steps = read_transcript_steps(get_transcript_path(active_conv_id))
                if any(s.get("type") == "USER_INPUT" for s in curr_steps[baseline_steps_count:]):
                    submitted = True
                    break

            time.sleep(0.3)

        # إذا لم يتم إرسال الرسالة بعد (مثلاً بسبب قائمة إكمال تلقائي)، نرسل ضغطة Enter إضافية
        if not submitted and proc.poll() is None:
            send_console_key_enter()
            time.sleep(1.5)
            active_conv_id = detect_active_conversation_from_log(log_file, active_conv_id)

        # مراقبة transcript.jsonl حتى تنتهي المهمة الحالية بالكامل
        quiescent_since: Optional[float] = None
        last_file_size = -1

        while proc.poll() is None:
            if not active_conv_id:
                active_conv_id = detect_active_conversation_from_log(log_file, active_conv_id)
                if not active_conv_id:
                    time.sleep(1.0)
                    continue

            t_path = get_transcript_path(active_conv_id)
            if not t_path.is_file():
                time.sleep(1.0)
                continue

            try:
                curr_size = t_path.stat().st_size
            except Exception:
                curr_size = -1

            all_steps = read_transcript_steps(t_path)
            new_steps = all_steps[baseline_steps_count:]

            if is_turn_complete(new_steps):
                if curr_size == last_file_size and curr_size > 0:
                    if quiescent_since is None:
                        quiescent_since = time.time()
                    elif time.time() - quiescent_since >= 4.0:
                        # اكتملت المهمة رسمياً واستقر سجل المحادثة!
                        break
                else:
                    last_file_size = curr_size
                    quiescent_since = time.time()
            else:
                quiescent_since = None
                last_file_size = curr_size

            time.sleep(1.0)

        if proc.poll() is not None:
            return

        # تحديث حالة المهمة في ملف المهام إلى [COMPLETED]
        try:
            mark_task_as_completed(tasks_file, task_id)
        except Exception:
            pass

        # إذا كانت هناك مهمة تالية، ننتظر مهلة قصيرة ثم نضخها تلقائياً في نفس الجلسة
        if idx < total - 1:
            next_id = target_tasks[idx + 1]["id"]
            for remaining in range(int(auto_next_delay), 0, -1):
                if proc.poll() is not None:
                    return
                set_console_title(
                    f"Antigravity Live Runner [✔ اكتملت #{task_id}] - إرسال المهمة #{next_id} خلال {remaining} ث..."
                )
                time.sleep(1.0)
        else:
            set_console_title(
                f"Antigravity Live Runner [Session: {active_conv_id}] - ✔ اكتملت جميع المهام ({total}/{total}) بنجاح!"
            )


def run_interactive_pipeline(
    project_dir_raw: str,
    tasks_file_raw: str,
    session_id: str,
    model: str = "gemini-3.8-flash",
    mode: str = "accept-edits",
    effort: str = "from-task",
    dangerously_skip_permissions: bool = True,
    task_id: Optional[str] = None,
    no_auto_next: bool = False,
    pause_at_end: bool = True,
) -> int:
    """
    تشغيل خط معالجة المهام تسلسلياً داخل جلسة agy التفاعلية الحية في نفس المحادثة.
    """
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    project_dir = clean_to_absolute_path(project_dir_raw)
    tasks_file = clean_to_absolute_path(tasks_file_raw)

    set_console_title(f"Antigravity Live Runner [Session: {session_id}]")

    print("=" * 78)
    print("        ANTIGRAVITY TASK RUNNER - المشغّل التفاعلي المباشر (Live TUI)        ")
    print("=" * 78)
    print(f"المشروع     : {project_dir}")
    print(f"ملف المهام  : {tasks_file}")
    print(f"الجلسة      : {session_id}")
    print(f"النموذج     : {model} | وضع الوكيل: {mode}")
    print("=" * 78)

    if not project_dir.is_dir():
        print(f"[✘] خطأ: مجلد المشروع غير موجود: {project_dir}")
        if pause_at_end:
            input("\nاضغط Enter للإغلاق...")
        return 1

    if not tasks_file.is_file():
        print(f"[✘] خطأ: ملف المهام غير موجود: {tasks_file}")
        if pause_at_end:
            input("\nاضغط Enter للإغلاق...")
        return 1

    try:
        all_pending_tasks, skipped_ids = parse_tasks_file(tasks_file)
    except Exception as e:
        print(f"[✘] خطأ في قراءة ملف المهام: {e}")
        if pause_at_end:
            input("\nاضغط Enter للإغلاق...")
        return 1

    # تحديد المهام المراد تنفيذها
    target_tasks: List[Task] = []
    if task_id:
        found = [t for t in all_pending_tasks if str(t["id"]) == str(task_id)]
        if not found:
            with open(tasks_file, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.search(
                rf"^#\s*{re.escape(str(task_id))}(?:[ \t]+\[[^\]]+\])?(?:\s*:\s*([a-zA-Z]+))?.*?\n(.*?)(?=\n#|\Z)",
                content,
                flags=re.MULTILINE | re.DOTALL,
            )
            if m:
                target_tasks = [
                    {
                        "id": str(task_id),
                        "effort": (m.group(1) or "medium").lower(),
                        "content": m.group(2).strip(),
                    }
                ]
            else:
                print(f"[✘] لم يتم العثور على المهمة رقم #{task_id} في الملف.")
                if pause_at_end:
                    input("\nاضغط Enter للإغلاق...")
                return 1
        else:
            target_tasks = found
    else:
        target_tasks = all_pending_tasks

    if not target_tasks:
        print("\n[i] لا توجد مهام معلقة للتنفيذ! جميع المهام مكتملة مسبقاً.")
        if pause_at_end:
            input("\nاضغط Enter للإغلاق...")
        return 0

    print(f"\n[+] تم تجهيز {len(target_tasks)} مهمة لإرسالها تسلسلياً في نفس جلسة agy الحية:")
    for t in target_tasks:
        print(f"    - المهمة #{t['id']:<4} | الجهد: {t['effort'].upper():<8}")

    # مواءمة النموذج ومستوى الجهد لأول مهمة
    first_effort = effort if (effort and effort != "from-task") else target_tasks[0]["effort"]
    resolved_model, resolved_effort_flag = resolve_agy_model_and_effort(model, first_effort)

    # التحقق مما إذا كان معرف الجلسة موجوداً فعلياً في مجلد brain لاستئنافه بدقة
    clean_session = (session_id or "").strip()
    brain_dir = get_agy_brain_dir()
    session_exists_in_brain = bool(clean_session and (brain_dir / clean_session).is_dir())

    agy_executable = shutil.which("agy") or "agy"
    temp_log_file = Path(tempfile.gettempdir()) / f"agytask_live_{uuid.uuid4().hex[:8]}.log"

    # ملاحظة جوهرية: لا نمرر الراية (-i) هنا لأن (-i) تجبر agy على إنشاء محادثة جديدة
    # وتجاهل (--conversation). بدلاً من ذلك نفتحه مباشرة ونضخ المهام عبر CONIN$.
    cmd = [
        agy_executable,
        "--add-dir", str(project_dir),
        "--model", resolved_model,
        "--mode", mode,
        "--log-file", str(temp_log_file),
    ]

    if session_exists_in_brain:
        cmd.extend(["--conversation", clean_session])
        print(f"[+] سيتم استئناف الجلسة المحددة مباشرة: {clean_session}")
    else:
        print(f"[i] الجلسة ({clean_session}) غير موجودة مسبقاً في سجل agy؛ سيتم بدء جلسة حية موحدة لجميع المهام.")

    if resolved_effort_flag:
        cmd.extend(["--effort", resolved_effort_flag])

    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    print(f"[+] النموذج النشط: {resolved_model} | الوضع: {mode}")
    print("[+] جاري فتح واجهة agy الحية وإرسال المهام تلقائياً الواحدة تلو الأخرى...\n")
    time.sleep(0.6)

    try:
        proc = subprocess.Popen(cmd, cwd=str(project_dir))

        orchestrator = threading.Thread(
            target=orchestrate_tasks_in_live_session,
            args=(
                proc,
                target_tasks,
                project_dir,
                tasks_file,
                clean_session if session_exists_in_brain else None,
                temp_log_file,
                4.0 if not no_auto_next else 8.0,
            ),
            daemon=True,
        )
        orchestrator.start()

        return_code = proc.wait()
        return return_code

    except KeyboardInterrupt:
        print("\n\n[!] تم إيقاف جلسة agy بواسطة المستخدم (Ctrl+C).")
        return 130
    except FileNotFoundError:
        print("\n[✘] خطأ: لم يتم العثور على أداة agy في النظام! يرجى التأكد من تثبيتها وإضافتها للمسار PATH.")
        if pause_at_end:
            input("\nاضغط Enter للإغلاق...")
        return 127
    finally:
        try:
            if temp_log_file.is_file():
                temp_log_file.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="مشغّل مهام Antigravity التفاعلي الحي")
    parser.add_argument("--project-dir", required=True, help="مسار مجلد المشروع")
    parser.add_argument("--tasks-file", required=True, help="مسار ملف المهام Markdown")
    parser.add_argument("--session", required=True, help="معرف الجلسة Conversation ID")
    parser.add_argument("--model", default="gemini-3.8-flash", help="اسم النموذج")
    parser.add_argument("--mode", default="accept-edits", help="وضع التنفيذ لـ agy")
    parser.add_argument("--effort", default="from-task", help="جهد التفكير Override أو from-task")
    parser.add_argument("--dangerously-skip-permissions", action="store_true", default=True, help="تخطي الأذونات تلقائياً")
    parser.add_argument("--task-id", default=None, help="تنفيذ مهمة محددة فقط برقمها")
    parser.add_argument("--no-auto-next", action="store_true", help="إلغاء المتابعة التلقائية وانتظار تأكيد يدوي")

    args = parser.parse_args()

    exit_code = run_interactive_pipeline(
        project_dir_raw=args.project_dir,
        tasks_file_raw=args.tasks_file,
        session_id=args.session,
        model=args.model,
        mode=args.mode,
        effort=args.effort,
        dangerously_skip_permissions=args.dangerously_skip_permissions,
        task_id=args.task_id,
        no_auto_next=args.no_auto_next,
        pause_at_end=True,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
