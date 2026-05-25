from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .phase1 import DEFAULT_TRANSLATION_LANGUAGE, Phase1Identifier


@dataclass
class LiveState:
    accepted_response: dict[str, Any] | None = None
    pending_shabad_id: str | None = None
    pending_count: int = 0


class SequenceSmoother:
    def __init__(
        self,
        identifier: Phase1Identifier,
        *,
        shabad_change_confirmations: int = 2,
        max_backward_jump: int = 2,
    ) -> None:
        self.identifier = identifier
        self.shabad_change_confirmations = shabad_change_confirmations
        self.max_backward_jump = max_backward_jump
        self.state = LiveState()

    def update(
        self,
        response: dict[str, Any],
        *,
        translation_language: str = DEFAULT_TRANSLATION_LANGUAGE,
    ) -> dict[str, Any]:
        if response.get("status") != "identified":
            return self._unknown(response, "unknown_chunk")

        if self.state.accepted_response is None:
            return self._accept(response, "initial")

        current = self.state.accepted_response
        current_shabad_id = current["shabad"]["shabad_id"]
        next_shabad_id = response["shabad"]["shabad_id"]
        if next_shabad_id != current_shabad_id:
            return self._handle_shabad_change(response)

        selected_line = self._select_allowed_line(current, response)
        if selected_line is None:
            return self._hold_current(
                "held_impossible_line_jump",
                candidate=response,
            )

        if selected_line["line_id"] != response["active_line"]["line_id"]:
            response = self.identifier.response_for_line(
                response,
                shabad_id=next_shabad_id,
                line_id=selected_line["line_id"],
                translation_language=translation_language,
            )
            response["confidence"] = min(float(response.get("confidence", 0.0)), 0.5)

        return self._accept(response, "accepted_same_shabad")

    def _handle_shabad_change(self, response: dict[str, Any]) -> dict[str, Any]:
        next_shabad_id = response["shabad"]["shabad_id"]
        if self.state.pending_shabad_id == next_shabad_id:
            self.state.pending_count += 1
        else:
            self.state.pending_shabad_id = next_shabad_id
            self.state.pending_count = 1

        if self.state.pending_count >= self.shabad_change_confirmations:
            return self._accept(response, "accepted_confirmed_shabad_change")
        return self._hold_current("held_pending_shabad_change", candidate=response)

    def _select_allowed_line(
        self,
        current: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any] | None:
        current_order = int(current["active_line"]["order"])
        candidates = response.get("top_lines", [])[:3] or [response["active_line"]]
        for candidate in candidates:
            candidate_order = int(candidate["order"])
            if candidate_order == current_order:
                return candidate
            if candidate_order == current_order + 1:
                return candidate
            if bool(candidate.get("is_refrain")):
                return candidate
            if 0 < current_order - candidate_order <= self.max_backward_jump:
                return candidate
        return None

    def _accept(self, response: dict[str, Any], decision: str) -> dict[str, Any]:
        accepted = deepcopy(response)
        accepted["live"] = {
            "status": "accepted",
            "decision": decision,
            "pending_shabad_id": None,
            "pending_count": 0,
        }
        self.state.accepted_response = accepted
        self.state.pending_shabad_id = None
        self.state.pending_count = 0
        return accepted

    def _hold_current(
        self,
        decision: str,
        *,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        held = deepcopy(self.state.accepted_response)
        held["confidence"] = min(float(held.get("confidence", 0.0)), 0.45)
        held["live"] = {
            "status": "holding",
            "decision": decision,
            "pending_shabad_id": self.state.pending_shabad_id,
            "pending_count": self.state.pending_count,
            "candidate_shabad_id": candidate.get("shabad", {}).get("shabad_id"),
            "candidate_line_id": candidate.get("active_line", {}).get("line_id"),
        }
        return held

    def _unknown(self, response: dict[str, Any], decision: str) -> dict[str, Any]:
        unknown = deepcopy(response)
        unknown["live"] = {
            "status": "unknown",
            "decision": decision,
            "pending_shabad_id": self.state.pending_shabad_id,
            "pending_count": self.state.pending_count,
        }
        return unknown

