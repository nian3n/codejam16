# Owner: shared (Teammate 4 maintains; add fields, never rename them)
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(frozen=True)
class Action:
    verb: str
    target: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"verb": self.verb, "target": dict(self.target)}

    @staticmethod
    def from_json(d: dict) -> "Action":
        return Action(str(d["verb"]), dict(d.get("target") or {}))


class Rule(BaseModel):
    # JSON uses the keywords "if" / "then" / "else"; Python can't, hence the aliases.
    model_config = ConfigDict(populate_by_name=True)
    when: list[list[Any]] | None = Field(default=None, alias="if")
    then: dict | None = None
    otherwise: dict | None = Field(default=None, alias="else")

    @model_validator(mode="after")
    def _one_shape(self):
        if self.otherwise is not None:
            if self.when is not None or self.then is not None:
                raise ValueError("an else rule has no if/then")
        elif self.when is None or self.then is None:
            raise ValueError("a rule needs if + then, or else")
        for cond in self.when or []:
            if len(cond) != 3 or cond[1] not in ("==", "!=", "<", "<=", ">", ">=", "in"):
                raise ValueError(f"bad condition {cond}")
        return self

    @property
    def is_else(self) -> bool:
        return self.otherwise is not None

    def action(self) -> Action:
        a = self.otherwise if self.is_else else self.then
        assert a is not None  # guaranteed by _one_shape
        return Action.from_json(a)


class PuzzleSpec(BaseModel):
    id: str
    title: str
    widget: Literal["wires", "keypad", "icons", "dial", "switches", "big_button"]
    topic: str
    hard: bool = False
    looks_like: str
    pool: list[str]
    target_words: Literal["color", "name", "digits", "letters", "position", "state"]
    setup: dict
    rules: list[Rule]

    @model_validator(mode="after")
    def _ends_with_else(self):
        if not self.rules or not self.rules[-1].is_else:
            raise ValueError(f"{self.id}: last rule must be an else")
        if any(r.is_else for r in self.rules[:-1]):
            raise ValueError(f"{self.id}: only the last rule may be an else")
        return self
