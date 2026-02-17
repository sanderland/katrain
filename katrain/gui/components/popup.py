from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from katrain.gui.theme import Theme


class KtPopupContent(BoxLayout):
    """Base class for popup content widgets used with PopupManager."""

    popup = ObjectProperty(None, allownone=True)

    def validate(self) -> None:
        """Raise if inputs are invalid."""

    def on_opened(self) -> None:
        """Hook after popup is opened."""


class I18NPopup(Popup):
    """Popup wrapper with i18n title (styled in `katrain/popups.kv`)."""

    title_key = StringProperty("")
    font_name = StringProperty(Theme.DEFAULT_FONT)

    def __init__(self, size=None, **kwargs):
        if size:  # do not exceed window size
            app = App.get_running_app()
            if app and getattr(app, "gui", None):
                size[0] = min(app.gui.width, size[0])
                size[1] = min(app.gui.height, size[1])
        super().__init__(size=size, **kwargs)
        self.bind(on_dismiss=Clock.schedule_once(lambda _dt: App.get_running_app().gui.update_state(), 1))


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
        # Not all legacy popup contents implement `on_opened()`. Keep the new hook for
        # `KtPopupContent` instances, but don't crash for older BoxLayout-based popups.
        if hasattr(content, "on_opened"):
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

