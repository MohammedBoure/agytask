"""
parser.py - دوال استخراج وتحديث ملف المهام والتعامل مع المسارات.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, TypedDict, Union, Optional


class Task(TypedDict):
    """بنية بيانات تمثل المهمة المستخرجة من ملف المهام."""
    id: str
    effort: str
    content: str


def clean_to_absolute_path(raw_input: Union[str, Path]) -> Path:
    """
    تنظيف المسار المدخل وتحويله إلى مسار مطلق صحيح وموحد.

    Args:
        raw_input: النص أو المسار المدخل من المستخدم.

    Returns:
        Path: كائن المسار المطلق بعد التنظيف.
    """
    cleaned = str(raw_input).strip()
    # إزالة أي نقطتين أو مسافات في البداية ناتجة عن النسخ واللصق
    cleaned = re.sub(r"^[:\s]+", "", cleaned)
    # إزالة علامات الاقتباس
    cleaned = cleaned.strip("\"'")
    # توسيع مسار المستخدم ومسار الهوم (~)
    expanded = os.path.expanduser(cleaned)
    return Path(expanded).resolve()


def parse_tasks_file(file_path: Union[str, Path]) -> Tuple[List[Task], List[str]]:
    """
    قراءة وتحليل ملف المهام (Markdown) واستخراج المهام المعلقة والمكتملة.

    Args:
        file_path: مسار ملف المهام.

    Returns:
        Tuple[List[Task], List[str]]: قائمة بالمهام الجاهزة للتنفيذ وقائمة بأرقام المهام المكتملة مسبقاً.

    Raises:
        FileNotFoundError: إذا لم يكن ملف المهام موجوداً.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"ملف المهام غير موجود: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # التعبير النمطي يلتقط رقم المهمة، الجهد، وما إذا كان هناك وسم اكتمال (COMPLETED أو مكتملة)
    pattern = r"^#\s*(\d+)\s*(?::\s*([a-zA-Z]+)?)?(?:\s*\[(COMPLETED|مكتملة)\])?"
    sections = re.split(pattern, content, flags=re.MULTILINE)

    tasks: List[Task] = []
    skipped_tasks: List[str] = []

    # re.split تنتج: [ما قبل أول تطابق، رقم، جهد، حالة الاكتمال، المحتوى، رقم، ...]
    for i in range(1, len(sections), 4):
        task_id = sections[i].strip()
        effort_raw = sections[i + 1]
        status = sections[i + 2]
        body = sections[i + 3].strip() if (i + 3) < len(sections) else ""

        effort = (effort_raw if effort_raw else "medium").strip().lower()

        # التحقق مما إذا كانت المهمة مكتملة مسبقاً
        if status:
            skipped_tasks.append(task_id)
            continue

        if body and len(body) > 3:
            tasks.append({
                "id": task_id,
                "effort": effort,
                "content": body
            })

    return tasks, skipped_tasks


def mark_task_as_completed(file_path: Union[str, Path], task_id: str) -> bool:
    """
    تحديث ترويسة المهمة في الملف وإضافة [COMPLETED] أمامها مباشرة وبأمان.

    Args:
        file_path: مسار ملف المهام المراد تعديله.
        task_id: رقم المهمة المكتملة.

    Returns:
        bool: True في حال تم تحديث الملف بنجاح، و False إذا كانت المهمة موسومة مسبقاً أو غير موجودة.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"ملف المهام غير موجود: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # استبدال سطر عنوان المهمة لإضافة وسم الاكتمال إذا لم يكن موجوداً
    pattern = rf"^(#\s*{re.escape(str(task_id))}(?:\s*:\s*[a-zA-Z]+)?)(?!.*\[COMPLETED\])"

    def replacer(match: re.Match) -> str:
        return f"{match.group(1)} [COMPLETED]"

    updated_content, count = re.subn(pattern, replacer, content, count=1, flags=re.MULTILINE)

    if count > 0:
        # الكتابة الآمنة عبر ملف مؤقت لتفادي تلف البيانات أثناء المقاطعة المفاجئة
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        temp_path.replace(path)
        print(f"[✔] File updated: Task #{task_id} marked as [COMPLETED].")
        return True

    return False
