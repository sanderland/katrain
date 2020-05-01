from kivy.config import Config  # isort:skip

Config.set("input", "mouse", "mouse,multitouch_on_demand")  # isort:skip  # no red dots on right click

from core.main import KaTrainGui
import signal, sys, traceback
from kivy.app import App
from core.common import OUTPUT_DEBUG
from gui import *


class KaTrainApp(App):
    gui = ObjectProperty(None)

    def build(self):
        self.icon = "./img/icon.png"
        self.gui = KaTrainGui()
        Window.bind(on_request_close=self.on_request_close)
        return self.gui

    def on_start(self):
        self.gui.start()

    def on_request_close(self, *args):
        if getattr(self, "gui", None) and self.gui.engine:
            self.gui.engine.shutdown()

    def signal_handler(self, *args):
        if self.gui.debug_level >= OUTPUT_DEBUG:
            print("TRACEBACKS")
            for threadId, stack in sys._current_frames().items():
                print(f"\n# ThreadID: {threadId}")
                for filename, lineno, name, line in traceback.extract_stack(stack):
                    print(f"\tFile: {filename}, line {lineno}, in {name}")
                    if line:
                        print(f"\t\t{line.strip()}")
        self.on_request_close()
        sys.exit(0)


if __name__ == "__main__":
    app = KaTrainApp()
    signal.signal(signal.SIGINT, app.signal_handler)
    try:
        app.run()
    except Exception:
        app.on_request_close()
        raise
