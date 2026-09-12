# Private payment configuration

Put the owner's QR image here as `fampay_qr.png`.

Put the private UPI/FamPay value in `.env` as `FAMPAY_UPI=`.

Never commit `.env` or the real QR into a public repository.

QR is NOT sent automatically. A user requests a QR; the owner must approve the request from the owner panel/message first. Only then is the QR sent to that user.

The bot does not expose the owner's Telegram ID/username in the payment flow.
