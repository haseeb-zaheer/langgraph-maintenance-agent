# Agent Tool Safety

Repository inspector agents can call only the registered Python tools created
from validated config. Every tool takes `repo_name`; no tool accepts arbitrary
repository roots from the model. During an individual repo inspection, tool calls
for any other repo are rejected.

Current tools:

- `git_status(repo_name)`: branch, dirty state, ahead/behind where available.
- `latest_commit(repo_name)`: latest hash, commit date, and subject.
- `list_files(repo_name, patterns=None)`: bounded public-safe relative paths.
- `read_safe_file(repo_name, relative_path)`: approved small text docs and
  manifests only.
- `search_static_markers(repo_name)`: bounded TODO/FIXME/HACK summaries.
- `detect_dependency_manifests(repo_name)`: Python, Node, Docker, and dbt
  manifests without running package managers.
- `run_configured_safe_command(repo_name, command_label)`: skipped placeholder
  until command execution is implemented.

Blocked paths include `.env`, logs, databases, private keys, generated reports,
caches, symlinks, path traversal, files outside the repo, oversized files, and
likely binary files. Traversal prunes blocked directories before descending.
Tool outputs are JSON-serializable and bounded before they can be returned to an
LLM.
