"""
interactive_worker.py - تشغيل مهام Antigravity تسلسلياً عبر agy -i في نافذة تفاعلية حية.
"""

import os
import sys
import time
import shutil
import argparse
import ctypes
from pathlib import Path
from typing import Optional, List

from .parser import clean_to_absolute_path, parse_tasks_file, mark_task_as_completed, Task

# دعم قراءة ضغطة المفتاح مع مهلة زمنية في نظام ويندوز
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


def set_console_title(title: str) -> None:
    """تعيين عنوان نافذة الطرفية بشكل آمن في ويندوز."""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def timed_prompt(prompt_text: str, timeout_seconds: int = 4) -> str:
    """
    عرض رسالة انتظار مع عد تنازلي؛ إذا ضغط المستخدم على مفتاح يتم استقباله،
    وإذا انتهت المهلة يتم استئناف العمل تلقائياً بالقيمة الافتراضية.
    """
    if not HAS_MSVCRT:
        try:
            return input(f"{prompt_text} (Enter للمتابعة): ").strip()
        except EOFError:
            return ""

    print(f"{prompt_text} [متابعة تلقائية بعد {timeout_seconds} ثوانٍ - اضغط Enter للمتابعة أو q للإيقاف]: ", end="", flush=True)

    start_time = time.time()
    collected = []

    while time.time() - start_time < timeout_seconds:
        if msvcrt.kbhit():
            ch = msvcrt.getwche()
            if ch in ("\r", "\n"):
                print()
                return "".join(collected).strip()
            elif ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            elif ch == "\x08":  # Backspace
                if collected:
                    collected.pop()
            else:
                collected.append(ch)
        time.sleep(0.05)

    print("\n[i] انتهت المهلة، جاري المتابعة تلقائياً...")
    return "".join(collected).strip()


def run_interactive_task(
    task: Task,
    project_dir: Path,
    tasks_file_path: Path,
    session_id: str,
    model: str,
    mode: str,
    effort_override: Optional[str],
    dangerously_skip_permissions: bool = True
) -> int:
    """
    تنفيذ مهمة واحدة عبر الدخول المباشر إلى واجهة agy -i.
    """
    import subprocess

    task_id = task["id"]
    task_effort = effort_override if (effort_override and effort_override != "from-task") else task["effort"]
    task_body = task["content"]

    prompt = f"""Project Root: {project_dir}
Tasks Source File: {tasks_file_path}

Executing Task #{task_id}:
--------------------------------------------------
{task_body}
--------------------------------------------------

Requirements:
1. Check docs/ and assets/ if referenced in the task description.
2. Apply code modifications directly to target files.
3. Ensure exact requirements (diacritics, conditions, layout) are satisfied.
4. Provide a brief summary of completed changes.
"""

    agy_executable = shutil.which("agy") or "agy"

    cmd = [
        agy_executable,
        "-i", prompt,
        "--conversation", session_id,
        "--add-dir", str(project_dir),
        "--model", model,
        "--mode", mode,
    ]

    if task_effort:
        cmd.extend(["--effort", task_effort])

    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    print("\n" + "=" * 78)
    print(f"[*] تشغيل المهمة #{task_id} عبر [agy -i] | الجهد: [{task_effort.upper()}]")
    print(f"[*] الجلسة: [{session_id}] | النموذج: [{model}] | الوضع: [{mode}]")
    print(f"[*] المسار التنفيذي لـ agy: {agy_executable}")
    print("=" * 78 + "\n")

    # تشغيل الأمر مباشرة بحيث يرث stdio الخاص بالطرفية لتمكين واجهة agy التفاعلية بالكامل
    try:
        proc = subprocess.run(cmd, cwd=str(project_dir))
        return proc.returncode
    except KeyboardInterrupt:
        print("\n\n[!] تم إيقاف تنفيذ المهمة بواسطة المستخدم (Ctrl+C).")
        raise
    except FileNotFoundError:
        print(f"\n[✘] خطأ: لم يتم العثور على أداة agy في النظام! يرجى التأكد من تثبيتها وإضافتها للمسار PATH.")
        return 127


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
    pause_at_end: bool = True
) -> int:
    """
    تشغيل خط معالجة المهام تسلسلياً عبر agy -i في الطرفية التفاعلية الحالية.
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
    print("        ANTIGRAVITY TASK RUNNER - الوضع التفاعلي المباشر (agy -i)        ")
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
            import re
            m = re.search(rf"^#\s*{re.escape(str(task_id))}(?:[ \t]+\[[a-zA-Z]+\])?(?:\s*:\s*([a-zA-Z]+))?.*?\n(.*?)(?=\n#|\Z)", content, flags=re.MULTILINE | re.DOTALL)
            if m:
                target_tasks = [{
                    "id": str(task_id),
                    "effort": (m.group(1) or "medium").lower(),
                    "content": m.group(2).strip()
                }]
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

    print(f"\n[+] تم تحميل {len(target_tasks)} مهمة جاهزة للتنفيذ:")
    for t in target_tasks:
        print(f"    - المهمة #{t['id']:<4} | الجهد: {t['effort'].upper():<8}")
    print()

    completed_count = 0
    failed_count = 0

    try:
        for idx, task in enumerate(target_tasks):
            return_code = run_interactive_task(
                task=task,
                project_dir=project_dir,
                tasks_file_path=tasks_file,
                session_id=session_id,
                model=model,
                mode=mode,
                effort_override=effort,
                dangerously_skip_permissions=dangerously_skip_permissions
            )

            # فحص نتيجة التنفيذ وتحديث ملف المهام
            if return_code == 0:
                mark_task_as_completed(tasks_file, task["id"])
                print(f"\n[✔] تم إكمال المهمة #{task['id']} بنجاح، وتم وسمها بـ [COMPLETED] في {tasks_file.name}.")
                completed_count += 1
            else:
                print(f"\n[!] تم إنهاء agy بكود الخروج: {return_code}.")
                choice = input(f"هل تم إنجاز المهمة #{task['id']} وتريد وسمها كمكتملة؟ (y/n) [افتراضي n]: ").strip().lower()
                if choice in ("y", "yes"):
                    mark_task_as_completed(tasks_file, task["id"])
                    print(f"[✔] تم وسم المهمة #{task['id']} كمكتملة بناءً على طلبك.")
                    completed_count += 1
                else:
                    failed_count += 1

            # في حال وجود مهام متبقية
            if idx < len(target_tasks) - 1:
                next_task = target_tasks[idx + 1]
                print("-" * 78)
                if no_auto_next:
                    user_resp = input(f"[>] اضغط Enter للانتقال للمهمة التالية #{next_task['id']} (أو اكتب 'q' للخروج): ").strip()
                else:
                    user_resp = timed_prompt(f"[>] الاستعداد للمهمة التالية #{next_task['id']}", timeout_seconds=4)

                if user_resp.lower() in ("q", "quit", "exit"):
                    print("[!] تم إيقاف التنفيذ بواسطة المستخدم.")
                    break

    except KeyboardInterrupt:
        print("\n\n[!] تم إيقاف التنفيذ بواسطة إشارة المقاطعة.")

    print("\n" + "=" * 78)
    print(f"ملخص التنفيذ: اكتملت {completed_count} مهمة | فشلت أو توقفت {failed_count} مهمة")
    print("=" * 78)
    if pause_at_end:
        input("\nاضغط Enter لإغلاق هذه النافذة...")

    return 0 if failed_count == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="مشغّل مهام Antigravity التفاعلي الحي (agy -i)")
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
        pause_at_end=True
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
