# VIKKY Encoder — FINAL TOTAL

## Locked product rules
- Final output is **MKV only**. MP4 is never produced as a final output.
- Exactly two numeric Telegram owner IDs are configured in `.env`.
- Owners are lifetime/free for every bot feature and never need to pay.
- Normal users pay only for the service they choose.
- Payment is manual: request -> owner QR approval -> QR sent -> user submits proof -> owner verifies -> owner selects grant -> owner final-confirms -> access activates.
- No automatic payment verification and no automatic access grant.

## Prices
- Encoding — ₹300 / 30 days
- 2K Upscale — ₹350 / 30 days
- 4K Upscale — ₹500 / 30 days
- 8K Upscale — ₹1400 / 30 days
- Monthly Full Bot Access — ₹2500 / 30 days

## Private payment setup
1. Copy `.env.example` to `.env`.
2. Put your two numeric Telegram IDs in `OWNER_IDS`.
3. Put your private FamPay/UPI value in `FAMPAY_UPI`.
4. Put your QR image at `config/payment/fampay_qr.png` (or set `VIKKY_QR_PATH`).
5. Never commit `.env`, QR, or payment proofs.

## Owner-controlled QR
A user cannot receive the QR merely by opening Pay. They select a plan and request the QR. Owners receive an approval button. Only after an owner presses **Send QR** does the bot send the configured QR and payment UPI value to that user.

## Owner-controlled payment verification
The user presses **I've Paid** and sends proof. Owners receive the proof. The bot does not grant access at this point. The owner presses **PAID — Grant**, selects the exact entitlement, then presses **CONFIRM & GRANT**. Only then is access activated.

## Contact Admin privacy
Contact Admin is bot-mediated. Users send their message to the bot; the bot relays it to the owners. Owners reply with `/reply REQUEST_ID your message`. The bot does not display the owner's Telegram ID or username to the user.

Telegram bots do not expose reliable read receipts for arbitrary private messages. Therefore the package does not falsely claim an "if unread then extend" rule. Support cleanup is conservative; payment proof files are retained for audit and are not auto-deleted.

## 24/7 reality
Termux is not the final production host. Use a Linux VPS/server for the bot control plane. The included `scripts/vikky.service` is for systemd. Heavy AI needs a real GPU worker; the bundled FFmpeg fallback is not AI upscaling.

## Large files
Telegram cloud Bot API has strict file limits. 50–60GB workflows require a Local Bot API server and/or external object storage/uploader architecture. Do not promise direct Telegram cloud upload for 50–60GB.
