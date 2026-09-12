from dataclasses import dataclass


@dataclass(frozen=True)
class ModePolicy:
    mode: str
    width: int
    height: int
    ai: bool
    hybrid: bool


MODES = {
    "2K_AI": ModePolicy("2K_AI", 2560, 1440, True, False),
    "4K_AI": ModePolicy("4K_AI", 3840, 2160, True, False),
    "8K_AI": ModePolicy("8K_AI", 7680, 4320, True, False),
    "4K_HYBRID": ModePolicy("4K_HYBRID", 3840, 2160, True, True),
    "8K_HYBRID": ModePolicy("8K_HYBRID", 7680, 4320, True, True),
    "ENCODING": ModePolicy("ENCODING", 0, 0, False, False),
}


def get_policy(mode: str) -> ModePolicy:
    try:
        return MODES[mode]
    except KeyError as exc:
        raise ValueError("UNSUPPORTED_MODE") from exc


def upload_recommendation(mode: str) -> int:
    if mode == "2K_AI":
        return 2
    if mode == "4K_AI":
        return 3
    if mode in ("8K_AI", "8K_HYBRID"):
        return 4
    if mode == "4K_HYBRID":
        return 3
    return 1
