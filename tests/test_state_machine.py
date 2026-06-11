from orchestrator.runtime.state_machine import allowed_transition


def test_closer_only_after_verified_pending_close():
    assert allowed_transition("closer", "verified_pending_close", "done")
    assert not allowed_transition("closer", "ready_for_close", "done")
    assert not allowed_transition("closer", "validator_tester_pending", "done")


def test_slice_verifier_contract():
    assert allowed_transition("slice-verifier", "ready_for_close", "verified_pending_close")
    assert allowed_transition("slice-verifier", "ready_for_close", "needs_debug")
    assert not allowed_transition("slice-verifier", "validator_tester_pending", "verified_pending_close")


def test_developer_tester_flow():
    assert allowed_transition("developer", "in_progress", "validator_tester_pending")
    assert allowed_transition("developer", "in_progress", "blocked")
    assert allowed_transition("debugger", "needs_debug", "validator_tester_pending")
    assert allowed_transition("tester", "validator_tester_pending", "ready_for_close")
    assert allowed_transition("tester", "validator_tester_pending", "needs_debug")
