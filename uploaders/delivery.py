from __future__ import annotations

async def deliver_result(client, uid, channel_id, text, *, job_id='', provider='', url=''):
    from hydrogram import enums
    await client.send_message(uid, text, parse_mode=enums.ParseMode.DISABLED)
    if channel_id:
        try:
            await client.send_message(channel_id, text, parse_mode=enums.ParseMode.DISABLED)
        except Exception:
            pass
