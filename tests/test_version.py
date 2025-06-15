import tomllib
from pathlib import Path

from katrain.core.constants import VERSION


def test_version_consistency():
    """Test that the version in constants.py matches the version in pyproject.toml"""
    # Get the project root directory (parent of tests directory)
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"
    
    # Read the version from pyproject.toml
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
    
    pyproject_version = pyproject_data["project"]["version"]
    
    # Compare versions
    assert VERSION == pyproject_version, (
        f"Version mismatch: constants.py has '{VERSION}' but "
        f"pyproject.toml has '{pyproject_version}'. "
        "Please update both files to have the same version."
    ) 