from app.ai.engines.base import AIEngine


class RealESRGANEngine(AIEngine):

    def name(self):
        return "Real-ESRGAN"

    def process(self, input_path, output_path, scale):
        if scale not in (2, 4):
            raise ValueError("Real-ESRGAN scale must be 2 or 4")

        raise NotImplementedError(
            "Real AI worker execution will run on the GPU worker."
        )
