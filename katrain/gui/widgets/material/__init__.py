"""Minimal re-implementations of the KivyMD widgets KaTrain used.

KaTrain only ever needed a handful of Material Design widgets, but pulling them
in meant depending on KivyMD (and its theme manager, icon font and widget
hierarchy) for the whole app. These modules provide just those widgets, built
directly on Kivy, so that colours come from :class:`katrain.gui.theme.Theme`
like the rest of the GUI.
"""

from katrain.gui.widgets.material.checkbox import MaterialCheckBox
from katrain.gui.widgets.material.navigationdrawer import NavigationDrawer, NavigationLayout
from katrain.gui.widgets.material.ripple import CircularRippleBehavior, RectangularRippleBehavior
from katrain.gui.widgets.material.spinner import LoadingSpinner
from katrain.gui.widgets.material.textfield import MaterialTextField

__all__ = [
    "CircularRippleBehavior",
    "LoadingSpinner",
    "MaterialCheckBox",
    "MaterialTextField",
    "NavigationDrawer",
    "NavigationLayout",
    "RectangularRippleBehavior",
]
