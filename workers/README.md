# GPU/AI worker contract

`main.py` can call a real worker through `VIKKY_WORKER_CMD` with:
`{input} {output} {mode} {profile}`.

The worker MUST write the requested `{output}` path and that path MUST end in `.mkv`.
The bundled worker is a safe FFmpeg fallback, not an AI model. For genuine AI restoration,
install and test your chosen open-source/licensed model stack on an actual GPU machine.
Do not claim proprietary Topaz models unless licensed and actually installed.
