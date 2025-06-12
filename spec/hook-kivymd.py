from PyInstaller.utils.hooks import collect_data_files, get_package_paths
import os

# Collect all KivyMD data files
datas = collect_data_files('kivymd')

# Add specific KivyMD paths
kivymd_path = get_package_paths('kivymd')[1]

# Ensure KivyMD directories are included
kivymd_data_dirs = ['fonts', 'images', 'uix']
for data_dir in kivymd_data_dirs:
    dir_path = os.path.join(kivymd_path, data_dir)
    if os.path.exists(dir_path):
        datas.append((dir_path, f'kivymd/{data_dir}'))

# Create missing .kv files for KivyMD components
# This is a workaround for KivyMD 1.2.0 missing .kv files
missing_kv_files = {
    'kivymd/uix/label/label.kv': '''
<MDLabel>:
    disabled_color: self.theme_cls.disabled_hint_text_color
    text_size: self.size
''',
    'kivymd/uix/button/button.kv': '''
<MDButton>:
    disabled_color: self.theme_cls.disabled_hint_text_color
''',
    'kivymd/uix/textfield/textfield.kv': '''
<MDTextField>:
    disabled_color: self.theme_cls.disabled_hint_text_color
''',
}

# Add the missing .kv files to datas
import tempfile
import shutil

temp_dir = tempfile.mkdtemp()
for kv_path, kv_content in missing_kv_files.items():
    full_temp_path = os.path.join(temp_dir, kv_path)
    os.makedirs(os.path.dirname(full_temp_path), exist_ok=True)
    with open(full_temp_path, 'w') as f:
        f.write(kv_content)
    datas.append((full_temp_path, kv_path))

# Hidden imports for KivyMD
hiddenimports = [
    'kivymd.icon_definitions',
    'kivymd.font_definitions',
    'kivymd.color_definitions',
    'kivymd.uix.label.label',
    'kivymd.uix.button.button',
    'kivymd.uix.textfield.textfield',
] 