
from dataclasses import dataclass
from typing import List


@dataclass
class Interaction:
    action: str
    locator: str = ""
    params: str = ""

@dataclass
class Interactions:
    interactions: List[Interaction]