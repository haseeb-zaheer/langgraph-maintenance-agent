from __future__ import annotations

from pathlib import Path

import pytest

from langgraph_maintenance_agent.config import (
    CheckName,
    ConfigError,
    RepoConfig,
    load_config,
)


def write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: example
    path: /path/to/example
    enabled: true
    checks:
      - git-status
      - docs
    safe_commands: {}
report:
  output_dir: reports
  filename_prefix: routine-maintenance
  update_latest: true
  discord_enabled: false
""",
    )

    config = load_config(config_path)

    assert config.repos[0].name == "example"
    assert config.repos[0].checks == [CheckName.GIT_STATUS, CheckName.DOCS]
    assert config.report.output_dir == Path("reports")
    assert config.repos[0].source_review_max_files == 20
    assert config.repos[0].source_review_max_plan_files == 12


def test_missing_config_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(tmp_path / "missing.yaml")


def test_duplicate_repo_names_fail(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: duplicate
    path: /path/to/one
    enabled: true
  - name: duplicate
    path: /path/to/two
    enabled: true
""",
    )

    with pytest.raises(ConfigError, match="duplicate repo names"):
        load_config(config_path)


def test_enabled_repo_without_path_fails() -> None:
    with pytest.raises(ValueError, match="enabled repo requires a path"):
        RepoConfig(name="missing-path", enabled=True)


def test_unknown_check_fails(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: example
    path: /path/to/example
    enabled: true
    checks:
      - made-up-check
""",
    )

    with pytest.raises(ConfigError, match="made-up-check"):
        load_config(config_path)


def test_source_review_config_loads(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: example
    path: /path/to/example
    enabled: true
    checks:
      - source-review
      - bug-risk-review
      - refactor-review
      - test-gap-review
    source_roots:
      - src
      - tests
    source_include_patterns:
      - "*.py"
    source_exclude_patterns:
      - "src/generated/*"
    source_review_max_files: 5
    source_review_max_plan_files: 4
    source_review_max_bytes_per_file: 2000
    source_review_max_total_bytes: 10000
    source_review_max_snippets: 3
""",
    )

    config = load_config(config_path)
    repo = config.repos[0]

    assert repo.checks == [
        CheckName.SOURCE_REVIEW,
        CheckName.BUG_RISK_REVIEW,
        CheckName.REFACTOR_REVIEW,
        CheckName.TEST_GAP_REVIEW,
    ]
    assert repo.source_roots == ["src", "tests"]
    assert repo.source_review_max_files == 5
    assert repo.source_review_max_plan_files == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_roots", "[/absolute]"),
        ("source_roots", "[../outside]"),
        ("source_include_patterns", '["../*.py"]'),
        ("source_exclude_patterns", '["/tmp/*"]'),
    ],
)
def test_source_review_paths_must_be_relative(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        f"""
repos:
  - name: example
    path: /path/to/example
    enabled: true
    {field}: {value}
""",
    )

    with pytest.raises(ConfigError, match="source path values"):
        load_config(config_path)


def test_source_review_budget_must_be_positive(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: example
    path: /path/to/example
    enabled: true
    source_review_max_files: 0
""",
    )

    with pytest.raises(ConfigError, match="source review budgets"):
        load_config(config_path)


def test_unsupported_safe_command_label_fails(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: example
    path: /path/to/example
    enabled: true
    safe_commands:
      format: ruff format .
""",
    )

    with pytest.raises(ConfigError, match="unsupported safe command label"):
        load_config(config_path)


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard",
        "touch marker",
        "python -c \"open('x', 'w').write('bad')\"",
        "ruff format .",
        "ruff check --fix .",
        "npm run test",
    ],
)
def test_unsafe_safe_command_string_fails(tmp_path: Path, command: str) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        f"""
repos:
  - name: example
    path: /path/to/example
    enabled: true
    safe_commands:
      tests: {command}
""",
    )

    with pytest.raises(ConfigError, match="approved diagnostic profile"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("label", "command"),
    [
        ("tests", "python -m pytest --version"),
        ("tests", "pytest --version"),
        ("lint", "ruff check --help"),
        ("python-syntax", "python -m compileall --help"),
        ("python-syntax", "python -m py_compile README.md"),
        ("build", "python -m build --help"),
    ],
)
def test_safe_command_profiles_load(
    tmp_path: Path, label: str, command: str
) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        f"""
repos:
  - name: example
    path: /path/to/example
    enabled: true
    safe_commands:
      {label}: {command}
""",
    )

    config = load_config(config_path)

    assert config.repos[0].safe_commands[label] == command


def test_disabled_repo_can_omit_path(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "repos.yaml",
        """
repos:
  - name: disabled-example
    enabled: false
""",
    )

    config = load_config(config_path)

    assert config.repos[0].path is None
    assert not config.repos[0].enabled


def test_example_config_is_public_safe_and_valid() -> None:
    config = load_config(Path("examples/repos.yaml"))

    assert config.repos
    assert str(config.repos[0].path).startswith("/path/to/")
