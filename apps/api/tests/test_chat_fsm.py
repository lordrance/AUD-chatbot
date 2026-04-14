from app.schemas.flow import EligibilitySubmit
from app.services.eligibility import evaluate_eligibility
from app.services.chat_fsm import (
    CAP_MARKER_MAX_TURNS,
    STAGE_3_SHRINK_SLOTS,
    first_missing_slot,
    initial_current_substate,
    max_user_turns_for_stage,
    next_stage_after_completion,
    pad_incomplete_stage_with_cap_marker,
    qualified_slot_key,
    stage_slots_complete,
    total_required_slots_count,
)


def test_total_slots_base_count():
    # 1+5+6+5+5 = 22 (Stage 3 shrink slots are conditional, not in static sum)
    assert total_required_slots_count() == 22


def test_first_missing_stage0_through_stage1_start():
    slots: dict = {}
    assert first_missing_slot(0, slots) == "ready_to_start"
    assert not stage_slots_complete(0, slots)
    slots[qualified_slot_key(0, "ready_to_start")] = "yes"
    assert stage_slots_complete(0, slots)


def test_numeric_slot_must_be_valid_0_10():
    slots = {
        qualified_slot_key(1, "recent_drinking_pattern"): "x",
        qualified_slot_key(1, "most_concerning_episode"): "y",
        qualified_slot_key(1, "top_reason_to_cut_down"): "z",
    }
    assert first_missing_slot(1, slots) == "importance_0_10"
    slots[qualified_slot_key(1, "importance_0_10")] = "not-a-number"
    assert first_missing_slot(1, slots) == "importance_0_10"
    slots[qualified_slot_key(1, "importance_0_10")] = "8"
    assert first_missing_slot(1, slots) == "confidence_0_10"


def test_initial_substate():
    assert initial_current_substate() == qualified_slot_key(0, "ready_to_start")


def test_next_stage_terminal():
    assert next_stage_after_completion(3) == 4
    assert next_stage_after_completion(4) is None


def test_max_user_turns_per_stage_defined():
    assert max_user_turns_for_stage(0) >= 3
    assert max_user_turns_for_stage(4) >= 5


def test_pad_incomplete_stage_fills_cap_marker():
    slots: dict = {qualified_slot_key(1, "recent_drinking_pattern"): "x"}
    assert pad_incomplete_stage_with_cap_marker(1, slots) is True
    assert stage_slots_complete(1, slots)
    assert slots.get(qualified_slot_key(1, "importance_0_10")) == "0"
    assert slots.get(qualified_slot_key(1, "most_concerning_episode")) == CAP_MARKER_MAX_TURNS


def test_stage3_shrink_path():
    """信心 <7 时必须依次填 if_then_plan_revised 与 final_confidence_0_10_after_shrink。"""
    slots: dict = {}
    for s in (
        "selected_strategy",
        "if_then_plan",
        "likely_obstacle",
        "workaround",
    ):
        slots[qualified_slot_key(3, s)] = "x"
    slots[qualified_slot_key(3, "final_confidence_0_10")] = "5"
    assert first_missing_slot(3, slots) == STAGE_3_SHRINK_SLOTS[0]
    assert not stage_slots_complete(3, slots)
    slots[qualified_slot_key(3, "if_then_plan_revised")] = "smaller step"
    assert first_missing_slot(3, slots) == STAGE_3_SHRINK_SLOTS[1]
    slots[qualified_slot_key(3, "final_confidence_0_10_after_shrink")] = "8"
    assert stage_slots_complete(3, slots)


def test_eligibility_crisis_screen_fails():
    body = EligibilitySubmit(
        age_years=30,
        sex_at_birth="male",
        audit_c_frequency=3,
        audit_c_typical_quantity=2,
        audit_c_binge=2,
        wants_to_reduce_drinking=True,
        crisis_seeking_emergency_help_now=True,
    )
    r = evaluate_eligibility(body)
    assert not r.passed
    assert "crisis_seeking_emergency_help" in r.reasons


def test_stage3_no_shrink_when_conf_high():
    slots = {}
    for s in (
        "selected_strategy",
        "if_then_plan",
        "likely_obstacle",
        "workaround",
        "final_confidence_0_10",
    ):
        slots[qualified_slot_key(3, s)] = "8" if s == "final_confidence_0_10" else "ok"
    assert first_missing_slot(3, slots) is None
    assert stage_slots_complete(3, slots)
