import asyncio
import json
import os
from pathlib import Path

import pytest

from mini_agent.tools import MAX_FILE_BYTES, Workspace, default_registry
from mini_agent.types import ToolCall


async def call(root: Path, name: str, args: dict | str):
    return await default_registry().execute(
        ToolCall(
            id="test_call",
            name=name,
            arguments=args if isinstance(args, str) else json.dumps(args),
        ),
        Workspace(root),
    )


async def test_read_and_create_unicode_paths(tmp_path):
    result = await call(tmp_path, "write_file", {"path": "中文 目录/hello.py", "content": "问候\n"})
    assert result.ok
    read = await call(tmp_path, "read_file", {"path": "中文 目录/hello.py"})
    assert read.data["content"] == "问候\n"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_read_range(tmp_path, newline):
    (tmp_path / "source.py").write_bytes(f"one{newline}two{newline}three{newline}".encode())
    result = await call(tmp_path, "read_file", {"path": "source.py", "start_line": 2, "limit": 1})
    assert result.ok
    assert result.data["content"] == f"two{newline}"
    assert result.data["end_line"] == 2
    assert result.data["has_more_lines"] is True


async def test_refuse_overwrite_without_changing_file(tmp_path):
    target = tmp_path / "source.py"
    target.write_text("original", encoding="utf-8")
    result = await call(tmp_path, "write_file", {"path": "source.py", "content": "replaced"})
    assert result.error.code == "file_exists"
    assert target.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize("path", ["../escape.py", ".git/config", ".env", ".env.local", "cert.pem"])
async def test_refuse_outside_and_protected_paths(tmp_path, path):
    result = await call(tmp_path, "write_file", {"path": path, "content": "x"})
    assert not result.ok
    assert result.error.code in {"path_outside_workspace", "protected_path"}


async def test_refuse_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            raise
        junction = await asyncio.create_subprocess_exec(
            "cmd",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(root / "link"),
            str(outside),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(junction.communicate(), timeout=5)
        if junction.returncode != 0:
            pytest.skip(f"无法创建符号链接或 NTFS 联接：{type(exc).__name__}")
    result = await call(root, "write_file", {"path": "link/escape.py", "content": "x"})
    assert result.error.code == "path_outside_workspace"
    assert not (outside / "escape.py").exists()


@pytest.mark.parametrize(
    ("name", "args", "code"),
    [
        ("not_registered", {}, "unknown_tool"),
        ("read_file", "{", "invalid_json"),
        ("read_file", [], "invalid_arguments"),
        ("read_file", {"path": "x", "limit": "10"}, "invalid_arguments"),
        ("read_file", {"path": "x", "extra": "secret-value"}, "invalid_arguments"),
        ("read_file", {"path": "missing.py"}, "file_not_found"),
    ],
)
async def test_tool_errors_are_structured(tmp_path, name, args, code):
    encoded = args if isinstance(args, str) else json.dumps(args)
    result = await call(tmp_path, name, encoded)
    assert not result.ok
    assert result.error.code == code
    assert "secret-value" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("data", "code"), [(b"\x00hello", "binary_file"), (b"\xff", "encoding_error")]
)
async def test_reject_binary_and_unknown_encoding(tmp_path, data, code):
    (tmp_path / "data.bin").write_bytes(data)
    result = await call(tmp_path, "read_file", {"path": "data.bin"})
    assert result.error.code == code


async def test_read_size_limit(tmp_path):
    (tmp_path / "large.txt").write_bytes(b"a" * (MAX_FILE_BYTES + 1))
    result = await call(tmp_path, "read_file", {"path": "large.txt"})
    assert result.error.code == "file_too_large"


async def test_read_truncation_is_explicit(tmp_path):
    (tmp_path / "long.txt").write_text("a" * 13000, encoding="utf-8")
    result = await call(tmp_path, "read_file", {"path": "long.txt"})
    assert result.truncated
    assert len(result.data["content"]) == 12000
