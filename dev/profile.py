from datetime import datetime

import yappi

from katrain.__main__ import run_app

yappi.set_clock_type("cpu")
yappi.start()
try:
    run_app()
except:
    pass
yappi.get_func_stats().save("callgrind.out." + datetime.now().isoformat(), "CALLGRIND")
