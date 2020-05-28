from kivy.lang import Builder
from kivy.metrics import sp
from kivy.properties import ObjectProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.app import MDApp
from kivymd.uix.menu import MDDropdownMenu, RightContent


class AnalysisDropdownMenuRightContent(RightContent):
    font_size = NumericProperty(sp(16))


class AnalysisDropdownMenu(MDDropdownMenu):
    pass


ANALYSIS_ICONS = ["git", "git", "git", "git"]
ANALYSIS_OPTIONS = ["analysis:extra", "analysis:equalize", "analysis:sweep", "analysis:aimove"]
ANALYSIS_SHORTCUTS = ["a", "s", "d", "Enter"]


class MenuOpener(BoxLayout):
    analysis_button = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        menu_items = [
            {"icon": icon, "text": text, "right_content_cls": AnalysisDropdownMenuRightContent(text=shortcut)}
            for icon, text, shortcut in zip(ANALYSIS_ICONS, ANALYSIS_OPTIONS, ANALYSIS_SHORTCUTS)
        ]
        self.analysis_menu = AnalysisDropdownMenu(caller=self.analysis_button, items=menu_items, width_mult=6, use_icon_item=False, callback=lambda _: print(_),)

    #        self.analysis_menu.create_menu_items()
    #        for item in self.analysis_menu.menu.ids.box.children:
    #            item.ids._right_container.padding = [100,0,0,0]

    def open_analysis_menu(self):
        self.analysis_menu.open()


KV = """
<Label>:
    canvas.before:
        Color:
            rgba: [1,0,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1

<AnalysisDropdownMenu>:

    
<MDMenuItem>:    
    canvas.after:
        Color:
            rgba: [0,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1

<MDMenuItemIcon>:
    canvas.after:
        Color:
            rgba: [1,1,0,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1
                
<AnalysisDropdownMenuRightContent>:
    width: 0
    adaptive_width: False
    canvas.after:
        Color:
            rgba: [0,0,1,1]
        Line:
            rectangle:  (*self.pos,*self.size)
            width: 1
    Label:
        pos_hint: {'right':0}
        width: dp(30)
        id: label
        size: self.texture_size
        font_size: root.font_size
        text: root.text
        color: [1,0,1,1]
        canvas.after:
            Color:
                rgba: [0,1,1,1]
            Line:
                rectangle:  (*self.pos,*self.size)
                width: 1
                    
<MenuOpener>:
    analysis_button:analysis_button
    Button:
        id: analysis_button
        text:'open!'
        on_press: root.open_analysis_menu()
    Label:
        text: 'text'
"""


Builder.load_string(KV)


class MenuApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def build(self):
        return MenuOpener()


MenuApp().run()
