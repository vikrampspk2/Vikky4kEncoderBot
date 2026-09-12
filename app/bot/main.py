import logging
import os
import sys

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import BOT_TOKEN, OWNER_IDS
from app.access.store import AccessStore


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("VIKKY")
access_store = AccessStore()


# =========================================================
# SECURITY
# =========================================================

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


# =========================================================
# KEYBOARDS
# =========================================================

def owner_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 ENCODING", callback_data="owner_encoding"),
        ],
        [
            InlineKeyboardButton("✨ AI UPSCALE", callback_data="owner_upscale"),
        ],
        [
            InlineKeyboardButton("💎 HYBRID REMASTER", callback_data="owner_hybrid"),
        ],
        [
            InlineKeyboardButton("👥 USERS", callback_data="owner_users"),
            InlineKeyboardButton("📤 UPLOADERS", callback_data="owner_uploaders"),
        ],
        [
            InlineKeyboardButton("💳 PAYMENTS", callback_data="owner_payments"),
        ],
        [
            InlineKeyboardButton("☁️ UPLOAD HOSTS", callback_data="owner_hosts"),
        ],
        [
            InlineKeyboardButton("📊 JOBS / WORKERS", callback_data="owner_jobs"),
        ],
        [
            InlineKeyboardButton("⚙️ SETTINGS", callback_data="owner_settings"),
        ],
    ])


def locked_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 GET ACCESS", callback_data="get_access"),
        ],
        [
            InlineKeyboardButton("📞 CONTACT OWNER", callback_data="contact_owner"),
        ],
    ])


def processing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 ENCODING", callback_data="user_encoding"),
        ],
        [
            InlineKeyboardButton("✨ AI UPSCALE", callback_data="user_upscale"),
        ],
        [
            InlineKeyboardButton("💎 HYBRID REMASTER", callback_data="user_hybrid"),
        ],
    ])


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    user = update.effective_user

    if is_owner(user.id):
        await update.message.reply_text(
            "👑 VIKKY Encoder\n\n"
            "Owner access verified.\n"
            "🔐 Secure control mode active.\n\n"
            "Select a control:",
            reply_markup=owner_menu(),
        )
        return

    # Register/update user in the persistent access database.
    access_store.ensure_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
    )

    # Owners always have full access.
    if access_store.has_active_access(user.id):
        await update.message.reply_text(
            "🎬 VIKKY Encoder\\n\\n"
            "✅ Access verified.\\n"
            "Your processing access is active.\\n\\n"
            "Select a processing mode:",
            reply_markup=processing_menu(),
        )
        return

    # Non-approved users remain locked.
    await update.message.reply_text(
        "🎬 VIKKY Encoder\\n\\n"
        "Welcome!\\n\\n"
        "🔒 Your access is currently locked.\\n"
        "Processing features are available after owner approval.\\n\\n"
        "Use the options below:",
        reply_markup=locked_menu(),
    )



# =========================================================
# OWNER ACCESS COMMANDS
# =========================================================

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Owner-only command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/grant USER_ID [DAYS]\n\n"
            "Example:\n/grant 123456789 30"
        )
        return

    try:
        user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30

        if days <= 0 or days > 3650:
            raise ValueError

        access_store.ensure_user(user_id)
        access_store.approve_user(user_id, days=days)

        await update.message.reply_text(
            f"✅ ACCESS GRANTED\\n\\n"
            f"User ID: {user_id}\\n"
            f"Duration: {days} days"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input.\\n"
            "Use: /grant USER_ID [DAYS]"
        )



async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Owner-only command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/revoke USER_ID\n\n"
            "Example:\n/revoke 123456789"
        )
        return

    try:
        user_id = int(context.args[0])

        if is_owner(user_id):
            await update.message.reply_text(
                "⛔ Owner access cannot be revoked."
            )
            return

        access_store.ensure_user(user_id)
        access_store.revoke_user(user_id)

        await update.message.reply_text(
            f"🔒 ACCESS REVOKED\\n\\n"
            f"User ID: {user_id}"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID.\\n"
            "Use: /revoke USER_ID"
        )


async def uploaders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Owner-only command.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage:\n"
            "/uploaders add USER_ID\n"
            "/uploaders remove USER_ID"
        )
        return

    action = context.args[0].lower()

    try:
        user_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    if action == "add":
        if is_owner(user_id):
            await update.message.reply_text(
                "ℹ️ Owner already has full control."
            )
            return

        access_store.ensure_user(user_id)
        access_store.add_uploader(
            user_id,
            added_by=update.effective_user.id,
        )

        await update.message.reply_text(
            f"📤 UPLOADER ADDED\\n\\n"
            f"User ID: {user_id}"
        )
        return

    if action == "remove":
        access_store.remove_uploader(user_id)

        await update.message.reply_text(
            f"📤 UPLOADER REMOVED\\n\\n"
            f"User ID: {user_id}"
        )
        return

    await update.message.reply_text(
        "❌ Unknown action.\\n"
        "Use: add or remove"
    )


# =========================================================
# CALLBACK SECURITY
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # -----------------------------------------------------
    # OWNER-ONLY CALLBACKS
    # -----------------------------------------------------

    if data.startswith("owner_"):
        if not is_owner(user_id):
            await query.answer(
                "⛔ Owner-only control.",
                show_alert=True,
            )
            return

        if data == "owner_users":
            await query.edit_message_text(
                "👥 VIKKY USERS\n\n"
                "User access management is ready.\n\n"
                "Use owner commands:\n"
                "/grant USER_ID DAYS\n"
                "/revoke USER_ID\n\n"
                "Default access period: 30 days.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ OWNER MENU",
                            callback_data="back_owner",
                        )
                    ]
                ]),
            )
            return

        if data == "owner_uploaders":
            await query.edit_message_text(
                "📤 VIKKY UPLOADERS\n\n"
                "Uploader management is ready.\n\n"
                "Use owner commands:\n"
                "/uploaders add USER_ID\n"
                "/uploaders remove USER_ID",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ OWNER MENU",
                            callback_data="back_owner",
                        )
                    ]
                ]),
            )
            return

        if data == "owner_payments":
            await query.edit_message_text(
                "💳 VIKKY PAYMENTS\n\n"
                "Payment management module is ready.\n\n"
                "Next: payment plans, QR flow, proof review, "
                "and owner confirmation.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ OWNER MENU",
                            callback_data="back_owner",
                        )
                    ]
                ]),
            )
            return

        if data == "owner_hosts":
            await query.edit_message_text(
                "☁️ VIKKY UPLOAD HOSTS\n\n"
                "Upload host management module is ready.\n\n"
                "Next: Google Drive + additional host pool, "
                "automatic routing, retry, and owner selection.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ OWNER MENU",
                            callback_data="back_owner",
                        )
                    ]
                ]),
            )
            return

        await query.edit_message_text(
            "👑 VIKKY OWNER CONTROL\n\n"
            f"Selected: {data.replace('owner_', '').upper()}\n\n"
            "🔐 Authorization verified.\n"
            "⚙️ This module will be connected to the real backend next.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ OWNER MENU",
                        callback_data="back_owner",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # OWNER MENU
    # -----------------------------------------------------

    if data == "back_owner":
        if not is_owner(user_id):
            await query.answer(
                "⛔ Owner-only control.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "👑 VIKKY OWNER PANEL\n\n"
            "🔐 Owner authorization verified.\n"
            "Select a control:",
            reply_markup=owner_menu(),
        )
        return

    # -----------------------------------------------------
    # USER ACCESS
    # -----------------------------------------------------

    if data == "get_access":
        await query.edit_message_text(
            "💳 VIKKY ACCESS\n\n"
            "Your access request/payment flow will be connected here.\n\n"
            "🔒 Processing remains locked until owner approval.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ BACK",
                        callback_data="back_locked",
                    )
                ]
            ]),
        )
        return

    if data == "contact_owner":
        await query.edit_message_text(
            "📞 CONTACT OWNER\n\n"
            "Owner contact flow will be connected here.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ BACK",
                        callback_data="back_locked",
                    )
                ]
            ]),
        )
        return

    if data == "back_locked":
        await query.edit_message_text(
            "🎬 VIKKY Encoder\n\n"
            "🔒 Your access is currently locked.\n"
            "Processing features are available after approval.",
            reply_markup=locked_menu(),
        )
        return

    # -----------------------------------------------------
    # PROCESSING BUTTONS
    # -----------------------------------------------------
    # These are intentionally protected.
    # Until the real user-access database is connected,
    # non-owners cannot execute processing.

    if data in {"user_encoding", "user_upscale", "user_hybrid"}:
        if not is_owner(user_id):
            await query.answer(
                "🔒 Access required.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "🎬 Processing control selected.\n\n"
            "Real processing backend will be connected next.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ OWNER MENU",
                        callback_data="back_owner",
                    )
                ]
            ]),
        )
        return

    # -----------------------------------------------------
    # UNKNOWN CALLBACK
    # -----------------------------------------------------

    logger.warning(
        "Unknown callback: user=%s data=%s",
        user_id,
        data,
    )

    await query.answer(
        "Unknown action.",
        show_alert=True,
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Unhandled Telegram error",
        exc_info=context.error,
    )


# =========================================================
# APPLICATION
# =========================================================

def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Set it in .env."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("grant", grant_command))
    application.add_handler(CommandHandler("revoke", revoke_command))
    application.add_handler(CommandHandler("uploaders", uploaders_command))

    application.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    application.add_error_handler(error_handler)

    return application


# =========================================================
# MAIN
# =========================================================

def main():
    logger.info("Starting VIKKY Encoder...")

    application = build_application()

    logger.info(
        "VIKKY Encoder started successfully | owners=%d",
        len(OWNER_IDS),
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
