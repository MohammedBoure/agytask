"""
runner.py - دوال تشغيل أوامر subprocess والبث المباشر والتعافي التلقائي.
"""

import os
import sys
import time
import uuid
import signal
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

from .parser import Task, parse_tasks_file, mark_task_as_completed, clean_to_absolute_path

DEFAULT_MODEL = "gemini-3.8-flash"


def run_stream_command(
    cmd: List[str],
    project_dir: Union[str, Path],
    log_file: Union[str, Path],
    append: bool = False
) -> int:
    """
    تشغيل الأمر وبث المخرجات لحظياً في سطر الأوامر وحفظها في ملف السجل،
    مع التعامل الآمن مع إشارات الإيقاف والمقاطعة (SIGINT / Ctrl+C).

    Args:
        cmd: قائمة عناصر الأمر المراد تنفيذه.
        project_dir: مسار مجلد العمل للأمر.
        log_file: مسار ملف السجل لحفظ المخرجات.
        append: إذا كان True يتم الإلحاق بنهاية ملف السجل بدلاً من الكتابة من البداية.

    Returns:
        int: رمز خروج العملية (returncode).

    Raises:
        KeyboardInterrupt: في حال قام المستخدم بإيقاف العملية بواسطة Ctrl+C.
    """
    mode = "a" if append else "w"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process: Optional[subprocess.Popen] = None

    try:
        with open(log_file, mode, encoding="utf-8", errors="replace") as out_file:
            process = subprocess.Popen(
                cmd,
                cwd=str(project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env
            )

            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    out_file.write(line)
                    out_file.flush()

            process.wait()
            return process.returncode if process.returncode is not None else 0

    except KeyboardInterrupt:
        print("\n\n[!] تم استلام إشارة المقاطعة (Ctrl+C). جاري إيقاف العملية الفرعية بأمان...")
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        print("[!] تم إيقاف العملية الفرعية بنجاح.")
        raise


def execute_task(
    task: Task,
    project_dir: Union[str, Path],
    tasks_file_path: Union[str, Path],
    log_dir: Union[str, Path],
    conversation_id: str,
    model_name: str = DEFAULT_MODEL,
    max_retries: int = 2,
    interactive_on_failure: bool = True
) -> bool:
    """
    تنفيذ مهمة واحدة وإدارتها عبر CLI وتطبيق التعافي التلقائي عند الفشل.

    Args:
        task: قاموس بيانات المهمة (id, effort, content).
        project_dir: مجلد جذر المشروع.
        tasks_file_path: مسار ملف المهام لتحديثه عند الاكتمال.
        log_dir: مجلد حفظ ملفات السجل.
        conversation_id: معرف الجلسة التفاعلية.
        model_name: اسم النموذج المستخدم مع agy.
        max_retries: الحد الأقصى لمحاولات التعافي عند حدوث خطأ.
        interactive_on_failure: طلب قرار المستخدم في حال فشلت المهمة نهائياً.

    Returns:
        bool: True إذا اكتملت المهمة بنجاح، و False في حال الفشل.
    """
    task_id = task["id"]
    effort = task["effort"]
    task_body = task["content"]
    log_file = Path(log_dir) / f"task_{task_id}.log"

    prompt = f"""
Project Root: {project_dir}
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

    cmd = [
        "agy",
        "-p", prompt,
        "--conversation", conversation_id,
        "--add-dir", str(project_dir),
        "--model", model_name,
        "--effort", effort,
        "--mode", "accept-edits",
        "--dangerously-skip-permissions"
    ]

    print(f"\n{'-'*70}")
    print(f"[*] Running Task #{task_id} | Effort: [{effort.upper()}] | Session: [{conversation_id}]")
    print(f"[*] Streaming output live... (Log: {log_file})")
    print(f"{'-'*70}\n")

    start_time = time.time()
    return_code = run_stream_command(cmd, project_dir, log_file, append=False)

    # محاولات التعافي وإعادة الاستئناف في نفس الجلسة عند الفشل
    retries = 0
    while return_code != 0 and retries < max_retries:
        retries += 1
        print(f"\n[!] Task #{task_id} failed with exit code {return_code}.")
        print(f"[>] Sending resume/recovery prompt to SAME session [{conversation_id}] (Attempt {retries}/{max_retries})...\n")

        recovery_prompt = f"""
حدث انقطاع أو خطأ (رمز الخروج: {return_code}) أثناء إنجاز المهمة #{task_id}.
راجع حالة الكود الحالية وأصلح الخطأ مع إكمال باقي متطلبات المهمة السابقة دون التراجع عن التعديلات الصحيحة.
"""
        recovery_cmd = [
            "agy",
            "-p", recovery_prompt,
            "--conversation", conversation_id,
            "--add-dir", str(project_dir),
            "--model", model_name,
            "--effort", "high",
            "--mode", "accept-edits",
            "--dangerously-skip-permissions"
        ]

        return_code = run_stream_command(recovery_cmd, project_dir, log_file, append=True)

    duration = round(time.time() - start_time, 2)

    if return_code == 0:
        print(f"\n[✔] Task #{task_id} completed successfully in {duration}s.\n")
        mark_task_as_completed(tasks_file_path, task_id)
        return True
    else:
        print(f"\n[✘] Task #{task_id} failed after {max_retries} retries. See log: {log_file}\n")
        if interactive_on_failure:
            choice = input("Do you want to continue to the next task anyway? (y/n): ").strip().lower()
            if choice not in ("y", "yes"):
                print("Execution stopped to protect project integrity.")
                return False
        return False


def run_tasks(
    project_dir: Union[str, Path] = ".",
    tasks_file: Union[str, Path] = "TASKS.md",
    session_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    retries: int = 2,
    auto_confirm: bool = False,
    interactive: bool = True,
    sleep_between_tasks: float = 2.0
) -> Dict[str, Any]:
    """
    الواجهة البرمجية الرئيسية (Python API) لتنفيذ مهام ملف الـ Markdown تسلسلياً.

    Args:
        project_dir: مسار مجلد المشروع (الافتراضي هو المجلد الحالي).
        tasks_file: مسار ملف المهام أو اسمه داخل مجلد المشروع.
        session_id: معرف الجلسة، في حال تركه فارغاً يتم توليد معرف تلقائي فريد.
        model: اسم النموذج الافتراضي لـ agy.
        retries: عدد محاولات التعافي عند حدوث أي خطأ في المهمة.
        auto_confirm: بدء التنفيذ فوراً دون طلب تأكيد من المستخدم.
        interactive: تفعيل الوضع التفاعلي عند مواجهة أخطاء أو قرارات التخطي.
        sleep_between_tasks: مدة الانتظار بالثواني بين كل مهمة وأخرى.

    Returns:
        Dict[str, Any]: تقرير شامل لنتائج التنفيذ يحتوي على الإحصائيات ومعرف الجلسة.
    """
    resolved_project_dir = clean_to_absolute_path(project_dir)
    if not resolved_project_dir.is_dir():
        raise NotADirectoryError(f"مجلد المشروع غير موجود: {resolved_project_dir}")

    # تحديد مسار ملف المهام سواء كمسار مستقل أو داخل مجلد المشروع
    task_path_candidate = Path(tasks_file)
    if task_path_candidate.is_absolute() or task_path_candidate.is_file():
        resolved_tasks_file = clean_to_absolute_path(task_path_candidate)
    else:
        resolved_tasks_file = clean_to_absolute_path(resolved_project_dir / tasks_file)

    if not resolved_tasks_file.is_file():
        raise FileNotFoundError(f"ملف المهام غير موجود: {resolved_tasks_file}")

    # معرف الجلسة
    conversation_id = session_id if session_id else f"agy-session-{uuid.uuid4().hex[:10]}"

    # مجلد السجلات داخل المشروع
    log_dir = resolved_project_dir / "tasks_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # تحليل واستخراج المهام
    tasks, skipped_tasks = parse_tasks_file(resolved_tasks_file)

    if skipped_tasks:
        print(f"\n[i] Skipped previously completed tasks: {', '.join(f'#{tid}' for tid in skipped_tasks)}")

    if not tasks:
        print("[!] No pending tasks to execute. All tasks are completed!")
        return {
            "status": "empty",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "skipped": len(skipped_tasks),
            "session_id": conversation_id,
            "log_dir": str(log_dir)
        }

    # طباعة ملخص المهام
    print("\n" + "=" * 70)
    print(f"LOADED PENDING TASKS ({len(tasks)} tasks ready):")
    print("=" * 70)
    for t in tasks:
        print(f"  [>] Task #{t['id']:<4} | Effort: {t['effort'].upper():<8}")
    print("=" * 70)

    # طلب التأكيد إذا لم يكن auto_confirm مفعلاً
    if not auto_confirm and interactive:
        confirm = input(f"\nStart execution immediately using session [{conversation_id}]? (y/n): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Execution cancelled by user.")
            return {
                "status": "cancelled",
                "total": len(tasks),
                "completed": 0,
                "failed": 0,
                "skipped": len(skipped_tasks),
                "session_id": conversation_id,
                "log_dir": str(log_dir)
            }

    completed_count = 0
    failed_count = 0

    try:
        for index, task in enumerate(tasks):
            success = execute_task(
                task=task,
                project_dir=resolved_project_dir,
                tasks_file_path=resolved_tasks_file,
                log_dir=log_dir,
                conversation_id=conversation_id,
                model_name=model,
                max_retries=retries,
                interactive_on_failure=interactive
            )

            if success:
                completed_count += 1
            else:
                failed_count += 1
                if not interactive:
                    print("[!] مهمة فشلت في الوضع غير التفاعلي، تم إيقاف المتابعة.")
                    break

            if index < len(tasks) - 1:
                time.sleep(sleep_between_tasks)

    except KeyboardInterrupt:
        print(f"\n[!] تم إيقاف التنفيذ بواسطة المستخدم بعد إنجاز {completed_count} من أصل {len(tasks)} مهمة.")
        return {
            "status": "interrupted",
            "total": len(tasks),
            "completed": completed_count,
            "failed": failed_count,
            "skipped": len(skipped_tasks),
            "session_id": conversation_id,
            "log_dir": str(log_dir)
        }

    print(f"\nAll tasks finished! Completed: {completed_count}/{len(tasks)}. Logs saved in: {log_dir}")
    return {
        "status": "completed" if failed_count == 0 else "partial",
        "total": len(tasks),
        "completed": completed_count,
        "failed": failed_count,
        "skipped": len(skipped_tasks),
        "session_id": conversation_id,
        "log_dir": str(log_dir)
    }
