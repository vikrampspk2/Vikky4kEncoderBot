# VIKKY payment/security flow

Plans:
- Encoding — ₹300 / 30 days
- 2K Upscale — ₹350 / 30 days
- 4K Upscale — ₹500 / 30 days
- 8K Upscale — ₹1400 / 30 days
- Monthly Full Bot Access — ₹2500 / 30 days

Owners: exactly two numeric Telegram IDs, lifetime/free, bypass all payment and entitlement checks.

Normal users: select a service -> request QR -> owner approves -> QR is sent -> user marks paid -> user sends proof -> owner manually verifies -> owner clicks PAID—Grant -> entitlement is activated.

No automatic payment verification or automatic access grant exists.

Contact Admin is bot-mediated. The user's message is relayed to owners and the owner replies using `/reply REQUEST_ID message`. The owner's Telegram ID/username is not revealed by the bot.

Telegram bots cannot reliably know whether a user has read a message, so a true "24h + another 24h if unread" policy cannot be implemented from read receipts. The package uses a conservative 24-hour cleanup policy for support request records/messages where Telegram permissions allow deletion, while payment proof records are retained for audit and are not auto-deleted.
