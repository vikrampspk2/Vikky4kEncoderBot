from dataclasses import dataclass


@dataclass
class PipelinePlan:
    mode: str
    target_width: int
    target_height: int
    restoration: bool
    super_resolution: bool
    temporal: bool
    face_protection: bool
    preserve_audio: bool
    codec: str = "hevc"


class PipelineRouter:

    MODES = {
        "ENCODING": {
            "width": 0,
            "height": 0,
            "restoration": False,
            "super_resolution": False,
            "temporal": False,
            "face_protection": False,
        },

        "2K_AI": {
            "width": 2560,
            "height": 1440,
            "restoration": True,
            "super_resolution": True,
            "temporal": True,
            "face_protection": True,
        },

        "4K_AI": {
            "width": 3840,
            "height": 2160,
            "restoration": True,
            "super_resolution": True,
            "temporal": True,
            "face_protection": True,
        },

        "8K_AI": {
            "width": 7680,
            "height": 4320,
            "restoration": True,
            "super_resolution": True,
            "temporal": True,
            "face_protection": True,
        },

        "4K_HYBRID": {
            "width": 3840,
            "height": 2160,
            "restoration": True,
            "super_resolution": True,
            "temporal": True,
            "face_protection": True,
        },

        "8K_HYBRID": {
            "width": 7680,
            "height": 4320,
            "restoration": True,
            "super_resolution": True,
            "temporal": True,
            "face_protection": True,
        },
    }

    def create(self, mode: str) -> PipelinePlan:
        mode = mode.upper().strip()

        if mode not in self.MODES:
            raise ValueError(f"Unsupported VIKKY mode: {mode}")

        config = self.MODES[mode]

        return PipelinePlan(
            mode=mode,
            target_width=config["width"],
            target_height=config["height"],
            restoration=config["restoration"],
            super_resolution=config["super_resolution"],
            temporal=config["temporal"],
            face_protection=config["face_protection"],
            preserve_audio=True,
        )


def get_pipeline(mode: str) -> PipelinePlan:
    return PipelineRouter().create(mode)
