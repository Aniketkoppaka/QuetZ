"""
tests/unit/test_authentic_benchmark.py

Comprehensive tests for Milestone 11:
- Authentic historical benchmark registry validation
- Commit SHA authenticity and length (40-char hex, zero synthetic patterns)
- Authoritative provenance tracking
- Strict ground-truth isolation invariant
- Executor expressiveness categorization
- Pydantic model immutability and round-trip serialization
"""
from __future__ import annotations

import re
import pytest

from autonomous_engineer.evaluation.dataset import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    RealBenchmarkIssue,
)
from autonomous_engineer.evaluation.ground_truth import GroundTruthValidationStatus
from autonomous_engineer.domain.models import Issue


HEX_40_REGEX = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# 1. Authentic SHA & Length Tests
# ---------------------------------------------------------------------------


class TestCommitShaAuthenticity:
    def test_all_verified_cases_have_40_char_hex_shas(self) -> None:
        authentic_cases = [c for c in BENCHMARK_REGISTRY if not c.case_id.startswith("EXCL-")]
        assert len(authentic_cases) >= 10, f"Expected at least 10 authentic cases, found {len(authentic_cases)}"

        for case in authentic_cases:
            assert HEX_40_REGEX.match(case.parent_commit_sha), (
                f"Case {case.case_id} parent SHA '{case.parent_commit_sha}' is not a valid 40-char hex SHA"
            )
            assert HEX_40_REGEX.match(case.reference_commit_sha), (
                f"Case {case.case_id} ref SHA '{case.reference_commit_sha}' is not a valid 40-char hex SHA"
            )

    def test_zero_synthetic_patterns_in_verified_cases(self) -> None:
        authentic_cases = [c for c in BENCHMARK_REGISTRY if not c.case_id.startswith("EXCL-")]
        for case in authentic_cases:
            for sha in (case.parent_commit_sha, case.reference_commit_sha):
                assert "123456789abcdef" not in sha.lower(), (
                    f"Case {case.case_id} contains synthetic placeholder pattern in SHA: {sha}"
                )
                assert "deadbeef" not in sha.lower(), (
                    f"Case {case.case_id} contains placeholder deadbeef in SHA: {sha}"
                )


# ---------------------------------------------------------------------------
# 2. Provenance & Metadata Tests
# ---------------------------------------------------------------------------


class TestBenchmarkProvenance:
    def test_all_verified_cases_have_provenance_and_urls(self) -> None:
        verified_cases = [c for c in BENCHMARK_REGISTRY if c.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)]
        for case in verified_cases:
            assert len(case.provenance_sources) > 0, f"Case {case.case_id} missing provenance sources"
            assert case.pull_request_url or case.issue_url, f"Case {case.case_id} missing PR or issue URL"
            assert len(case.expected_affected_files) > 0, f"Case {case.case_id} missing expected affected files"
            assert len(case.reference_patch_summary) > 0, f"Case {case.case_id} missing reference patch summary"

    def test_all_excluded_cases_have_documented_rationale(self) -> None:
        excluded_cases = [c for c in BENCHMARK_REGISTRY if c.status == BenchmarkIssueStatus.EXCLUDED]
        assert len(excluded_cases) >= 3, "Expected at least 3 documented excluded cases"
        for case in excluded_cases:
            assert case.exclusion_reason is not None and len(case.exclusion_reason) > 0, (
                f"Excluded case {case.case_id} missing exclusion reason"
            )


# ---------------------------------------------------------------------------
# 3. Ground-Truth Isolation Invariant Tests
# ---------------------------------------------------------------------------


class TestGroundTruthIsolationInvariant:
    def test_to_planner_issue_strips_all_evaluator_metadata(self) -> None:
        verified_cases = [c for c in BENCHMARK_REGISTRY if c.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)]
        for case in verified_cases:
            planner_issue: Issue = case.to_planner_issue()
            assert isinstance(planner_issue, Issue)
            assert planner_issue.id == case.case_id
            assert planner_issue.title == case.issue_title
            assert planner_issue.body == case.issue_body
            assert planner_issue.repository_url == case.repository_url

            # Verify evaluator attributes do NOT exist on the domain Issue object
            for attr in (
                "parent_commit_sha",
                "reference_commit_sha",
                "expected_affected_files",
                "expected_test_command",
                "reference_patch_summary",
                "issue_url",
                "pull_request_url",
                "provenance_sources",
                "executor_expressiveness_category",
                "ground_truth_status",
            ):
                assert not hasattr(planner_issue, attr), (
                    f"Domain Issue leaked evaluator-only attribute '{attr}'"
                )

    def test_planner_issue_does_not_contain_reference_fix_patch(self) -> None:
        verified_cases = [c for c in BENCHMARK_REGISTRY if c.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)]
        for case in verified_cases:
            planner_issue = case.to_planner_issue()
            # Reference patch summary should not be embedded inside the user-facing issue body
            assert case.reference_patch_summary not in planner_issue.body


# ---------------------------------------------------------------------------
# 4. Executor Expressiveness Category Tests
# ---------------------------------------------------------------------------


class TestExecutorExpressiveness:
    def test_all_cases_have_valid_expressiveness_classification(self) -> None:
        valid_categories = {
            "CATEGORY_A_DIRECTLY_EXPRESSIBLE",
            "CATEGORY_B_REQUIRES_SMALL_EXTENSION",
            "CATEGORY_C_NOT_CURRENTLY_EXPRESSIBLE",
        }
        for case in BENCHMARK_REGISTRY:
            assert case.executor_expressiveness_category in valid_categories, (
                f"Case {case.case_id} has invalid expressiveness category: {case.executor_expressiveness_category}"
            )


# ---------------------------------------------------------------------------
# 5. Immutability & Serialization Tests
# ---------------------------------------------------------------------------


class TestModelImmutability:
    def test_real_benchmark_issue_is_frozen(self) -> None:
        case = BENCHMARK_REGISTRY[0]
        with pytest.raises(Exception):  # ValidationError / TypeError due to frozen=True
            case.parent_commit_sha = "0000000000000000000000000000000000000000"  # type: ignore

    def test_json_round_trip(self) -> None:
        case = BENCHMARK_REGISTRY[0]
        json_data = case.model_dump_json()
        reconstructed = RealBenchmarkIssue.model_validate_json(json_data)
        assert reconstructed == case