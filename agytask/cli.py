"""
cli.py - معالجة مدخلات سطر الأوامر (CLI UX) وتقديم واجهة مستخدم احترافية عبر Click.
"""

import sys
import uuid
from pathlib import Path
from typing import Optional

import click

from .parser import clean_to_absolute_path
from .runner import run_tasks, DEFAULT_MODEL


@click.command(
    name="agytask",
    context_settings={"help_option_names": ["-h", "--help"]},
    help="أداة سطر أوامر احترافية لأتمتة وتشغيل مهام Antigravity من ملفات Markdown."
)
@click.option(
    "-p", "--project-dir",
    type=str,
    default=".",
    show_default=True,
    help="مسار مجلد المشروع (الافتراضي: المجلد الحالي)."
)
@click.option(
    "-f", "--tasks-file",
    type=str,
    default="TASKS.md",
    show_default=True,
    help="مسار ملف المهام بصيغة Markdown."
)
@click.option(
    "-s", "--session",
    type=str,
    default=None,
    help="معرف الجلسة (Session / Conversation ID). عند عدم التمرير يتم توليد UUID افتراضي."
)
@click.option(
    "-m", "--model",
    type=str,
    default=DEFAULT_MODEL,
    show_default=True,
    help="اسم النموذج المستخدم لتنفيذ المهام مع agy."
)
@click.option(
    "--retries",
    type=int,
    default=2,
    show_default=True,
    help="عدد محاولات التعافي وإعادة المحاولة في حال فشل أي مهمة."
)
@click.option(
    "-y", "--yes",
    is_flag=True,
    default=False,
    help="تخطي طلبات التأكيد والبدء المباشر بالتنفيذ."
)
@click.version_option(
    version="0.1.0",
    prog_name="agytask",
    message="%(prog)s الإصدار %(version)s"
)
def main(
    project_dir: str,
    tasks_file: str,
    session: Optional[str],
    model: str,
    retries: int,
    yes: bool
) -> None:
    """نقطة الدخول الرئيسية لأداة الطرفية agytask."""
    click.echo("=" * 70)
    click.secho("                ANTIGRAVITY TASK RUNNER PIPELINE                ", fg="cyan", bold=True)
    click.echo("=" * 70)

    # التحقق من مسار المشروع وتفعيله تفاعلياً عند الحاجة
    resolved_proj = clean_to_absolute_path(project_dir)
    if not resolved_proj.is_dir():
        if not yes and sys.stdin.isatty():
            click.secho(f"[!] مجلد المشروع غير موجود: {resolved_proj}", fg="yellow")
            while True:
                user_proj = click.prompt("أدخل مسار مجلد المشروع الصحيح", type=str, default=".")
                resolved_proj = clean_to_absolute_path(user_proj)
                if resolved_proj.is_dir():
                    break
                click.secho(f"[!] المسار غير صحيح أو ليس مجلداً: {resolved_proj}", fg="red")
        else:
            click.secho(f"[✘] خطأ: مجلد المشروع غير موجود: {resolved_proj}", fg="red", err=True)
            sys.exit(1)

    # التحقق من مسار ملف المهام وتفعيله تفاعلياً عند الحاجة
    candidate_tasks = Path(tasks_file)
    if candidate_tasks.is_absolute() or candidate_tasks.is_file():
        resolved_tasks = clean_to_absolute_path(candidate_tasks)
    else:
        resolved_tasks = clean_to_absolute_path(resolved_proj / tasks_file)

    if not resolved_tasks.is_file():
        if not yes and sys.stdin.isatty():
            click.secho(f"[!] ملف المهام غير موجود في: {resolved_tasks}", fg="yellow")
            while True:
                user_file = click.prompt("أدخل مسار ملف المهام الصحيح", type=str, default="TASKS.md")
                c_file = Path(user_file)
                if c_file.is_absolute() or c_file.is_file():
                    resolved_tasks = clean_to_absolute_path(c_file)
                else:
                    resolved_tasks = clean_to_absolute_path(resolved_proj / user_file)

                if resolved_tasks.is_file():
                    break
                click.secho(f"[!] لم يتم العثور على الملف: {resolved_tasks}", fg="red")
        else:
            click.secho(f"[✘] خطأ: ملف المهام غير موجود: {resolved_tasks}", fg="red", err=True)
            sys.exit(1)

    # إدارة الجلسة
    final_session = session
    if not final_session:
        if not yes and sys.stdin.isatty():
            click.echo("\n--- Session Management ---")
            click.echo("1. Start a New Dedicated Session (Recommended)")
            click.echo("2. Resume Existing Session by Conversation ID")
            choice = click.prompt("Select option", type=click.Choice(["1", "2"]), default="1")
            if choice == "2":
                input_id = click.prompt("Enter Conversation ID to resume", type=str, default="").strip()
                if input_id:
                    final_session = input_id
                else:
                    final_session = f"agy-session-{uuid.uuid4().hex[:10]}"
                    click.secho(f"[!] إدخال فارغ. تم توليد معرف جديد: {final_session}", fg="yellow")
            else:
                final_session = f"agy-session-{uuid.uuid4().hex[:10]}"
        else:
            final_session = f"agy-session-{uuid.uuid4().hex[:10]}"

    click.secho(f"[*] Bound Session ID: {final_session}", fg="green")

    try:
        results = run_tasks(
            project_dir=resolved_proj,
            tasks_file=resolved_tasks,
            session_id=final_session,
            model=model,
            retries=retries,
            auto_confirm=yes,
            interactive=(not yes)
        )

        if results.get("status") in ("completed", "empty"):
            sys.exit(0)
        elif results.get("status") == "cancelled":
            sys.exit(130)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        click.secho("\n[!] تم إيقاف التنفيذ بأمان بناءً على طلب المستخدم.", fg="yellow")
        sys.exit(130)
    except Exception as exc:
        click.secho(f"\n[✘] حدث خطأ غير متوقع: {exc}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
