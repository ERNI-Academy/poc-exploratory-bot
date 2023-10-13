from dataclasses import dataclass
from typing import List


@dataclass
class UseCaseData:
    requirements: str
    use_case_template: str
    scenarios: str = ""
    covered_requirements: str = ""


@dataclass
class UseCaseStep:
    action: str
    expected: str
    requirements: List[str]


@dataclass
class UseCase:
    name: str
    description: str
    steps: List[UseCaseStep]
    assumptions: List[str]


@dataclass
class UseCases:
    use_cases: List[UseCase]
