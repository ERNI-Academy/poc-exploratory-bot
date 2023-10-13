from dataclasses import dataclass
from typing import List


@dataclass
class ElementReviewed:
    locator: str
    explanation: str
    should_exist: bool


@dataclass
class Verdict:
    result: str
    acceptance_criteria: str
    explanation: str
    elements_reviewed: List[ElementReviewed]


@dataclass
class Verifications:
    result: str
    acceptance_criteria: str
    not_satisfied: Verdict
    satisfied: Verdict
    explanation: str
