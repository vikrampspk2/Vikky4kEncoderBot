from app.pipeline.router import get_pipeline


MODES = [
    "ENCODING",
    "2K_AI",
    "4K_AI",
    "8K_AI",
    "4K_HYBRID",
    "8K_HYBRID",
]


for mode in MODES:
    plan = get_pipeline(mode)

    print(
        f"{plan.mode}: "
        f"{plan.target_width}x{plan.target_height} | "
        f"SR={plan.super_resolution} | "
        f"Temporal={plan.temporal} | "
        f"Face={plan.face_protection} | "
        f"AudioCopy={plan.preserve_audio}"
    )

print("VIKKY PIPELINE ROUTER READY")
