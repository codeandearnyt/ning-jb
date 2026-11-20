"""Turning model output into validated proposals.

This module is the only bridge from language-model text to an :class:`Action`,
and it is deliberately narrow:

* The model's JSON is parsed into the *existing* action contract, so
  ``extra="forbid"`` rejects a payload that tries to supply ``risk``,
  ``reversible``, an executor reference or a shell command.
* The action type must exist in the sealed registry, and the target kind must
  match that action's declared target kind.
* ``requested_by`` is overwritten with ``agent:<id>``. A model cannot label its
  own proposal as user-requested, because that label is what an auditor reads.
* Nothing here can execute. A proposal is data; it still has to pass the policy
  engine and, in Agent mode, a human approval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from ningx.contracts.action import Action
from ningx.contracts.time import utcnow
from ningx.core.action_registry import ActionRegistry

MAX_PROPOSALS = 20
_MAX_RAW = 200_000


class ProposalRejected(ValueError):
    """A model response that cannot become a proposal, with a reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class Proposal:
    """One validated proposal. Inert: it carries no executor and no approval."""

    action: Action
    agent_id: str
    provider_id: str
    model: str
    rationale: str
    raw_text: str
    created_at: datetime
    claimed_requester: str | None = None

    @property
    def requester_was_relabelled(self) -> bool:
        return self.claimed_requester is not None


def parse_proposals(
    raw: str,
    *,
    registry: ActionRegistry,
    agent_id: str,
    provider_id: str,
    model: str,
    now: datetime | None = None,
) -> tuple[Proposal, ...]:
    """Validate a model response. Raises :class:`ProposalRejected` with a code."""
    if len(raw) > _MAX_RAW:
        raise ProposalRejected("proposal.too_large", f"{len(raw)} characters")

    payload = _decode(raw)
    items = _items(payload)
    if not items:
        raise ProposalRejected("proposal.none", "the response proposed no actions")
    if len(items) > MAX_PROPOSALS:
        raise ProposalRejected(
            "proposal.too_many", f"{len(items)} proposals, limit is {MAX_PROPOSALS}"
        )

    created = now or utcnow()
    proposals: list[Proposal] = []
    for index, item in enumerate(items):
        proposals.append(
            _build(
                item,
                index=index,
                registry=registry,
                agent_id=agent_id,
                provider_id=provider_id,
                model=model,
                raw=raw,
                now=created,
            )
        )
    return tuple(proposals)


def _build(
    item: object,
    *,
    index: int,
    registry: ActionRegistry,
    agent_id: str,
    provider_id: str,
    model: str,
    raw: str,
    now: datetime,
) -> Proposal:
    if not isinstance(item, dict):
        raise ProposalRejected("proposal.not_an_object", f"item {index} is not an object")

    try:
        action = Action.model_validate(item)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "action"
        raise ProposalRejected(
            "proposal.invalid_action", f"item {index}: {location}: {first['msg']}"
        ) from None

    spec = registry.require(action.action_type)
    if spec is None:
        raise ProposalRejected(
            "proposal.unknown_action_type",
            f"item {index}: {action.action_type!r} is not a registered action",
        )
    if action.target.kind != spec.expected_target_kind:
        raise ProposalRejected(
            "proposal.target_kind_mismatch",
            f"item {index}: {action.action_type} expects a "
            f"{spec.expected_target_kind} target, got {action.target.kind}",
        )
    if not action.reason.strip():
        raise ProposalRejected(
            "proposal.missing_reason",
            f"item {index}: a proposal must state why, or it cannot be reviewed",
        )

    unknown = sorted(set(action.parameters) - spec.allowed_parameters)
    if unknown:
        # A shell command or executor hint would have to travel in here, so
        # unknown parameter names are refused rather than ignored.
        raise ProposalRejected(
            "proposal.unknown_parameter",
            f"item {index}: {action.action_type} does not accept "
            f"{', '.join(repr(name) for name in unknown)}",
        )

    claimed = action.requested_by if action.requested_by != "unknown" else None
    return Proposal(
        action=action.model_copy(update={"requested_by": f"agent:{agent_id}"}),
        agent_id=agent_id,
        provider_id=provider_id,
        model=model,
        rationale=action.reason,
        raw_text=raw,
        created_at=now,
        claimed_requester=claimed,
    )


def _decode(raw: str) -> object:
    text = _strip_fence(raw).strip()
    if not text:
        raise ProposalRejected("proposal.empty", "the response was empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProposalRejected(
            "proposal.invalid_json", f"line {exc.lineno}: {exc.msg}"
        ) from None


def _items(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ProposalRejected("proposal.not_an_object", "expected a JSON object")
    if "proposals" in payload:
        value = payload["proposals"]
        if not isinstance(value, list):
            raise ProposalRejected("proposal.not_an_object", "'proposals' must be a list")
        return value
    if "action_type" in payload:
        return [payload]
    raise ProposalRejected(
        "proposal.unrecognized_shape",
        "expected {'proposals': [...]} or a single action object",
    )


def _strip_fence(raw: str) -> str:
    """Remove a Markdown code fence, which models add even when told not to."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 2:
        return text
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body)


__all__ = [
    "MAX_PROPOSALS",
    "Proposal",
    "ProposalRejected",
    "parse_proposals",
]
