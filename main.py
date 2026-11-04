"""
main.py - نقطة الدخول والتشغيل المباشر لأداة agytask.

الاستخدام:
1. الواجهة الرسومية (Tkinter GUI):
    python main.py

2. واجهة سطر الأوامر (CLI):
    python main.py --help
    python main.py -p . -i
"""

import sys
from agytask.ui import launch_ui
from agytask.cli import main as cli_main

if __name__ == "__main__":
    # عند التشغيل المباشر دون معاملات أو عند طلب الواجهة صراحة يتم فتح واجهة Tkinter
    if len(sys.argv) <= 1 or (len(sys.argv) == 2 and sys.argv[1] in ("--ui", "--gui")):
        launch_ui()
    else:
        cli_main()
