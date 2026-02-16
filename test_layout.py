"""Test widget layout to debug text positioning."""
import os

os.environ["KIVY_HEADLESS"] = "1"
os.environ["KIVY_NO_WINDOW"] = "1"
os.environ["KIVY_GL_BACKEND"] = "mock"
os.environ["KIVY_LOG_LEVEL"] = "warning"

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.floatlayout import FloatLayout
from kivy.resources import resource_add_path

import katrain

katrain_path = os.path.dirname(katrain.__file__)
resource_add_path(os.path.join(katrain_path, "fonts"))
resource_add_path(os.path.join(katrain_path, "img"))

import katrain.gui.kivyutils  # noqa: F401
Builder.load_file("katrain/gui.kv")

from katrain.gui.kivyutils import *


def dump_label(name, btn):
    lbl = btn.label
    if not lbl:
        print(f"  {name}: NO LABEL")
        return
    print(f"  {name}:")
    print(f"    btn  pos={btn.pos}, size={btn.size}")
    print(f"    lbl  pos={lbl.pos}, size={lbl.size}")
    print(f"    lbl  text_size={lbl.text_size}, halign={lbl.halign}, valign={lbl.valign}")
    print(f"    lbl  texture_size={lbl.texture_size}")
    print(f"    lbl  font_size={lbl.font_size:.1f}")


root = FloatLayout(size=(1400, 900))

# SizedButton (like Undo/Resign)
btn1 = SizedRoundedRectangleButton(text="Undo", size_hint=(None, None), size=(100, 40), pos=(100, 100))
root.add_widget(btn1)

# AutoSizedButton (like Pass)
btn2 = AutoSizedRoundedRectangleButton(text="Pass", size_hint=(None, None), height=40, pos=(250, 100))
root.add_widget(btn2)

# AutoSizedButton (like Analysis Options)
btn3 = AutoSizedRectangleButton(text="Analysis Options", size_hint=(None, None), height=30, pos=(400, 100))
root.add_widget(btn3)

# CollapsablePanelTab
tab = CollapsablePanelTab(text="Point Loss", height=25)
header = CollapsablePanelHeader(height=25, size_hint_y=None, spacing=6, size=(400, 25), pos=(100, 200))
header.add_widget(tab)
root.add_widget(header)

# Force several layout passes
for _ in range(10):
    Clock.tick()

print("Widget layout state after 10 ticks:")
dump_label("SizedButton (Undo)", btn1)
dump_label("AutoSizedButton (Pass)", btn2)
dump_label("AutoSizedButton (Analysis Options)", btn3)
dump_label("CollapsablePanelTab (Point Loss)", tab)

# Check for problems
problems = []
for name, btn in [("Undo", btn1), ("Pass", btn2), ("Analysis Options", btn3), ("Point Loss", tab)]:
    lbl = btn.label
    if not lbl:
        problems.append(f"{name}: no label")
        continue
    if lbl.pos != btn.pos:
        problems.append(f"{name}: label pos {lbl.pos} != btn pos {btn.pos}")
    if lbl.valign != "middle":
        problems.append(f"{name}: valign={lbl.valign}, expected 'middle'")
    if lbl.text_size == (None, None):
        problems.append(f"{name}: text_size is (None, None) - valign won't work")
    if isinstance(btn, AutoSizedButton) and btn.width < 20:
        problems.append(f"{name}: width={btn.width} too small")

if problems:
    print(f"\nPROBLEMS FOUND ({len(problems)}):")
    for p in problems:
        print(f"  - {p}")
else:
    print("\nAll checks passed!")
