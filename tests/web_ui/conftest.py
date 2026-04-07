import sys
from unittest.mock import MagicMock

# Define a list of kivy modules to mock
kivy_modules = [
    "kivy",
    "kivy.config",
    "kivy.storage",
    "kivy.storage.jsonstore",
    "kivy.utils",
    "kivy.clock",
    "kivy.properties",
    "kivy.uix",
    "kivy.uix.boxlayout",
    "kivy.uix.widget",
    "kivy.core",
    "kivy.core.window",
    "kivy.metrics",
    "kivy._event",
    "kivy.lang",
    "kivy.resources",
    "kivy.app",
    "kivy.core.clipboard",
    "kivymd",
    "kivymd.app",
    "kivymd.uix",
    "kivymd.uix.floatlayout"
]

for mod in kivy_modules:
    sys.modules[mod] = MagicMock()

# Specific mocks for values and classes
sys.modules["kivy.utils"].platform = "linux"

class MockObservable:
    pass
sys.modules["kivy._event"].Observable = MockObservable

# Mock JsonStore to behave like a dict for simple tests
import json
import os

class MockJsonStore(dict):
    def __init__(self, filename, **kwargs):
        super().__init__()
        self.filename = filename
        # Initialize with some default values to avoid KeyError in KaTrainBase
        self["general"] = {"version": "0.0.0", "debug_level": 0}
        if os.path.exists(filename):
            try:
                with open(filename, "r") as f:
                    self.update(json.load(f))
            except Exception:
                pass
        
    def put(self, key, **kwargs):
        self[key] = kwargs
    def get(self, key):
        return self[key]

sys.modules["kivy.storage.jsonstore"].JsonStore = MockJsonStore

# Mock Config
sys.modules["kivy"].Config = MagicMock()
sys.modules["kivy.config"].Config = MagicMock()

# Mock katrain.web.interface to prevent kivy/lang import chain triggered
# by katrain/web/__init__.py → katrain/web/interface.py → katrain.core...
sys.modules["katrain.web.interface"] = MagicMock()
