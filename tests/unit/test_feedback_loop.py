"""
Unit tests for AdaptiveConfidenceTuner in observability/feedback_loop.py.
"""
from autonomous_engineer.observability.feedback_loop import (
    AdaptiveConfidenceTuner,
    ConfidenceWeights,
    PRFeedbackRecord,
    PROutcome,
)


def test_confidence_weights_computation():
    weights = ConfidenceWeights()
    # Perfect scores
    score = weights.compute_score(s_grounding=1.0, s_plan=1.0, s_verification=1.0, s_authority=1.0)
    assert score == 1.0

    # Mixed scores
    score_mixed = weights.compute_score(s_grounding=0.8, s_plan=0.6, s_verification=0.9, s_authority=1.0)
    # 0.30*0.8 + 0.25*0.6 + 0.35*0.9 + 0.10*1.0 = 0.24 + 0.15 + 0.315 + 0.10 = 0.805
    assert score_mixed == 0.805


def test_feedback_tuner_shifts_weight_on_rejections():
    tuner = AdaptiveConfidenceTuner()

    # Initial default weights
    initial_weights = tuner.get_calibrated_weights()
    assert initial_weights.w_verification == 0.35

    # Record 3 rejections
    for i in range(3):
        tuner.record_feedback(
            PRFeedbackRecord(
                pr_id=f"pr-{i}",
                issue_id=f"issue-{i}",
                outcome=PROutcome.REJECTED_OR_ABANDONED,
                confidence_at_generation=0.90,
                files_touched=("src/risky_module.py",),
            )
        )

    # Weights should adapt by boosting verification stringency
    adapted_weights = tuner.get_calibrated_weights()
    assert adapted_weights.w_verification > initial_weights.w_verification
    assert adapted_weights.w_verification == 0.50  # 0.35 + min(0.15, 1.0*0.20)

    # Module penalty check
    penalty = tuner.get_module_penalty("src/risky_module.py")
    assert penalty == 0.15  # 3 * 0.05
    assert tuner.get_module_penalty("src/safe_module.py") == 0.0


def test_feedback_persistence(tmp_path):
    log_file = tmp_path / "feedback.jsonl"
    t1 = AdaptiveConfidenceTuner(persistence_file=log_file)
    t1.record_feedback(
        PRFeedbackRecord(
            pr_id="pr-persisted",
            issue_id="issue-p",
            outcome=PROutcome.MERGED_AS_IS,
            confidence_at_generation=0.95,
        )
    )
    assert log_file.exists()

    # Restore in new tuner
    t2 = AdaptiveConfidenceTuner(persistence_file=log_file)
    assert len(t2.feedback_records) == 1
    assert t2.feedback_records[0].pr_id == "pr-persisted"