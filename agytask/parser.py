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
    قراءة وتحليل ملف المهام (Markdown) واستخراج المهام المعلقة والمكتملة بدقة.
    يدعم مختلف صيغ الترويسات مثل:
      # 1 [PENDING]: medium
      # 1 [COMPLETED]: medium
      # 1: high
      # 1: medium [COMPLETED]
      # 1: low [مكتملة]
      # 1

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

    # التعبير النمطي الشامل للترويسات
    pattern = r"^#\s*(\d+)(?:[ \t]+\[(PENDING|COMPLETED|مكتملة)\])?(?:\s*:\s*([a-zA-Z]+))?(?:[ \t]+\[(PENDING|COMPLETED|مكتملة)\])?"
    sections = re.split(pattern, content, flags=re.MULTILINE)

    tasks: List[Task] = []
    skipped_tasks: List[str] = []

    # re.split تنتج مجموعات: [نص_سابق, رقم, حالة1, جهد, حالة2, محتوى, رقم, ...]
    # الخطوة 5 لكل تطابق
    for i in range(1, len(sections), 5):
        task_id = sections[i].strip()
        st1 = sections[i + 1]
        effort_raw = sections[i + 2]
        st2 = sections[i + 3]
        body = sections[i + 4].strip() if (i + 4) < len(sections) else ""

        status = (st1 or st2 or "").upper()
        effort = (effort_raw if effort_raw else "medium").strip().lower()

        # التحقق مما إذا كانت المهمة مكتملة مسبقاً
        if status in ("COMPLETED", "مكتملة"):
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
    تحديث ترويسة المهمة في الملف وإضافة أو استبدال [COMPLETED] بأمان تام.

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

    # الحالة الأولى: استبدال [PENDING] بـ [COMPLETED]
    p_pending = rf"^(#\s*{re.escape(str(task_id))}[^\n]*?)\[PENDING\]"
    updated_content, count = re.subn(p_pending, r"\1[COMPLETED]", content, count=1, flags=re.MULTILINE | re.IGNORECASE)

    # الحالة الثانية: إذا لم تكن تحتوي على [PENDING] وليست مكتملة بعد، نضيف [COMPLETED]
    if count == 0:
        p_append = rf"^(#\s*{re.escape(str(task_id))}(?:\s*:[^\n]*)?)(?!.*\[COMPLETED\])$"
        updated_content, count = re.subn(p_append, r"\1 [COMPLETED]", content, count=1, flags=re.MULTILINE)

    if count > 0:
        # الكتابة الآمنة عبر ملف مؤقت لتفادي تلف البيانات أثناء المقاطعة المفاجئة
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        temp_path.replace(path)
        print(f"[✔] File updated: Task #{task_id} marked as [COMPLETED].")
        return True

    return False
