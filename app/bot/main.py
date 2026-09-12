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


def has_access(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    return access_store.has_active_access(user_id)


# =========================================================
# MENUS
# =========================================================

def owner_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎯 ENCODING",
                callback_data="owner_encoding",
            ),
        ],
        [
            InlineKeyboardButton(
                "✨ AI UPSCALE",
                callback_data="owner_upscale",
            ),
        ],
        [
            InlineKeyboardButton(
                "💎 HYBRID REMASTER",
                callback_data="owner_hybrid",
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 USERS",
                callback_data="owner_users",
            ),
            InlineKeyboardButton(
                "📤 UPLOADERS",
                callback_data="owner_uploaders",
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 PAYMENTS",
                callback_data="owner_payments",
            ),
        ],
        [
            InlineKeyboardButton(
                "☁️ UPLOAD HOSTS",
                callback_data="owner_hosts",
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 JOBS / WORKERS",
                callback_data="owner_jobs",
            ),
        ],
        [
            InlineKeyboardButton(
                "⚙️ SETTINGS",
                callback_data="owner_settings",
            ),
        ],
    ])


def locked_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💳 GET ACCESS",
                callback_data="get_access",
            ),
        ],
        [
            InlineKeyboardButton(
                "📞 CONTACT OWNER",
                callback_data="contact_owner",
            ),
        ],
    ])


def processing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎯 ENCODING",
                callback_data="user_encoding",
            ),
        ],
        [
            InlineKeyboardButton(
                "✨ AI UPSCALE",
                callback_data="user_upscale",
            ),
        ],
        [
            InlineKeyboardButton(
                "💎 HYBRID REMASTER",
                callback_data="user_hybrid",
            ),
        ],
    ])


def back_locked_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ BACK",
                callback_data="back_locked",
            )
        ]
    ])


def back_owner_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ OWNER MENU",
                callback_data="back_owner",
            )
        ]
    ])


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return

    user = update.effective_user

    if is_owner(user.id):
        await update.message.reply_text(
            "👑 VIKKY Encoder\n\n"
            "✅ Owner access verified.\n"
            "🔐 Secure control mode active.\n\n"
            "Select a control:",
            reply_markup=owner_menu(),
        )
        return

    access_store.ensure_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
    )

    if has_access(user.id):
        await update.message.reply_text(
            "🎬 VIKKY Encoder\n\n"
            "✅ Access verified.\n"
            "Your processing access is active.\n\n"
            "Select a processing mode:",
            reply_markup=processing_menu(),
        )
        return

    await update.message.reply_text(
        "🎬 VIKKY Encoder\n\n"
        "🔒 Your access is currently locked.\n\n"
        "Processing features become available after "
        "owner approval.\n\n"
        "Use the options below:",
        reply_markup=locked_menu(),
    )


# =========================================================
# /GRANT
# =========================================================

async def grant_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Owner-only command."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/grant USER_ID [DAYS]\n\n"
            "Example:\n"
            "/grant 123456789 30"
        )
        return

    try:
        user_id = int(context.args[0])
        days = (
            int(context.args[1])
            if len(context.args) > 1
            else 30
        )

        if user_id <= 0:
            raise ValueError

        if days <= 0 or days > 3650:
            raise ValueError

        access_store.ensure_user(user_id)
        access_store.approve_user(
            user_id,
            days=days,
        )

        await update.message.reply_text(
            "✅ ACCESS GRANTED\n\n"
            f"User ID: {user_id}\n"
            f"Duration: {days} days"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input.\n"
            "Use: /grant USER_ID [DAYS]"
        )


# =========================================================
# /REVOKE
# =========================================================

async def revoke_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Owner-only command."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/revoke USER_ID\n\n"
            "Example:\n"
            "/revoke 123456789"
        )
        return

    try:
        user_id = int(context.args[0])

        if user_id <= 0:
            raise ValueError

        if is_owner(user_id):
            await update.message.reply_text(
                "⛔ Owner access cannot be revoked."
            )
            return

        access_store.ensure_user(user_id)
        access_store.revoke_user(user_id)

        await update.message.reply_text(
            "🔒 ACCESS REVOKED\n\n"
            f"User ID: {user_id}"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID.\n"
            "Use: /revoke USER_ID"
        )


# =========================================================
# /UPLOADERS
# =========================================================

async def uploaders_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None or update.message is None:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Owner-only command."
        )
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
        if user_id <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID."
        )
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
            "📤 UPLOADER ADDED\n\n"
            f"User ID: {user_id}"
        )
        return

    if action == "remove":
        access_store.remove_uploader(user_id)

        await update.message.reply_text(
            "📤 UPLOADER REMOVED\n\n"
            f"User ID: {user_id}"
        )
        return

    await update.message.reply_text(
        "❌ Unknown action.\n"
        "Use: add or remove"
    )


# =========================================================
# CALLBACKS
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None or query.from_user is None:
        return

    user_id = query.from_user.id
    data = query.data or ""

    # -----------------------------------------------------
    # OWNER CALLBACKS
    # -----------------------------------------------------

    if data.startswith("owner_"):
        if not is_owner(user_id):
            await query.answer(
                "⛔ Owner-only control.",
                show_alert=True,
            )
            return

        await query.answer()

        if data == "owner_users":
            await query.edit_message_text(
                "👥 VIKKY USERS\n\n"
                "Access management is active.\n\n"
                "/grant USER_ID DAYS\n"
                "/revoke USER_ID\n\n"
                "Default access: 30 days.",
                reply_markup=back_owner_menu(),
            )
            return

        if data == "owner_uploaders":
            await query.edit_message_text(
                "📤 VIKKY UPLOADERS\n\n"
                "Uploader management is active.\n\n"
                "/uploaders add USER_ID\n"
                "/uploaders remove USER_ID",
                reply_markup=back_owner_menu(),
            )
            return

        if data == "owner_payments":
            await query.edit_message_text(
                "💳 VIKKY PAYMENTS\n\n"
                "Payment backend is reserved for the "
                "real payment/QR integration.\n\n"
                "No fake payment confirmation is used.",
                reply_markup=back_owner_menu(),
            )
            return

        if data == "owner_hosts":
            await query.edit_message_text(
                "☁️ VIKKY UPLOAD HOSTS\n\n"
                "Google Drive + external host adapters "
                "are configured in the backend.\n\n"
                "Provider upload is only reported as "
                "successful after real provider confirmation.",
                reply_markup=back_owner_menu(),
            )
            return

        if data == "owner_jobs":
            await query.edit_message_text(
                "📊 VIKKY JOBS / WORKERS\n\n"
                "GPU-first orchestration, queueing, "
                "retry and worker recovery are handled "
                "by the backend worker layer.",
                reply_markup=back_owner_menu(),
            )
            return

        await query.edit_message_text(
            "👑 VIKKY OWNER CONTROL\n\n"
            f"Selected: {data[6:].upper()}\n\n"
            "🔐 Owner authorization verified.",
            reply_markup=back_owner_menu(),
        )
        return

    # -----------------------------------------------------
    # BACK OWNER
    # -----------------------------------------------------

    if data == "back_owner":
        if not is_owner(user_id):
            await query.answer(
                "⛔ Owner-only control.",
                show_alert=True,
            )
            return

        await query.answer()

        await query.edit_message_text(
            "👑 VIKKY OWNER PANEL\n\n"
            "🔐 Owner authorization verified.\n"
            "Select a control:",
            reply_markup=owner_menu(),
        )
        return

    # -----------------------------------------------------
    # LOCKED USER
    # -----------------------------------------------------

    if data == "get_access":
        await query.answer()

        await query.edit_message_text(
            "💳 VIKKY ACCESS\n\n"
            "Your access request has to be approved "
            "by a VIKKY owner.\n\n"
            "🔒 Processing remains locked until approval.",
            reply_markup=back_locked_menu(),
        )
        return

    if data == "contact_owner":
        await query.answer()

        await query.edit_message_text(
            "📞 CONTACT OWNER\n\n"
            "Please contact a VIKKY owner for access "
            "and payment instructions.",
            reply_markup=back_locked_menu(),
        )
        return

    if data == "back_locked":
        await query.answer()

        await query.edit_message_text(
            "🎬 VIKKY Encoder\n\n"
            "🔒 Your access is currently locked.\n"
            "Processing is available after approval.",
            reply_markup=locked_menu(),
        )
        return

    # -----------------------------------------------------
    # PROCESSING ACCESS CHECK
    # -----------------------------------------------------

    if data in {
        "user_encoding",
        "user_upscale",
        "user_hybrid",
    }:
        if not has_access(user_id):
            await query.answer(
                "🔒 Access required.",
                show_alert=True,
            )
            return

        await query.answer()

        mode = {
            "user_encoding": "🎯 ENCODING",
            "user_upscale": "✨ AI UPSCALE",
            "user_hybrid": "💎 HYBRID REMASTER",
        }[data]

        await query.edit_message_text(
            f"{mode}\n\n"
            "✅ Access verified.\n\n"
            "The processing request is accepted by "
            "the bot access layer.\n\n"
            "⚙️ Worker execution will only be reported "
            "after the real worker returns a verified result.",
            reply_markup=processing_menu(),
        )
        return

    # -----------------------------------------------------
    # UNKNOWN
    # -----------------------------------------------------

    await query.answer(
        "Unknown action.",
        show_alert=True,
    )

    logger.warning(
        "Unknown callback: user=%s data=%s",
        user_id,
        data,
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Unhandled Telegram error: %s",
        context.error,
        exc_info=(
            type(context.error),
            context.error,
            context.error.__traceback__,
        )
        if context.error
        else None,
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

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("grant", grant_command)
    )

    application.add_handler(
        CommandHandler("revoke", revoke_command)
    )

    application.add_handler(
        CommandHandler("uploaders", uploaders_command)
    )

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
        "VIKKY Encoder started | owners=%d",
        len(OWNER_IDS),
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
