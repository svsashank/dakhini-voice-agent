from dataclasses import dataclass, field, asdict


@dataclass
class Candidate:
    source: str            # "youtube" | "podcast"
    id: str                # video id or episode guid
    url: str               # page url (youtube) or enclosure url (podcast)
    title: str
    description: str = ""
    duration: float | None = None
    channel: str = ""
    query: str = ""
    score: int = 0
    extra: dict = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.source}:{self.id}"

    def to_dict(self):
        return asdict(self)
