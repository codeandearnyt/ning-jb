"""The AI layer.

Everything here consumes provider output. Nothing here can execute: a proposal
is inert data that still has to pass the policy engine and, in Agent mode, a
human approval.
"""

from __future__ import annotations

from ningx.ai.proposal import (
    MAX_PROPOSALS,
    Proposal,
    ProposalRejected,
    parse_proposals,
)

__all__ = ["MAX_PROPOSALS", "Proposal", "ProposalRejected", "parse_proposals"]
