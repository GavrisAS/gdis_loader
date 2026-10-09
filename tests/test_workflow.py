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


def test_candidate_release_requires_linux_and_windows_and_marks_prerelease() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "needs: [version, build, linux-checks]" in workflow
    assert "release_flags+=(--prerelease)" in workflow
    assert 'm["canonical"]' in workflow
    assert "templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v3.xlsx" in workflow
    assert "templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx" in workflow
