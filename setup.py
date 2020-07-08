import re
import os

from setuptools import find_packages, setup

package_data = {"": ["*.json", "*.kv", "*.wav"], "katrain": [], "tests": []}
packages = find_packages(exclude=["tests"])
version = re.search('^VERSION\s*=\s*"(.*)"', open("katrain/core/constants.py").read(), re.M).group(1)


def include_data_files(directory):
    for root, subfolders, files in os.walk(directory):
        for fn in files:
            filename = os.path.join(root.replace("/", os.path.sep), fn)
            parts = filename.split(os.path.sep)
            package_data[parts[0]].append(os.path.join(*parts[1:]))


include_data_files("katrain/KataGo")
include_data_files("katrain/models")
include_data_files("katrain/fonts")
include_data_files("katrain/sounds")
include_data_files("katrain/img/")
include_data_files("katrain/img/flaticon")
include_data_files("katrain/i18n")

print(packages, package_data)

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="KaTrain",
    version=version,
    description="Go/Baduk/Weiqi playing and teaching app with a variety of AIs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Sander Land",
    url="https://github.com/sanderland/katrain",
    license="MIT",
    install_requires=[
        "wheel",
        "setuptools",
        "importlib_resources ;python_version<'3.7'",
        "pygame;platform_system=='Darwin'",  # some mac versions need this for kivy
        "cython>=0.24,<=0.29.14,!=0.27,!=0.27.2",  # kivy wants this
        "kivy_deps.glew;platform_system=='Windows'",
        "kivy_deps.sdl2;platform_system=='Windows'",
        "kivy_deps.gstreamer;platform_system=='Windows'",
        "kivy==2.0.0rc2",  # rc3 failing on mac
        "kivymd>=0.104.1",
        "screeninfo;platform_system!='Darwin'",  # for screen resolution, has problems on macos
    ],
    python_requires=">=3.6, <4",
    entry_points={"console_scripts": ["katrain=katrain.__main__:run_app"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
    ],
    packages=packages,
    package_data=package_data,
)
