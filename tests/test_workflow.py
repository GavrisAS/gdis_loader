from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "build-windows.yml"


def test_manual_windows_build_is_non_release() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'if [[ "$EVENT_NAME" == "push" && "$REF_NAME" == "refs/heads/main" ]]; then' in workflow
    assert '"workflow_dispatch" && "$REF_NAME" == "refs/heads/main"' not in workflow
    assert "build_version='0.1'" in workflow
    assert "should_release=false" in workflow


def test_release_job_is_gated_by_version_job() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "if: needs.version.outputs.should_release == 'true'" in workflow
    assert 'git tag "$TAG" "$TARGET_SHA"' in workflow
    assert 'gh release create "$TAG"' in workflow
