from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResolvedSchema:
    """The three (or four) canonical columns plus any extras carried through."""

    user_id: str
    timestamp: str
    event_name: str
    session_id: str | None = None
    extras: tuple[str, ...] = field(default_factory=tuple)

    def as_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "event_name": self.event_name,
        }
        if self.session_id is not None:
            out["session_id"] = self.session_id
        return out
