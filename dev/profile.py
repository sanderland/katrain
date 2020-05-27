from datetime import datetime

import yappi

from katrain.__main__ import run_app

yappi.start()
run_app()
yappi.get_func_stats().save("callgrind.out." + datetime.now().isoformat(), "CALLGRIND")
