from app.services.chat_fsm import (
    first_missing_slot,
    initial_current_substate,
    next_stage_after_completion,
    qualified_slot_key,
    stage_slots_complete,
    total_required_slots_count,
)


def test_total_slots_is_nine():
    assert total_required_slots_count() == 9


def test_first_missing_and_completion():
    slots: dict = {}
    assert first_missing_slot(0, slots) == "orientation_ack"
    slots[qualified_slot_key(0, "orientation_ack")] = "ok"
    assert first_missing_slot(0, slots) == "time_ok"
    assert not stage_slots_complete(0, slots)
    slots[qualified_slot_key(0, "time_ok")] = "yes"
    assert stage_slots_complete(0, slots)


def test_initial_substate():
    assert initial_current_substate() == qualified_slot_key(0, "orientation_ack")


def test_next_stage_terminal():
    assert next_stage_after_completion(3) == 4
    assert next_stage_after_completion(4) is None
