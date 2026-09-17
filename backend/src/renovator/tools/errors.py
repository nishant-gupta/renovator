"""Shared error contract for the tool layer (design doc §4.5/§4.8).

Two distinct failure modes, matching how the reference app's UI behaves:

- `ValidationError` — a hard reject. The reference app either blocks the
  action outright (e.g. deleting a room still in use) or refuses to save
  (e.g. a circular dependency). There is no "confirm and force" path.
- `ConfirmationRequired` — the reference app shows a `confirm()` dialog and
  proceeds only if the user accepts (e.g. deleting a rate that's in use,
  deleting any task). Callers (the API layer for direct UI actions, or the
  agent's `interrupt_on` middleware once Phase 3/4 wires it up) catch this,
  surface `reason`/`detail` to the user, and re-call the same tool with
  `confirm=True` to proceed.
"""

from __future__ import annotations


class ValidationError(Exception):
    """The requested change is invalid and cannot be forced through."""


class ConfirmationRequired(Exception):
    """The requested change is valid but destructive/surprising — the
    caller must re-invoke the same tool with confirm=True to proceed."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)
