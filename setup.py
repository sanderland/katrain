import re
import os

from setuptools import find_packages, setup

package_data = {"": ["*.json", "*.kv"], "katrain": [], "tests": []}
packages = find_packages(exclude=["bots", "tests"])
version = re.search('^__version__\s*=\s*"(.*)"', open("katrain/__main__.py").read(), re.M).group(1)


def include_data_files(directory):
    for root, subfolders, files in os.walk(directory):
        for fn in files:
            filename = os.path.join(root.replace("/", os.path.sep), fn)
            parts = filename.split(os.path.sep)
            package_data[parts[0]].append(os.path.join(*parts[1:]))


include_data_files("katrain/KataGo")
include_data_files("katrain/models")
include_data_files("katrain/img/")
include_data_files("katrain/img/flaticon")

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
    author_email="sander.land@gmail.com",
    url="https://github.com/sanderland/katrain",
    license="MIT",
    install_requires=["kivy", "kivy_deps.glew;platform_system=='Windows'", "kivy_deps.sdl2;platform_system=='Windows'", "kivy_deps.gstreamer;platform_system=='Windows'","importlib_resources ;python_version<'3.7'",],
    python_requires=">=3.6, <3.8",
    entry_points={"console_scripts": ["katrain=katrain.__main__:run_app"]},
    classifiers=["Development Status :: 4 - Beta", "Operating System :: Microsoft :: Windows", "Operating System :: POSIX :: Linux", "Programming Language :: Python :: 3"],
    packages=packages,
    package_data=package_data,
)