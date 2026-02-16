#!/usr/bin/env python3
"""
Harness + screenshot helper that does NOT rely on macOS screencapture.

This is useful for CI/agents where Screen Recording permission is missing.

Usage:
  uv run python scripts/popup_harness_screenshot.py ai screenshots/popup_ai.png
  uv run python scripts/popup_harness_screenshot.py ai-human screenshots/popup_ai_human.png
  uv run python scripts/popup_harness_screenshot.py ai-proyear screenshots/popup_ai_proyear.png
  uv run python scripts/popup_harness_screenshot.py newgame screenshots/popup_newgame.png
  uv run python scripts/popup_harness_screenshot.py teacher screenshots/popup_teacher.png
  uv run python scripts/popup_harness_screenshot.py recovery screenshots/popup_recovery.png
  uv run python scripts/popup_harness_screenshot.py load screenshots/popup_load.png
  uv run python scripts/popup_harness_screenshot.py save screenshots/popup_save.png
  uv run python scripts/popup_harness_screenshot.py menu screenshots/menu.png
  uv run python scripts/popup_harness_screenshot.py main screenshots/main_layout.png
"""

import os
import sys

from kivy.clock import Clock
from kivy.core.window import Window

from katrain.__main__ import KaTrainApp


def main() -> None:
    which = (sys.argv[1] if len(sys.argv) > 1 else "config").strip().lower()
    out = (sys.argv[2] if len(sys.argv) > 2 else "screenshots/_katrain_last.png").strip()

    out_dir = os.path.dirname(out) or "."
    os.makedirs(out_dir, exist_ok=True)

    class HarnessApp(KaTrainApp):
        def on_start(self):
            def after_ready():
                self.gui.start()

                def open_popup(_dt):
                    if which == "config":
                        self.gui._do_config_popup()
                    elif which == "ai":
                        self.gui._do_ai_popup()
                    elif which == "ai-human":
                        self.gui._do_ai_popup()
                        popup = self.gui.popup_open
                        if popup and getattr(popup, "content", None) and hasattr(popup.content, "_strategy_select"):
                            popup.content._strategy_select.select_key("ai:human")
                    elif which == "ai-proyear":
                        self.gui._do_ai_popup()
                        popup = self.gui.popup_open
                        if popup and getattr(popup, "content", None) and hasattr(popup.content, "_strategy_select"):
                            popup.content._strategy_select.select_key("ai:human")
                            if hasattr(popup.content, "_human_profile"):
                                popup.content._human_profile.select_key("proyear")
                    elif which == "newgame":
                        self.gui._do_new_game_popup()
                    elif which == "teacher":
                        self.gui._do_teacher_popup()
                    elif which == "recovery":
                        self.gui._do_engine_recovery_popup("Test engine error", "TEST")
                    elif which == "load":
                        self.gui._do_analyze_sgf_popup()
                    elif which == "save":
                        self.gui._do_save_game_as_popup()
                    elif which == "menu":
                        self.gui.nav_drawer.set_state("open")
                    elif which == "main":
                        pass
                    else:
                        # Unknown selector: just show the main window.
                        pass

                    def take_screenshot(_dt2):
                        # Window.screenshot writes the current framebuffer to disk.
                        actual = Window.screenshot(name=out)
                        # Kivy appends a counter if the template has no %(counter).
                        # Normalize to the requested output path for stable filenames.
                        if actual and actual != out:
                            try:
                                os.replace(actual, out)
                                actual = out
                            except Exception:
                                pass
                        print(f"Wrote: {actual or out}")
                        Clock.schedule_once(lambda _dt3: self.stop(), 0.2)

                    # Give Kivy a moment to render the popup/menu state.
                    Clock.schedule_once(take_screenshot, 1.0)

                Clock.schedule_once(open_popup, 0.1)

            self.gui.ensure_engine_ready(after_ready)

    HarnessApp().run()


if __name__ == "__main__":
    main()

