from app.ai.engines.real_esrgan import RealESRGANEngine


class AIRouter:

    def __init__(self):
        self.real_esrgan = RealESRGANEngine()

    def select(self, source_class, mode):
        mode = mode.upper()

        if mode in {"2K_AI", "4K_AI", "8K_AI",
                    "4K_HYBRID", "8K_HYBRID"}:
            return self.real_esrgan

        return None


def get_ai_engine(source_class, mode):
    return AIRouter().select(source_class, mode)
