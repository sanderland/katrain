from __future__ import annotations

import json
import os
from collections.abc import Iterator


class JsonConfigStore:
    def __init__(self, filename: str, indent: int = 4):
        self.filename = filename
        self.indent = indent
        self._data = {}
        if os.path.exists(filename):
            with open(filename, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError(f"Expected object at root of config file {filename}")
            self._data = loaded

    def __iter__(self) -> Iterator[tuple[str, dict]]:
        return iter(self._data.items())

    def get(self, key: str) -> dict:
        return self._data[key]

    def put(self, key: str, **values) -> None:
        self._data[key] = values
        parent_dir = os.path.dirname(self.filename)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(self.filename, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=self.indent, ensure_ascii=False)
            handle.write("\n")
