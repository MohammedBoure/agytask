# agytask - Antigravity Task Runner

أداة سطر أوامر (CLI Tool) احترافية وحزمة بايثون قابلة للتثبيت لأتمتة وتشغيل وإدارة مهام Antigravity تسلسلياً بالاعتماد على ملفات المهام بصيغة Markdown.

---

## 📁 هيكلية المشروع ودليل الملفات

- **[`pyproject.toml`](file:///C:/Users/moham/Desktop/agytask/pyproject.toml)**: ملف إعدادات البناء والتثبيت ونقطة دخول الطرفية `agytask = "agytask.cli:main"` والتبعيات.
- **[`main.py`](file:///C:/Users/moham/Desktop/agytask/main.py)**: نقطة تشغيل بديلة للتوافقية العكسية تستدعي الدالة الرئيسية من الحزمة.
- **[`.gitignore`](file:///C:/Users/moham/Desktop/agytask/.gitignore)**: تحديد الملفات والمجلدات المستثناة من التتبع في مستودع Git.
- **[`README.md`](file:///C:/Users/moham/Desktop/agytask/README.md)**: التوثيق الشامل ودليل الاستخدام والتثبيت.
- **[`agytask/`](file:///C:/Users/moham/Desktop/agytask/agytask/)**: المجلد البرمجي للحزمة:
  - **[`__init__.py`](file:///C:/Users/moham/Desktop/agytask/agytask/__init__.py)**: تصدير الواجهات البرمجية العامة وتحديد رقم الإصدار.
  - **[`cli.py`](file:///C:/Users/moham/Desktop/agytask/agytask/cli.py)**: معالجة خيارات الطرفية والوضع التفاعلي باستخدام مكتبة Click.
  - **[`parser.py`](file:///C:/Users/moham/Desktop/agytask/agytask/parser.py)**: دوال قراءة وتفكيك ملف المهام وتحديث حالة الإنجاز `[COMPLETED]`.
  - **[`runner.py`](file:///C:/Users/moham/Desktop/agytask/agytask/runner.py)**: دوال تشغيل أوامر subprocess والبث الحي والتعافي التلقائي وإدارة الإشارات.
  - **[`README.md`](file:///C:/Users/moham/Desktop/agytask/agytask/README.md)**: دليل مجلد الحزمة الداخلي.

---

## 🚀 التثبيت المحلي في وضع التطوير (Editable Mode)

لتثبيت الحزمة محلياً وجعل أمر `agytask` متاحاً مباشرة في موجه الأوامر / الطرفية، نفّذ الأمر التالي من مجلد المشروع:

```bash
pip install -e .
```

---

## 💻 استخدام أداة سطر الأوامر (CLI)

بعد التثبيت، يمكنك استدعاء الأداة مباشرة:

```bash
agytask [OPTIONS]
```

### المعاملات والخيارات المتاحة (Flags):

| الخيار | الخيار المختصر | الوصف | القيمة الافتراضية |
| :--- | :--- | :--- | :--- |
| `--project-dir` | `-p` | مسار مجلد المشروع المراد العمل عليه | `.` (المجلد الحالي) |
| `--tasks-file` | `-f` | مسار ملف المهام بصيغة Markdown | `TASKS.md` |
| `--session` | `-s` | معرف الجلسة / المحادثة (Conversation ID) | توليد تلقائي لـ UUID |
| `--model` | `-m` | اسم النموذج المستخدم مع `agy` | `gemini-3.8-flash` |
| `--retries` | | عدد محاولات التعافي عند حدوث خطأ | `2` |
| `--yes` | `-y` | تخطي رسائل التأكيد والبدء المباشر | `False` |
| `--help` | `-h` | عرض رسالة المساعدة ودليل الخيارات | |
| `--version` | | عرض رقم إصدار الأداة | |

### أمثلة على الاستخدام:

1. **التشغيل الافتراضي التفاعلي:**
   ```bash
   agytask
   ```
   يقوم بالبحث عن `TASKS.md` في المجلد الحالي، ويوفر واجهة لاختيار جلسة جديدة أو استئناف جلسة سابقة ثم يطلب التأكيد قبل البدء.

2. **التشغيل المباشر بدون تأكيد مع مسارات مخصصة:**
   ```bash
   agytask -p "C:\MyProject" -f "TASKS.md" -y
   ```

3. **تحديد جلسة معينة ونموذج مخصص و3 محاولات تعافي:**
   ```bash
   agytask -s "my-custom-session" -m "gemini-3.8-flash" --retries 3 -y
   ```

---

## 🐍 الاستخدام كمكتبة بايثون (Python API)

يمكن استيراد الحزمة واستدعاء دوالها مباشرة داخل مشاريع وبرمجيات بايثون الأخرى:

```python
from agytask import run_tasks

# تنفيذ المهام برمجياً
result = run_tasks(
    project_dir=".",
    tasks_file="TASKS.md",
    session_id=None,               # توليد جلسة تلقائياً
    model="gemini-3.8-flash",
    retries=2,
    auto_confirm=True,             # بدء مباشر دون مقاطعة
    interactive=False              # وضع غير تفاعلي للسكربتات المؤتمتة
)

print("حالة التنفيذ:", result["status"])
print(f"تم إنجاز {result['completed']} من أصل {result['total']} مهمة.")
```

### استيراد الدوال الإضافية:

```python
from agytask import (
    parse_tasks_file,
    mark_task_as_completed,
    clean_to_absolute_path,
    execute_task,
    run_stream_command
)

# قراءة المهام وفصل المكتمل عن المعلق
tasks, skipped = parse_tasks_file("TASKS.md")
print(f"المهام المعلقة: {len(tasks)}, المكتملة مسبقاً: {len(skipped)}")
```

---

## 📝 بنية ملف المهام (Tasks Format)

تتعرف الأداة على المهام المكتوبة بصيغة Markdown على النحو التالي:

```markdown
# 1 : high
قم بإعداد هيكلية المشروع وملفات التكوين.

# 2 : medium [COMPLETED]
هذه المهمة مكتملة ولن يتم إعادة تشغيلها.

# 3
مهمة بجهد افتراضي (medium).
```

- وسم الجهد (Effort) اختياري (`low`، `medium`، `high`).
- عند نجاح المهمة، يتم تلقائياً إضافة وسم `[COMPLETED]` في السطر ذاته وحفظ الملف بأمان.

---

## 🛡️ الأمان والتعامل مع المقاطعة (Ctrl+C / SIGINT)

- تدعم الأداة إشارات المقاطعة `Ctrl+C`؛ حيث تقوم بإنهاء العمليات الفرعية (`agy`) فوراً وبشكل نظيف.
- يتم تحديث ملف المهام بطريقة ذرية عبر ملفات مؤقتة (`atomic write`) لحماية الملف الأصلي من أي تلف عند إيقاف العملية فجأة.
