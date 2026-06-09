from dataclasses import dataclass, field


@dataclass
class Protocol:
    name: str
    goal: str = ""
    steps: list = field(default_factory=list)
