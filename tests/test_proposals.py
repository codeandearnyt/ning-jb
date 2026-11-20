"""The proposal boundary: model text in, validated inert actions out.

Every test here feeds a *hostile or sloppy* model response through the parser.
The parser is the only route from language-model output to an :class:`Action`,
so each rule it enforces is a rule an attacker would otherwise have to defeat.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ningx.ai as ai_package
from ningx.ai.proposal import MAX_PROPOSALS, ProposalRejected, parse_proposals
from ningx.core.action_registry import build_default_registry

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

REGISTRY = build_default_registry()

_STARTUP_TARGET = {
    "kind": "startup",
    "hive": "HKCU",
    "registry_path": (
        r"Software\Microsoft\Windows\CurrentVersion\Run"
    ),
    "value_name": "ExampleUpdater",
}

_PROCESS_TARGET = {
    "kind": "process",
    "pid": 4242,
    "create_time": 1700000000.0,
    "executable": r"C:\Program Files\Example\example.exe",
}


def action(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action_type": "startup_disable",
        "target": dict(_STARTUP_TARGET),
        "reason": "runs at every logon and is not needed",
    }
    payload.update(overrides)
    return payload


def parse(payload: object, **overrides: object) -> tuple[object, ...]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    kwargs: dict[str, object] = {
        "registry": REGISTRY,
        "agent_id": "startup-analyst",
        "provider_id": "gemini",
        "model": "gemini-2.5-flash",
        "now": START,
    }
    kwargs.update(overrides)
    return parse_proposals(raw, **kwargs)  # type: ignore[arg-type]


# ------------------------------------------------------------------ happy path


def test_a_valid_proposal_becomes_an_inert_action() -> None:
    proposals = parse({"proposals": [action()]})

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action.action_type == "startup_disable"
    assert proposal.action.target.kind == "startup"
    assert proposal.rationale == "runs at every logon and is not needed"
    assert proposal.provider_id == "gemini"
    assert proposal.model == "gemini-2.5-flash"
    assert proposal.created_at == START
    assert proposal.agent_id == "startup-analyst"


def test_a_single_action_object_is_accepted() -> None:
    proposals = parse(action())
    assert len(proposals) == 1


def test_a_fenced_response_is_accepted_because_models_add_fences_anyway() -> None:
    fenced = "```json\n" + json.dumps({"proposals": [action()]}) + "\n```"
    assert len(parse(fenced)) == 1


def test_a_fence_without_a_language_is_accepted() -> None:
    fenced = "```\n" + json.dumps([action()]) + "\n```"
    assert len(parse(fenced)) == 1


def test_prose_around_the_json_is_rejected_rather_than_guessed_at() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse("Sure! Here is my plan:\n" + json.dumps(action()))
    assert caught.value.reason == "proposal.invalid_json"


def test_an_empty_response_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse("   \n  ")
    assert caught.value.reason == "proposal.empty"


def test_an_empty_proposal_list_is_not_a_success() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse({"proposals": []})
    assert caught.value.reason == "proposal.none"


def test_an_unrecognized_shape_names_what_was_expected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse({"plan": "do things"})
    assert caught.value.reason == "proposal.unrecognized_shape"


def test_a_bare_list_of_actions_is_accepted() -> None:
    proposals = parse(
        [
            action(),
            action(
                action_type="file_quarantine",
                target={"kind": "path", "path": r"C:\Temp\old.tmp"},
            ),
        ]
    )
    assert [proposal.action.action_type for proposal in proposals] == [
        "startup_disable",
        "file_quarantine",
    ]


# --------------------------------------------------------------- relabelling


def test_the_requester_is_overwritten_with_the_agent_identity() -> None:
    proposals = parse(action(requested_by="user"))
    proposal = proposals[0]

    # An auditor must never read a model's claim that the user asked for this.
    assert proposal.action.requested_by == "agent:startup-analyst"
    assert proposal.claimed_requester == "user"
    assert proposal.requester_was_relabelled


def test_an_absent_requester_is_simply_replaced() -> None:
    proposal = parse(action())[0]
    assert proposal.action.requested_by == "agent:startup-analyst"
    assert proposal.claimed_requester is None
    assert not proposal.requester_was_relabelled


# ------------------------------------------------------- smuggled authority


def test_a_model_supplied_risk_level_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(risk="low"))
    assert caught.value.reason == "proposal.invalid_action"
    assert "risk" in caught.value.detail


def test_a_model_supplied_reversibility_claim_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(reversible=True))
    assert caught.value.reason == "proposal.invalid_action"
    assert "reversible" in caught.value.detail


def test_a_model_supplied_approval_flag_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(approved=True))
    assert caught.value.reason == "proposal.invalid_action"


def test_a_top_level_shell_command_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(command="powershell -c Remove-Item C:\\ -Recurse"))
    assert caught.value.reason == "proposal.invalid_action"
    assert "command" in caught.value.detail


def test_a_shell_command_hidden_in_parameters_is_rejected() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(parameters={"command": "cmd /c del /f /s /q C:\\Users"}))
    assert caught.value.reason == "proposal.unknown_parameter"
    assert "command" in caught.value.detail


def test_an_action_with_no_parameters_accepts_an_empty_map() -> None:
    assert parse(action(parameters={}))[0].action.parameters == {}


def test_the_one_action_that_takes_a_parameter_still_accepts_it() -> None:
    proposal = parse(
        action(
            action_type="file_move",
            target={"kind": "path", "path": r"C:\Users\example\Downloads\setup.exe"},
            parameters={"destination": r"C:\Users\example\Downloads\Installers"},
        )
    )[0]
    assert proposal.action.parameters == {
        "destination": r"C:\Users\example\Downloads\Installers"
    }


def test_a_parameter_allowlisted_for_one_action_is_not_accepted_for_another() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(
            action(
                action_type="file_quarantine",
                target={"kind": "path", "path": r"C:\Temp\old.tmp"},
                parameters={"destination": r"C:\Windows\System32"},
            )
        )
    assert caught.value.reason == "proposal.unknown_parameter"


# ------------------------------------------------------------- registry rules


def test_an_unregistered_action_type_is_refused() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(action_type="shell_execute"))
    assert caught.value.reason == "proposal.unknown_action_type"
    assert "shell_execute" in caught.value.detail


def test_a_denied_action_type_still_parses_but_policy_will_deny_it() -> None:
    # The proposal layer's job is shape, not permission. A hardware change is a
    # registered action, so it parses; the policy engine denies it later. This
    # keeps the two layers' responsibilities separate and testable.
    proposal = parse(
        action(
            action_type="hardware_tune",
            target={"kind": "hardware", "device": "cpu", "setting": "voltage"},
        )
    )[0]
    assert proposal.action.action_type == "hardware_tune"


def test_a_target_kind_that_does_not_match_the_action_is_refused() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(target=dict(_PROCESS_TARGET)))
    assert caught.value.reason == "proposal.target_kind_mismatch"
    assert "startup" in caught.value.detail
    assert "process" in caught.value.detail


def test_a_missing_reason_is_refused_because_nothing_can_be_reviewed() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse(action(reason="   "))
    assert caught.value.reason == "proposal.missing_reason"


def test_a_non_object_item_names_its_index() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse({"proposals": [action(), "disable everything"]})
    assert caught.value.reason == "proposal.not_an_object"
    assert "item 1" in caught.value.detail


# -------------------------------------------------------------------- limits


def test_more_than_twenty_proposals_is_refused() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse({"proposals": [action() for _ in range(MAX_PROPOSALS + 1)]})
    assert caught.value.reason == "proposal.too_many"


def test_exactly_the_limit_is_accepted() -> None:
    assert len(parse({"proposals": [action() for _ in range(MAX_PROPOSALS)]})) == MAX_PROPOSALS


def test_an_oversized_response_is_refused_before_parsing() -> None:
    with pytest.raises(ProposalRejected) as caught:
        parse("x" * 200_001)
    assert caught.value.reason == "proposal.too_large"


# ------------------------------------------------------------------ structure


def _imports(package: object) -> set[str]:
    imported: set[str] = set()
    root = Path(package.__file__).parent  # type: ignore[attr-defined]
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    return imported


def test_the_ai_layer_cannot_reach_anything_that_executes() -> None:
    forbidden = (
        "subprocess",
        "ctypes",
        "winreg",
        "win32api",
        "win32con",
        "ningx.winapi",
    )
    imported = _imports(ai_package)
    for name in forbidden:
        assert not any(
            module == name or module.startswith(name + ".") for module in imported
        ), f"ningx.ai must not import {name}: {sorted(imported)}"


def test_a_proposal_offers_no_way_to_run_itself() -> None:
    proposal = parse(action())[0]
    assert not hasattr(proposal, "execute")
    assert not hasattr(proposal, "run")
    assert not hasattr(proposal, "apply")


def test_the_parser_accepts_no_executor_or_callback() -> None:
    signature = inspect.signature(parse_proposals)
    assert set(signature.parameters) == {
        "raw",
        "registry",
        "agent_id",
        "provider_id",
        "model",
        "now",
    }
