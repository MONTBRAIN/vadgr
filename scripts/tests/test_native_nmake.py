"""The Windows build must execute the reviewed native compiler's make tool."""

import os
from pathlib import Path
import shutil
import struct

import pytest

from scripts import build_native_wheels as build
from scripts import validate_native_wheels as gate


def tool(tmp_path, machine=0xAA64):
    installation = tmp_path / "Program Files" / "Visual Studio"
    tools = installation / "VC/Tools/MSVC/14.44.35207"
    executable = tools / "bin/Hostarm64/arm64/nmake.exe"
    executable.parent.mkdir(parents=True)
    body = bytearray(512)
    body[:2] = b"MZ"
    struct.pack_into("<I", body, 0x3c, 0x80)
    body[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", body, 0x84, machine)
    struct.pack_into("<H", body, 0x98, 0x20B)
    executable.write_bytes(body)
    return installation, tools, executable


def test_nmake_is_an_absolute_native_tool_from_the_selected_installation(tmp_path, monkeypatch):
    installation, tools, executable = tool(tmp_path)
    monkeypatch.setenv("PATH", "")
    environment = {"VCTOOLSINSTALLDIR": str(tools), "PATH": str(executable.parent)}
    selected = build.native_make(environment, installation)
    assert selected == executable.resolve() and selected.is_absolute()


@pytest.mark.parametrize("mutation", ["missing", "outside_installation", "wrong_host", "wrong_target",
                                      "amd64", "arm64ec", "not_pe", "truncated", "relative"])
def test_nmake_refuses_missing_wrong_directory_or_wrong_executable(tmp_path, mutation):
    installation, tools, executable = tool(tmp_path)
    environment = {"VCTOOLSINSTALLDIR": str(tools), "PATH": str(executable.parent)}
    if mutation == "missing":
        executable.unlink()
    elif mutation == "outside_installation":
        installation = tmp_path / "unreviewed-installation"
    elif mutation in ("wrong_host", "wrong_target"):
        wrong = tools / ("bin/Hostx64/arm64/nmake.exe" if mutation == "wrong_host" else "bin/Hostarm64/x64/nmake.exe")
        wrong.parent.mkdir(parents=True)
        executable.rename(wrong)
        environment["PATH"] = str(wrong.parent)
    elif mutation in ("amd64", "arm64ec"):
        body = bytearray(executable.read_bytes())
        struct.pack_into("<H", body, 0x84, 0x8664 if mutation == "amd64" else 0xA641)
        executable.write_bytes(body)
    elif mutation == "not_pe":
        executable.write_bytes(b"not a native tool" * 10)
    elif mutation == "truncated":
        executable.write_bytes(b"MZ")
    else:
        environment["VCTOOLSINSTALLDIR"] = "relative/tools"
    with pytest.raises(gate.Refused):
        build.native_make(environment, installation)


@pytest.mark.skipif(os.name != "nt", reason="exercises native Windows executable lookup")
def test_windows_child_only_path_needs_an_absolute_executable(tmp_path, monkeypatch):
    executable = tmp_path / "child tools" / "native-lookup-probe.exe"
    executable.parent.mkdir()
    shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32/cmd.exe", executable)
    monkeypatch.setenv("PATH", "")
    environment = os.environ.copy()
    environment["PATH"] = str(executable.parent)
    with pytest.raises(FileNotFoundError):
        build.run([executable.name, "/d", "/c", "exit 0"], env=environment, capture=True)
    assert build.run([executable, "/d", "/c", "exit 0"], env=environment, capture=True) == ""
