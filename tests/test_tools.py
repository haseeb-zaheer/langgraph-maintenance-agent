from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from langgraph_maintenance_agent.config import AppConfig, CheckName, RepoConfig
from langgraph_maintenance_agent.tools import build_tool_registry
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import ToolLimits


def make_registry(repo_root: Path, *, limits: ToolLimits | None = None):
    config = AppConfig(repos=[RepoConfig(name="demo", path=repo_root, enabled=True)])
    context = ToolContext.from_config(config, limits=limits)
    return build_tool_registry(context)


def make_source_registry(repo_root: Path, **repo_overrides: object):
    config = AppConfig(
        repos=[
            RepoConfig(
                name="demo",
                path=repo_root,
                enabled=True,
                checks=[CheckName.SOURCE_REVIEW],
                **repo_overrides,
            )
        ]
    )
    context = ToolContext.from_config(config)
    return build_tool_registry(context)


def make_command_registry(
    repo_root: Path,
    *,
    safe_commands: dict[str, str],
    checks: list[CheckName] | None = None,
    timeout_seconds: int | None = None,
    limits: ToolLimits | None = None,
):
    config = AppConfig(
        repos=[
            RepoConfig(
                name="demo",
                path=repo_root,
                enabled=True,
                checks=[CheckName.TESTS] if checks is None else checks,
                safe_commands=safe_commands,
                timeout_seconds=timeout_seconds,
            )
        ]
    )
    context = ToolContext.from_config(config, limits=limits)
    return build_tool_registry(context)


def test_registry_rejects_unknown_repo(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)

    result = registry.call("list_files", {"repo_name": "unknown"})

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "unknown_repo"


def test_registry_rejects_unregistered_tools(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)

    with pytest.raises(KeyError, match="unregistered tool"):
        registry.call("read_any_path", {"repo_name": "demo"})


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        "secret.log",
        "data.sqlite",
        "id_rsa",
        "../outside.md",
        "image.png",
    ],
)
def test_read_safe_file_rejects_sensitive_paths(
    tmp_path: Path, relative_path: str
) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (tmp_path / "secret.log").write_text("secret", encoding="utf-8")
    (tmp_path / "data.sqlite").write_text("db", encoding="utf-8")
    (tmp_path / "id_rsa").write_text("private", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    registry = make_registry(tmp_path)

    result = registry.call(
        "read_safe_file",
        {"repo_name": "demo", "relative_path": relative_path},
    )

    assert not result.ok
    assert result.error is not None


def test_read_safe_file_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x" * 20, encoding="utf-8")
    registry = make_registry(tmp_path, limits=ToolLimits(max_bytes_per_file=10))

    result = registry.call(
        "read_safe_file",
        {"repo_name": "demo", "relative_path": "README.md"},
    )

    assert not result.ok


def test_git_tools_work_with_synthetic_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)
    registry = make_registry(tmp_path)

    status = registry.call("git_status", {"repo_name": "demo"})
    latest = registry.call("latest_commit", {"repo_name": "demo"})

    assert status.ok
    assert not status.data["dirty"]
    assert latest.ok
    assert latest.data["subject"] == "Initial"


def test_static_marker_search_is_bounded_and_public_safe(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("# TODO: improve\n" * 5, encoding="utf-8")
    (tmp_path / ".env").write_text("TODO secret\n", encoding="utf-8")
    registry = make_registry(tmp_path, limits=ToolLimits(max_search_matches=2))

    result = registry.call("search_static_markers", {"repo_name": "demo"})

    assert result.ok
    assert len(result.data["matches"]) == 2
    assert result.data["truncated"]
    assert all(match["path"] != ".env" for match in result.data["matches"])


def test_static_marker_search_ignores_generated_next_artifacts(tmp_path: Path) -> None:
    generated = tmp_path / ".next" / "dev" / "server"
    generated.mkdir(parents=True)
    generated.joinpath("bundle.js.map").write_text("TODO generated\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.tsx").write_text(
        "export const value = 1;\n",
        encoding="utf-8",
    )
    registry = make_registry(tmp_path)

    result = registry.call("search_static_markers", {"repo_name": "demo"})

    assert result.ok
    assert result.data["matches"] == []


def test_file_tools_skip_symlinks_that_escape_repo(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("# TODO: private\n", encoding="utf-8")
    (tmp_path / "linked.md").symlink_to(outside)
    registry = make_registry(tmp_path)

    listed = registry.call("list_files", {"repo_name": "demo"})
    searched = registry.call("search_static_markers", {"repo_name": "demo"})
    read = registry.call(
        "read_safe_file",
        {"repo_name": "demo", "relative_path": "linked.md"},
    )

    assert listed.ok
    assert listed.data["files"] == []
    assert searched.ok
    assert searched.data["matches"] == []
    assert not read.ok


def test_list_files_prunes_sensitive_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "README.md").write_text("x", encoding="utf-8")
    registry = make_registry(tmp_path)

    result = registry.call("list_files", {"repo_name": "demo"})

    assert result.ok
    paths = [entry["path"] for entry in result.data["files"]]
    assert paths == ["src/README.md"]


def test_source_tree_summary_detects_nextjs_and_candidates(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"next":"1.0.0","react":"1.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "page.tsx").write_text(
        "export default function Page() { return null; }\n",
        encoding="utf-8",
    )
    registry = make_source_registry(tmp_path)

    result = registry.call("summarize_source_tree", {"repo_name": "demo"})

    assert result.ok
    assert "nextjs" in result.data["framework_signals"]
    assert result.data["languages"]["typescript"] == 1
    assert result.data["candidate_files"][0]["path"] == "src/page.tsx"


def test_source_tree_summary_detects_python_tests(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )
    registry = make_source_registry(tmp_path)

    result = registry.call("summarize_source_tree", {"repo_name": "demo"})

    assert result.ok
    assert "python" in result.data["framework_signals"]
    assert result.data["languages"]["python"] == 2
    assert result.data["test_roots"] == ["tests"]


def test_list_source_files_respects_budget_and_excludes_generated(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".next").mkdir()
    (tmp_path / ".next" / "generated.ts").write_text(
        "export const x = 1;\n",
        encoding="utf-8",
    )
    registry = make_source_registry(tmp_path, source_review_max_files=1)

    result = registry.call("list_source_files", {"repo_name": "demo"})

    assert result.ok
    assert [entry["path"] for entry in result.data["files"]] == ["src/app.py"]


def test_read_source_file_reads_approved_source_and_redacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "API_KEY = 'secret'\nprint('ok')\n",
        encoding="utf-8",
    )
    registry = make_source_registry(tmp_path)

    result = registry.call(
        "read_source_file",
        {"repo_name": "demo", "relative_path": "src/app.py"},
    )

    assert result.ok
    assert "secret" not in result.data["content"]
    assert "[redacted sensitive line]" in result.data["content"]


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        "src/secret.log",
        ".next/dev/page.tsx",
        "node_modules/pkg/index.ts",
        "src/bundle.js.map",
        "../outside.py",
        "src/image.png",
    ],
)
def test_read_source_file_rejects_unsafe_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "secret.log").write_text("secret", encoding="utf-8")
    (tmp_path / ".next" / "dev").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".next" / "dev" / "page.tsx").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "node_modules" / "pkg" / "index.ts").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "bundle.js.map").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    registry = make_source_registry(tmp_path)

    result = registry.call(
        "read_source_file",
        {"repo_name": "demo", "relative_path": relative_path},
    )

    assert not result.ok
    assert result.error is not None


def test_list_files_respects_max_file_limit(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"{index}.md").write_text("x", encoding="utf-8")
    registry = make_registry(tmp_path, limits=ToolLimits(max_files=2))

    result = registry.call("list_files", {"repo_name": "demo"})

    assert result.ok
    assert len(result.data["files"]) == 2
    assert result.data["truncated"]


def test_static_marker_search_respects_file_byte_limit(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "x" * 50 + "\nTODO: outside limit\n",
        encoding="utf-8",
    )
    registry = make_registry(tmp_path, limits=ToolLimits(max_bytes_per_file=20))

    result = registry.call("search_static_markers", {"repo_name": "demo"})

    assert result.ok
    assert result.data["matches"] == []


def test_dependency_manifest_detection(tmp_path: Path) -> None:
    for filename in ["pyproject.toml", "package.json", "Dockerfile", "dbt_project.yml"]:
        (tmp_path / filename).write_text("{}", encoding="utf-8")
    registry = make_registry(tmp_path)

    result = registry.call("detect_dependency_manifests", {"repo_name": "demo"})

    assert result.ok
    ecosystems = {item["ecosystem"] for item in result.data["manifests"]}
    assert {"python", "node", "docker", "dbt"} <= ecosystems


def test_configured_safe_command_exit_zero_returns_command_result(
    tmp_path: Path,
) -> None:
    registry = make_command_registry(
        tmp_path,
        safe_commands={"tests": f"{sys.executable} -m pytest --version"},
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "tests"},
    )

    assert result.ok
    assert result.data["status"] == "completed"
    command_result = result.data["command_result"]
    assert command_result["exit_code"] == 0
    assert command_result["timed_out"] is False
    assert "pytest" in command_result["stdout_excerpt"]


def test_configured_safe_command_bounds_and_redacts_output(tmp_path: Path) -> None:
    secret_key = "sk-" + "a" * 20
    test_file = tmp_path / "test_secret_output.py"
    test_file.write_text(
        f"def test_secret_output():\n    print('{secret_key}')\n",
        encoding="utf-8",
    )
    registry = make_command_registry(
        tmp_path,
        safe_commands={
            "tests": f"{sys.executable} -m pytest -s test_secret_output.py"
        },
        limits=ToolLimits(max_output_chars=2_000),
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "tests"},
    )

    assert result.ok
    stdout = result.data["command_result"]["stdout_excerpt"]
    assert secret_key not in stdout
    assert "[redacted]" in stdout
    assert len(stdout) <= 2_000


def test_configured_safe_command_runs_in_target_repo(tmp_path: Path) -> None:
    test_file = tmp_path / "test_cwd_output.py"
    test_file.write_text(
        "from pathlib import Path\n"
        "def test_cwd_output():\n"
        "    print(Path.cwd())\n",
        encoding="utf-8",
    )
    registry = make_command_registry(
        tmp_path,
        safe_commands={"tests": f"{sys.executable} -m pytest -s test_cwd_output.py"},
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "tests"},
    )

    assert result.ok
    assert str(tmp_path) in result.data["command_result"]["stdout_excerpt"]
    assert result.data["command_result"]["working_directory"] == str(tmp_path)


def test_configured_safe_command_timeout_is_captured(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sleep.py"
    test_file.write_text(
        "import time\n"
        "def test_sleep():\n"
        "    time.sleep(2)\n",
        encoding="utf-8",
    )
    registry = make_command_registry(
        tmp_path,
        safe_commands={"tests": f"{sys.executable} -m pytest -s test_sleep.py"},
        timeout_seconds=1,
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "tests"},
    )

    assert result.ok
    assert result.data["status"] == "incomplete"
    command_result = result.data["command_result"]
    assert command_result["timed_out"] is True
    assert command_result["exit_code"] is None
    assert command_result["timeout_seconds"] == 1


def test_unknown_command_label_does_not_execute(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    registry = make_command_registry(
        tmp_path,
        safe_commands={"tests": f"{sys.executable} -m pytest --version"},
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "missing"},
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "unknown_command_label"
    assert not marker.exists()


def test_command_label_not_enabled_does_not_execute(tmp_path: Path) -> None:
    registry = make_command_registry(
        tmp_path,
        checks=[],
        safe_commands={"tests": f"{sys.executable} -m pytest --version"},
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "tests"},
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "command_not_enabled"


def test_python_syntax_command_does_not_write_repo_pycache(tmp_path: Path) -> None:
    (tmp_path / "syntax_demo.py").write_text("value = 1\n", encoding="utf-8")
    registry = make_command_registry(
        tmp_path,
        checks=[CheckName.PYTHON_SYNTAX],
        safe_commands={
            "python-syntax": f"{sys.executable} -m py_compile syntax_demo.py"
        },
    )

    result = registry.call(
        "run_configured_safe_command",
        {"repo_name": "demo", "command_label": "python-syntax"},
    )

    assert result.ok
    assert result.data["command_result"]["exit_code"] == 0
    assert not (tmp_path / "__pycache__").exists()
