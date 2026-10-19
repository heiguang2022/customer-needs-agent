from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_documentation_exists() -> None:
    required = [
        "README.md",
        "docs/architecture.md",
        "docs/agent-loop.md",
        "docs/data-model.md",
        "docs/api.md",
        "docs/development.md",
        "docs/testing.md",
        "docs/adr/001-hybrid-agent.md",
        "docs/adr/002-sqlite.md",
        "docs/adr/003-structured-output.md",
        "docs/adr/004-deterministic-ranking.md",
    ]
    assert all((ROOT / item).is_file() for item in required)


def test_readme_links_to_core_documents() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in (
        "docs/architecture.md",
        "docs/agent-loop.md",
        "docs/data-model.md",
        "docs/api.md",
        "docs/development.md",
        "docs/testing.md",
        "docs/adr/README.md",
    ):
        assert f"]({target})" in readme
