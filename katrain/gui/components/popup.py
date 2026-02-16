from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

from katrain.gui.popups import I18NPopup


class KtPopupContent(BoxLayout):
    """Base class for popup content widgets used with PopupManager."""

    popup = ObjectProperty(None, allownone=True)

    def validate(self) -> None:
        """Raise if inputs are invalid."""

    def on_opened(self) -> None:
        """Hook after popup is opened."""


@dataclass(frozen=True)
class PopupSpec:
    title_key: str
    size: list[float]
    cache_key: str | None = None


class PopupManager:
    """Centralized popup lifecycle, caching, and wiring."""

    def __init__(self, *, on_popup_dismissed: Callable[[], None] | None = None):
        self._cache: dict[str, I18NPopup] = {}
        self._on_popup_dismissed = on_popup_dismissed

    def get_cached(self, cache_key: str) -> I18NPopup | None:
        return self._cache.get(cache_key)

    def show(self, spec: PopupSpec, content: KtPopupContent) -> I18NPopup:
        if spec.cache_key and spec.cache_key in self._cache:
            popup = self._cache[spec.cache_key]
            popup.open()
            return popup

        # Clamp size via I18NPopup's own logic.
        popup = I18NPopup(title_key=spec.title_key, size=[dp(spec.size[0]), dp(spec.size[1])], content=content)
        # KaTrain historically used `I18NPopup(...).__self__` in some places; normalize.
        if hasattr(popup, "__self__"):
            popup = popup.__self__
        content.popup = popup

        if spec.cache_key:
            self._cache[spec.cache_key] = popup

        if self._on_popup_dismissed:
            popup.bind(on_dismiss=lambda *_: self._on_popup_dismissed())

        popup.open()
        content.on_opened()
        return popup

    def dismiss(self, cache_key: str) -> None:
        popup = self._cache.pop(cache_key)
        popup.dismiss()

    def clear_cache(self) -> None:
        self._cache.clear()


class ConfirmPopupContent(KtPopupContent):
    text = StringProperty("")
    on_confirm = ObjectProperty(None, allownone=True)
    on_cancel = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"

