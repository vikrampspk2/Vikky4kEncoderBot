from app.ai.router import get_ai_engine


modes = [
    "2K_AI",
    "4K_AI",
    "8K_AI",
    "4K_HYBRID",
    "8K_HYBRID",
]

for mode in modes:
    engine = get_ai_engine("full_hd", mode)

    print(
        f"{mode} -> "
        f"{engine.name() if engine else 'NONE'}"
    )

print("VIKKY REAL AI ROUTER READY")
