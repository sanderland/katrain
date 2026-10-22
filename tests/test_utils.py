from katrain.core.utils import is_plain_filename


def test_plain_filenames_are_accepted():
    for name in ["OpenCL.dll", "libssl-3-x64.dll", "katago.exe"]:
        assert is_plain_filename(name), name


def test_paths_out_of_the_target_folder_are_rejected():
    for name in [
        "",
        ".",
        "..",
        "../evil.dll",
        "..\\evil.dll",
        "sub/dir.dll",
        "sub\\dir.dll",
        "/etc/evil.dll",
        "\\\\server\\share\\evil.dll",
        "C:evil.dll",
        "C:\\Windows\\evil.dll",
    ]:
        assert not is_plain_filename(name), name
