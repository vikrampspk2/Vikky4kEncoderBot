import asyncio, hashlib, json, os, re, shutil, sqlite3, subprocess, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters
)

load_dotenv()

APP = "VIKKY Encoder"
BASE = Path(__file__).resolve().parent
DB = BASE / "config" / "vikky.db"
TEMP = BASE / "temp"
OUT = BASE / "outputs"
REPORTS = BASE / "logs"
PAYMENT_DIR = BASE / "config" / "payment"
QR_PATH = Path(os.getenv("VIKKY_QR_PATH", str(PAYMENT_DIR / "fampay_qr.png")))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
MAX_INPUT_GB = float(os.getenv("VIKKY_MAX_INPUT_GB", "60"))
WORKER_CMD = os.getenv("VIKKY_WORKER_CMD", "").strip()
LIVE_INTERVAL = max(2, int(os.getenv("VIKKY_LIVE_INTERVAL", "5")))
FAMPAY_UPI = os.getenv("FAMPAY_UPI", "").strip()
CONTACT_DELETE_HOURS = max(1, int(os.getenv("CONTACT_DELETE_HOURS", "24")))

# Paid service plans. Owners bypass all entitlement checks.
PLANS = {
    "ENCODE_300": {"label": "🎬 Encoding — ₹300", "days": 30, "kind": "encode"},
    "UP2K_350": {"label": "✨ 2K Upscale — ₹350", "days": 30, "kind": "upscale_2k"},
    "UP4K_500": {"label": "✨ 4K Upscale — ₹500", "days": 30, "kind": "upscale_4k"},
    "UP8K_1400": {"label": "🔥 8K Upscale — ₹1400", "days": 30, "kind": "upscale_8k"},
    "ALL_2500": {"label": "👑 Monthly Full Bot Access — ₹2500", "days": 30, "kind": "all"},
}

MODES = {
    "encode": ["SMART", "3GB", "4GB", "5GB", "6GB", "7GB", "8GB", "CUSTOM"],
    "upscale": ["2K_AI", "4K_AI", "8K_AI"],
    "hybrid": ["4K_HYBRID", "8K_HYBRID"],
}

for p in (TEMP, OUT, REPORTS, DB.parent, PAYMENT_DIR):
    p.mkdir(parents=True, exist_ok=True)


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, access_until INTEGER DEFAULT 0, uploader INTEGER DEFAULT 0, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS entitlements(uid INTEGER NOT NULL, plan TEXT NOT NULL, until INTEGER NOT NULL, PRIMARY KEY(uid, plan));
    CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, uid INTEGER NOT NULL, plan TEXT NOT NULL, payload TEXT UNIQUE, status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL, proof_file TEXT DEFAULT '', proof_message_id INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS support_requests(id TEXT PRIMARY KEY, uid INTEGER NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL, owner_message_ids TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, uid INTEGER NOT NULL, mode TEXT NOT NULL, profile TEXT NOT NULL,
      status TEXT NOT NULL, progress INTEGER DEFAULT 0, input TEXT, output TEXT, error TEXT, created INTEGER NOT NULL, updated INTEGER NOT NULL,
      duration REAL DEFAULT 0, size INTEGER DEFAULT 0, sha256 TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, uid INTEGER, event TEXT, created INTEGER NOT NULL);
    """)
    # Migrate older DBs safely.
    cols = {r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()}
    if "plan" not in cols:
        c.execute("ALTER TABLE payments ADD COLUMN plan TEXT NOT NULL DEFAULT 'ALL_2500'")
    if "updated" not in cols:
        c.execute("ALTER TABLE payments ADD COLUMN updated INTEGER NOT NULL DEFAULT 0")
    if "proof_file" not in cols:
        c.execute("ALTER TABLE payments ADD COLUMN proof_file TEXT DEFAULT ''")
    if "proof_message_id" not in cols:
        c.execute("ALTER TABLE payments ADD COLUMN proof_message_id INTEGER DEFAULT 0")
    c.execute("UPDATE payments SET updated=created WHERE updated=0")
    c.execute("UPDATE jobs SET status='queued', updated=? WHERE status='processing'", (int(time.time()),))
    c.commit(); c.close()


def is_owner(uid):
    return int(uid) in OWNER_IDS


def entitlement_ok(uid, kind):
    if is_owner(uid):
        return True
    now = int(time.time())
    c = db()
    rows = c.execute("SELECT plan,until FROM entitlements WHERE uid=? AND until>?", (uid, now)).fetchall()
    c.close()
    for r in rows:
        if r["plan"] == "ALL_2500":
            return True
        if r["plan"] == "ENCODE_300" and kind == "encode":
            return True
        if r["plan"] == "UP2K_350" and kind == "upscale_2k":
            return True
        if r["plan"] == "UP4K_500" and kind == "upscale_4k":
            return True
        if r["plan"] == "UP8K_1400" and kind == "upscale_8k":
            return True
    return False


def access_ok(uid):
    # Compatibility helper: any active paid entitlement unlocks basic access.
    return is_owner(uid) or entitlement_ok(uid, "encode") or entitlement_ok(uid, "upscale_2k") or entitlement_ok(uid, "upscale_4k") or entitlement_ok(uid, "upscale_8k")


def touch_user(uid):
    c = db(); c.execute("INSERT OR IGNORE INTO users(uid, created) VALUES(?,?)", (uid, int(time.time()))); c.commit(); c.close()


def event(jid, uid, text):
    c = db(); c.execute("INSERT INTO events(job_id,uid,event,created) VALUES(?,?,?,?)", (jid, uid, text[:1000], int(time.time()))); c.commit(); c.close()


def safe_name(name):
    stem = Path(name or "video").stem
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .")[:160] or "video"


def ffprobe(path):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        return json.loads(p.stdout or "{}")
    except Exception:
        return {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def kb(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows])


def plan_keyboard():
    return kb([
        [(PLANS["ENCODE_300"]["label"], "buy:ENCODE_300")],
        [(PLANS["UP2K_350"]["label"], "buy:UP2K_350")],
        [(PLANS["UP4K_500"]["label"], "buy:UP4K_500")],
        [(PLANS["UP8K_1400"]["label"], "buy:UP8K_1400")],
        [(PLANS["ALL_2500"]["label"], "buy:ALL_2500")],
        [("📩 Contact Admin", "support")],
        [("❌ Close", "cancel")],
    ])


def owner_home_keyboard():
    return kb([
        [("🎬 Encode", "cmd:encode"), ("✨ Upscale", "cmd:upscale")],
        [("🔥 Hybrid", "cmd:hybrid"), ("📊 Jobs", "jobs")],
        [("💳 Payment Requests", "payments"), ("📩 Support Inbox", "support_inbox")],
        [("❤️ Health", "health")],
    ])


async def start(update, context):
    uid = update.effective_user.id; touch_user(uid)
    if is_owner(uid):
        await update.message.reply_text(
            "👑 *VIKKY Encoder — OWNER*\n\n"
            "♾️ Lifetime FREE access\n"
            "🎬 Encoding: FREE\n✨ 2K/4K/8K Upscale: FREE\n🔥 Hybrid: FREE\n\n"
            "You never need to pay. Use the Owner Panel below.",
            parse_mode="Markdown", reply_markup=owner_home_keyboard())
        return
    await update.message.reply_text(
        "🎞️ *VIKKY Encoder*\n\n"
        "🏆 Best-quality video encoding & AI upscaling service\n"
        "🎬 Encoding • 2K • 4K • 8K • Hybrid\n"
        "🎞️ Final output: *MKV only*\n\n"
        "🔒 Paid processing is required.\n"
        "Choose exactly what you want below.\n"
        "\n📌 Payment is *manual verification only*. Access is never activated automatically.",
        parse_mode="Markdown", reply_markup=plan_keyboard())


async def pay(update, context):
    if is_owner(update.effective_user.id):
        await update.message.reply_text("👑 Owner access is lifetime FREE. No payment is required.")
        return
    await update.message.reply_text("💳 Select the service you want to purchase:", reply_markup=plan_keyboard())


async def show_payment_request(q, context, plan_code):
    uid = q.from_user.id; plan = PLANS[plan_code]; touch_user(uid)
    if is_owner(uid):
        await q.edit_message_text("👑 Owner access is FREE. Payment is disabled for owners.")
        return
    pid = uuid.uuid4().hex[:12].upper(); now = int(time.time()); payload = f"VIKKY-{pid}"
    c = db(); c.execute("INSERT INTO payments(id,uid,plan,payload,status,created,updated) VALUES(?,?,?,?,?,?,?)", (pid,uid,plan_code,payload,"awaiting_qr",now,now)); c.commit(); c.close()
    await q.edit_message_text(
        f"💳 *{plan['label']}*\n\n"
        f"Your request has been sent to the owner for QR approval.\n"
        f"🧾 Request: `{pid}`\n\n"
        "⏳ *QR is NOT sent automatically.*\n"
        "The owner must approve the QR request first.\n\n"
        "After payment, use the button below and send your proof. Access is activated only after manual owner verification.",
        parse_mode="Markdown", reply_markup=kb([[('📷 Request QR from Admin', f'qrreq:{pid}')], [('⬅️ Plans', 'paymenu')]])
    )
    for oid in OWNER_IDS:
        try:
            await context.bot.send_message(oid, f"💳 PAYMENT REQUEST `{pid}`\nUser ID: `{uid}`\nPlan: *{plan['label']}*\n\nApprove QR or reject:", parse_mode="Markdown", reply_markup=kb([[('✅ Send QR', f'qrapprove:{pid}'), ('❌ Reject', f'qrreject:{pid}')]]))
        except Exception:
            pass


async def request_qr(q, context, pid):
    uid=q.from_user.id
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=? AND uid=?",(pid,uid)).fetchone(); c.close()
    if not r: await q.edit_message_text("❌ Payment request not found."); return
    if r["status"] not in ("awaiting_qr", "qr_requested"):
        await q.edit_message_text("ℹ️ This payment request is already processed or closed."); return
    now=int(time.time()); c=db(); c.execute("UPDATE payments SET status='qr_requested',updated=? WHERE id=?",(now,pid)); c.commit(); c.close()
    await q.edit_message_text(f"⏳ QR request `{pid}` sent to the owner. Wait for approval.",parse_mode="Markdown")
    for oid in OWNER_IDS:
        try:
            await context.bot.send_message(oid, f"📷 QR requested for `{pid}` by user `{uid}`. Approve to send the configured QR.", parse_mode="Markdown", reply_markup=kb([[('✅ Send QR', f'qrapprove:{pid}'), ('❌ Reject', f'qrreject:{pid}')]]))
        except Exception: pass


async def approve_qr(q, context, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if not r: c.close(); await q.edit_message_text("❌ Request not found."); return
    c.execute("UPDATE payments SET status='qr_sent',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    if not QR_PATH.exists():
        await q.edit_message_text(f"⚠️ QR file is not installed. Put your QR image at:\n`{QR_PATH}`\nthen retry QR approval.",parse_mode="Markdown"); return
    caption = f"📷 Payment QR\nPlan: {PLANS[r['plan']]['label']}\nUPI: {FAMPAY_UPI or 'configured privately'}\nRequest: {pid}\n\nAfter payment tap *I've Paid* and send proof."
    try:
        await context.bot.send_photo(r["uid"], photo=str(QR_PATH), caption=caption, parse_mode="Markdown", reply_markup=kb([[('✅ I’ve Paid', f'paid:{pid}')]]))
        await q.edit_message_text(f"✅ QR sent to user for `{pid}`. Your owner ID/username was not revealed.",parse_mode="Markdown")
    except Exception as e:
        await q.edit_message_text(f"❌ Could not send QR: {str(e)[:500]}")


async def reject_qr(q, context, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT uid FROM payments WHERE id=?",(pid,)).fetchone()
    if not r: c.close(); await q.edit_message_text("❌ Request not found."); return
    c.execute("UPDATE payments SET status='qr_rejected',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    await context.bot.send_message(r["uid"], f"❌ QR request `{pid}` was not approved. Use Contact Admin if you need help.",parse_mode="Markdown",reply_markup=kb([[('📩 Contact Admin','support')]]))
    await q.edit_message_text(f"❌ QR request `{pid}` rejected.")


async def mark_paid(q, context, pid):
    uid=q.from_user.id; c=db(); r=c.execute("SELECT * FROM payments WHERE id=? AND uid=?",(pid,uid)).fetchone()
    if not r: c.close(); await q.edit_message_text("❌ Payment request not found."); return
    c.execute("UPDATE payments SET status='proof_pending',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    context.user_data["proof_payment"] = pid
    await q.edit_message_text(f"🧾 Request `{pid}` marked as paid.\n\nNow send your payment proof (screenshot/photo or transaction text).\n\n⏳ Access remains LOCKED until owner verification.",parse_mode="Markdown")


async def proof_media(update, context):
    pid=context.user_data.get("proof_payment")
    if not pid: return False
    uid=update.effective_user.id; c=db(); r=c.execute("SELECT * FROM payments WHERE id=? AND uid=?",(pid,uid)).fetchone()
    if not r: c.close(); return False
    proof_dir=BASE/"config"/"payment_proofs"; proof_dir.mkdir(parents=True,exist_ok=True)
    fname=f"{pid}_{int(time.time())}"
    obj=update.message.photo[-1] if update.message.photo else update.message.document
    if obj:
        ext=".jpg" if update.message.photo else (Path(getattr(obj,"file_name","")).suffix or ".bin")
        path=proof_dir/(fname+ext)
        f=await context.bot.get_file(obj.file_id); await f.download_to_drive(custom_path=str(path)); stored=str(path)
    else:
        stored="text-proof"
    c.execute("UPDATE payments SET status='proof_submitted',updated=?,proof_file=?,proof_message_id=? WHERE id=?",(int(time.time()),stored,update.message.message_id,pid)); c.commit(); c.close()
    context.user_data.pop("proof_payment",None)
    await update.message.reply_text(f"✅ Proof received for `{pid}`.\n⏳ Owner will verify manually. No access is activated automatically.",parse_mode="Markdown")
    for oid in OWNER_IDS:
        try:
            await context.bot.send_message(oid,f"🧾 PAYMENT PROOF `{pid}`\nUser: `{uid}`\nPlan: *{PLANS[r['plan']]['label']}*\nProof stored securely.\n\nApprove only after you verify payment.",parse_mode="Markdown",reply_markup=kb([[('✅ PAID — Grant',f'paidapprove:{pid}'),('❌ Reject',f'paidreject:{pid}')]]))
            if obj: await context.bot.forward_message(oid, uid, update.message.message_id)
        except Exception: pass
    return True


async def support_start(q, context):
    context.user_data["support_mode"] = True
    await q.edit_message_text("📩 *Contact Admin*\n\nSend your message now. It will be delivered to the owner through the bot.\n\n🔐 Your private owner ID/contact details are not revealed.",parse_mode="Markdown",reply_markup=kb([[('❌ Cancel','cancel')]]))


async def support_message(update, context):
    if not context.user_data.get("support_mode"): return False
    uid=update.effective_user.id
    text=(update.message.text or update.message.caption or "[media message]")[:4000]
    rid=uuid.uuid4().hex[:10].upper(); now=int(time.time())
    c=db(); c.execute("INSERT INTO support_requests(id,uid,text,status,created,updated) VALUES(?,?,?,?,?,?)",(rid,uid,text,"open",now,now)); c.commit(); c.close()
    context.user_data.pop("support_mode",None)
    await update.message.reply_text(f"✅ Message sent to Admin.\nRequest ID: `{rid}`\n\nThe owner will reply through the bot.",parse_mode="Markdown")
    for oid in OWNER_IDS:
        try:
            await context.bot.send_message(oid,f"📩 SUPPORT `{rid}`\nUser: `{uid}`\n\n{text}\n\nReply with:\n`/reply {rid} your message`",parse_mode="Markdown")
            await context.bot.forward_message(oid,uid,update.message.message_id)
        except Exception: pass
    return True


async def reply_support(update, context):
    if not is_owner(update.effective_user.id): return
    if len(context.args)<2: await update.message.reply_text("Usage: /reply REQUEST_ID message"); return
    rid=context.args[0]; msg=" ".join(context.args[1:])[:4000]
    c=db(); r=c.execute("SELECT uid FROM support_requests WHERE id=?",(rid,)).fetchone()
    if not r: c.close(); await update.message.reply_text("❌ Request not found."); return
    c.execute("UPDATE support_requests SET status='replied',updated=? WHERE id=?",(int(time.time()),rid)); c.commit(); c.close()
    await context.bot.send_message(r["uid"],f"💬 *Admin reply*\n\n{msg}",parse_mode="Markdown")
    await update.message.reply_text(f"✅ Reply sent for `{rid}`.",parse_mode="Markdown")


async def paid_approve(q, context, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone(); c.close()
    if not r: await q.edit_message_text("❌ Payment not found."); return
    if r["status"] != "proof_submitted":
        await q.edit_message_text("⚠️ Proof is not submitted or request already processed."); return
    # Owner must explicitly select the entitlement before the final confirmation.
    buttons=[]
    for code,plan in PLANS.items():
        buttons.append([(f"{plan['label']}",f"grantplan:{pid}:{code}")])
    buttons.append([("❌ Reject",f"paidreject:{pid}")])
    await q.edit_message_text(f"🧾 *VERIFY PAYMENT*\nRequest `{pid}`\nUser `{r['uid']}`\n\nSelect exactly what you are granting. Nothing is activated yet.",parse_mode="Markdown",reply_markup=kb(buttons))

async def choose_grant_plan(q, context, pid, plan_code):
    if not is_owner(q.from_user.id): return
    if plan_code not in PLANS: return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone(); c.close()
    if not r or r["status"] != "proof_submitted":
        await q.edit_message_text("⚠️ Payment is no longer awaiting verification."); return
    plan=PLANS[plan_code]
    await q.edit_message_text(
        f"⚠️ *FINAL CONFIRMATION*\n\nUser: `{r['uid']}`\nRequest: `{pid}`\nSelected: *{plan['label']}*\nDuration: {plan['days']} days\n\nAccess will be activated ONLY after you press Confirm.",
        parse_mode="Markdown", reply_markup=kb([[('✅ CONFIRM & GRANT',f"grantconfirm:{pid}:{plan_code}")],[('⬅️ Change Plan',f"paidapprove:{pid}"),('❌ Reject',f"paidreject:{pid}")]]))

async def confirm_grant(q, context, pid, plan_code):
    if not is_owner(q.from_user.id): return
    if plan_code not in PLANS: return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if not r: c.close(); await q.edit_message_text("❌ Payment not found."); return
    if r["status"] != "proof_submitted":
        c.close(); await q.edit_message_text("⚠️ Already processed or not ready."); return
    plan=PLANS[plan_code]; until=int(time.time())+plan["days"]*86400
    c.execute("INSERT OR REPLACE INTO entitlements(uid,plan,until) VALUES(?,?,?)",(r["uid"],plan_code,until))
    c.execute("UPDATE users SET access_until=MAX(access_until,?) WHERE uid=?",(until,r["uid"]))
    c.execute("UPDATE payments SET status='paid_verified',plan=?,updated=? WHERE id=?",(plan_code,int(time.time()),pid)); c.commit(); c.close()
    await context.bot.send_message(r["uid"],f"✅ *Payment VERIFIED*\n\n{plan['label']}\n📅 Access active for {plan['days']} days.\n🔐 Activated manually by Admin.\n\nYou can now use the purchased service.",parse_mode="Markdown",reply_markup=kb([[('🎬 Open VIKKY','home')]]))
    await q.edit_message_text(f"✅ *VERIFIED + ACCESS GRANTED*\nRequest `{pid}`\nGranted: {plan['label']}",parse_mode="Markdown")


async def paid_reject(q, context, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT uid FROM payments WHERE id=?",(pid,)).fetchone()
    if not r: c.close(); await q.edit_message_text("❌ Payment not found."); return
    c.execute("UPDATE payments SET status='rejected',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    await context.bot.send_message(r["uid"],f"❌ Payment proof `{pid}` was not verified.\nNo access was granted.\n\nContact Admin if you believe this is an error.",parse_mode="Markdown",reply_markup=kb([[('📩 Contact Admin','support')]]))
    await q.edit_message_text(f"❌ Payment rejected: `{pid}`",parse_mode="Markdown")


async def payments(update, context):
    if not is_owner(update.effective_user.id): return
    c=db(); rows=c.execute("SELECT id,uid,plan,status,created FROM payments ORDER BY created DESC LIMIT 30").fetchall(); c.close()
    text="💳 *Payment Requests*\n\n"+"\n".join(f"`{r['id']}` | {r['uid']} | {PLANS.get(r['plan'],{}).get('label',r['plan'])} | {r['status']}" for r in rows) if rows else "No payment requests."
    await update.message.reply_text(text,parse_mode="Markdown")


async def status(update, context):
    uid=update.effective_user.id; touch_user(uid)
    if is_owner(uid):
        await update.message.reply_text("👑 OWNER — Lifetime FREE access to everything."); return
    now=int(time.time()); c=db(); rows=c.execute("SELECT plan,until FROM entitlements WHERE uid=? AND until>?",(uid,now)).fetchall(); c.close()
    if not rows: await update.message.reply_text("🔒 No active paid service access.",reply_markup=plan_keyboard()); return
    text="✅ *Active Services*\n\n"+"\n".join(f"• {PLANS[r['plan']]['label']} — until {datetime.fromtimestamp(r['until'],timezone.utc).date().isoformat()}" for r in rows)
    await update.message.reply_text(text,parse_mode="Markdown")


async def show_mode(target, mode):
    rows=[]
    for x in MODES[mode]:
        allowed = mode=="encode" or (x=="2K_AI" and entitlement_ok(target.from_user.id,"upscale_2k")) or (x=="4K_AI" and entitlement_ok(target.from_user.id,"upscale_4k")) or (x=="8K_AI" and entitlement_ok(target.from_user.id,"upscale_8k"))
        if mode=="hybrid": allowed=entitlement_ok(target.from_user.id,"upscale_4k") or entitlement_ok(target.from_user.id,"upscale_8k")
        label=x if allowed else f"🔒 {x}"
        rows.append([(label,f"profile:{mode}:{x}")])
    rows.append([('⬅️ Home','home'),('❌ Cancel','cancel')])
    await target.edit_message_text(f"Select *{mode}* profile:",parse_mode="Markdown",reply_markup=kb(rows))


async def menu(update, context, mode):
    uid=update.effective_user.id
    kind="encode" if mode=="encode" else None
    if mode=="encode" and not entitlement_ok(uid,"encode"):
        await update.message.reply_text("🔒 Encoding access not active. Choose Encoding — ₹300.",reply_markup=plan_keyboard()); return
    if mode=="upscale" and not (entitlement_ok(uid,"upscale_2k") or entitlement_ok(uid,"upscale_4k") or entitlement_ok(uid,"upscale_8k")):
        await update.message.reply_text("🔒 Upscale access not active. Choose a 2K/4K/8K plan.",reply_markup=plan_keyboard()); return
    if mode=="hybrid" and not (entitlement_ok(uid,"upscale_4k") or entitlement_ok(uid,"upscale_8k")):
        await update.message.reply_text("🔒 Hybrid requires 4K/8K Upscale access or Monthly Full Bot Access.",reply_markup=plan_keyboard()); return
    await update.message.reply_text(f"Select *{mode}* profile:",parse_mode="Markdown",reply_markup=kb([[ (x,f"profile:{mode}:{x}") ] for x in MODES[mode]]+[[('⬅️ Home','home'),('❌ Cancel','cancel')]]))


async def encode_cmd(u,c): await menu(u,c,"encode")
async def upscale_cmd(u,c): await menu(u,c,"upscale")
async def hybrid_cmd(u,c): await menu(u,c,"hybrid")


async def callback(update, context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; data=q.data
    if data=="home": await start_callback(q,context); return
    if data=="cancel": context.user_data.clear(); await q.edit_message_text("❌ Cancelled."); return
    if data in ("pay","paymenu"): await q.edit_message_text("💳 Select the service you want to purchase:",reply_markup=plan_keyboard()); return
    if data=="support": await support_start(q,context); return
    if data=="payments":
        if is_owner(uid): await payments_callback(q,context)
        return
    if data=="support_inbox":
        if is_owner(uid): await q.edit_message_text("📩 Support replies are sent with:\n`/reply REQUEST_ID your message`",parse_mode="Markdown")
        return
    if data=="health":
        if is_owner(uid): await q.edit_message_text(f"VIKKY HEALTH\nffmpeg={bool(shutil.which('ffmpeg'))}\nffprobe={bool(shutil.which('ffprobe'))}\nDB={DB.exists()}\nworker={'external' if WORKER_CMD else 'MKV FFmpeg fallback'}\nowners={len(OWNER_IDS)}\noutput=MKV-only")
        return
    if data=="jobs":
        if is_owner(uid): await jobs_callback(q,context)
        return
    if data.startswith("buy:"):
        await show_payment_request(q,context,data.split(":",1)[1]); return
    if data.startswith("qrreq:"): await request_qr(q,context,data.split(":",1)[1]); return
    if data.startswith("qrapprove:"): await approve_qr(q,context,data.split(":",1)[1]); return
    if data.startswith("qrreject:"): await reject_qr(q,context,data.split(":",1)[1]); return
    if data.startswith("paid:"): await mark_paid(q,context,data.split(":",1)[1]); return
    if data.startswith("paidapprove:"): await paid_approve(q,context,data.split(":",1)[1]); return
    if data.startswith("grantplan:"):
        _,pid,plan=data.split(":",2); await choose_grant_plan(q,context,pid,plan); return
    if data.startswith("grantconfirm:"):
        _,pid,plan=data.split(":",2); await confirm_grant(q,context,pid,plan); return
    if data.startswith("paidreject:"): await paid_reject(q,context,data.split(":",1)[1]); return
    if data.startswith("cmd:"):
        mode=data.split(":",1)[1]
        if mode=="encode" and not entitlement_ok(uid,"encode"): await q.edit_message_text("🔒 Encoding access required.",reply_markup=plan_keyboard()); return
        if mode in ("upscale","hybrid") and not (entitlement_ok(uid,"upscale_2k") or entitlement_ok(uid,"upscale_4k") or entitlement_ok(uid,"upscale_8k")): await q.edit_message_text("🔒 Paid access required.",reply_markup=plan_keyboard()); return
        await show_mode(q,mode); return
    if data.startswith("profile:"):
        _,mode,profile=data.split(":",2)
        if not is_owner(uid):
            needed="encode" if mode=="encode" else ("upscale_2k" if profile=="2K_AI" else "upscale_4k" if profile in ("4K_AI","4K_HYBRID") else "upscale_8k")
            if not entitlement_ok(uid,needed): await q.edit_message_text("🔒 This profile is not included in your active purchase.",reply_markup=plan_keyboard()); return
        context.user_data["selection"]={"mode":mode,"profile":profile}
        await q.edit_message_text(f"Selected: *{profile}*\n\n📤 Send the source video/file now.\n\n⚠️ Final output is always `.mkv`.",parse_mode="Markdown",reply_markup=kb([[('⬅️ Back',f'cmd:{mode}'),('❌ Cancel','cancel')]])); return


async def start_callback(q,context):
    uid=q.from_user.id
    if is_owner(uid): await q.edit_message_text("👑 *OWNER / LIFETIME FREE*\n\nEverything is unlocked.",parse_mode="Markdown",reply_markup=owner_home_keyboard())
    else: await q.edit_message_text("🎞️ *VIKKY Encoder*\n\n🏆 Best-quality encoding & AI upscaling\n🎞️ Final output: MKV only\n\nChoose your service:",parse_mode="Markdown",reply_markup=plan_keyboard())

async def payments_callback(q,context):
    c=db(); rows=c.execute("SELECT id,uid,plan,status FROM payments ORDER BY created DESC LIMIT 20").fetchall(); c.close()
    if not rows: await q.edit_message_text("💳 No payment requests.",reply_markup=owner_home_keyboard()); return
    rowsbtn=[]
    for r in rows:
        rowsbtn.append([(f"{r['id']} • {r['status']}",f"pview:{r['id']}")])
    rowsbtn.append([('⬅️ Owner','home')]); await q.edit_message_text("💳 Payment Requests",reply_markup=kb(rowsbtn))

async def jobs_callback(q,context):
    c=db(); rows=c.execute("SELECT id,uid,mode,profile,status,progress FROM jobs ORDER BY created DESC LIMIT 30").fetchall(); c.close()
    await q.edit_message_text("\n".join(f"{x['id'][:8]} | {x['uid']} | {x['mode']} | {x['profile']} | {x['status']} | {x['progress']}%" for x in rows) or "No jobs.",reply_markup=owner_home_keyboard())


async def media(update, context):
    if await proof_media(update,context): return
    if await support_message(update,context): return
    uid=update.effective_user.id
    sel=context.user_data.get("selection")
    if not sel: return
    if not is_owner(uid):
        needed="encode" if sel["mode"]=="encode" else ("upscale_2k" if sel["profile"]=="2K_AI" else "upscale_4k" if sel["profile"] in ("4K_AI","4K_HYBRID") else "upscale_8k")
        if not entitlement_ok(uid,needed): await update.message.reply_text("🔒 This profile is not included in your active purchase."); return
    obj=update.message.document or update.message.video
    if not obj: return
    name=getattr(obj,"file_name",None) or f"video_{getattr(obj,'file_unique_id',uuid.uuid4().hex)}"; size=int(getattr(obj,"file_size",0) or 0)
    if size>MAX_INPUT_GB*1024**3: await update.message.reply_text(f"❌ Input exceeds {MAX_INPUT_GB:g} GB configured ceiling."); return
    jid=uuid.uuid4().hex; work=TEMP/jid; work.mkdir(parents=True,exist_ok=True); path=work/(safe_name(name)+Path(name).suffix.lower())
    await update.message.reply_text(f"📥 `{jid[:8]}` accepted.\n⏳ Downloading…",parse_mode="Markdown")
    try:
        tg=await context.bot.get_file(obj.file_id); await tg.download_to_drive(custom_path=str(path)); meta=ffprobe(path)
        if not meta: raise RuntimeError("FFprobe could not read the media.")
        now=int(time.time()); duration=float(meta.get("format",{}).get("duration") or 0); fsize=path.stat().st_size
        c=db(); c.execute("INSERT INTO jobs(id,uid,mode,profile,status,progress,input,output,error,created,updated,duration,size) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,uid,sel["mode"],sel["profile"],"queued",0,str(path),"","",now,now,duration,fsize)); c.commit(); c.close(); event(jid,uid,"queued")
        await update.message.reply_text(f"🟢 `{jid[:8]}` queued.\n🔴 Live processing updates will follow.",parse_mode="Markdown")
        asyncio.create_task(run_job(context.application,jid))
    except Exception as e:
        shutil.rmtree(work,ignore_errors=True); await update.message.reply_text(f"❌ Input failed: {str(e)[:1000]}")


async def set_progress(jid,pct):
    c=db(); c.execute("UPDATE jobs SET progress=?,updated=? WHERE id=?",(max(0,min(99,int(pct))),int(time.time()),jid)); c.commit(); c.close()

def progress_from_ffmpeg(line,duration):
    m=re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",line)
    if not m or not duration:return None
    sec=int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3)); return max(5,min(98,int(sec/duration*90)+5))


async def run_job(app,jid):
    c=db(); r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone(); c.close()
    if not r:return
    inp=Path(r["input"]); out=OUT/f"{safe_name(inp.name)}.{r['profile']}.By.VIKKY.mkv"; out=out.with_suffix('.mkv')
    await set_progress(jid,2); event(jid,r["uid"],"processing")
    try:
        duration=float(r["duration"] or 0)
        if WORKER_CMD: cmd=WORKER_CMD.format(input=str(inp),output=str(out),mode=r["mode"],profile=r["profile"])
        else: cmd=f'ffmpeg -hide_banner -y -i "{inp}" -map 0 -c:v libx265 -preset medium -crf 18 -pix_fmt yuv420p10le -c:a copy -c:s copy -c:d copy -f matroska "{out}"'
        proc=await asyncio.create_subprocess_shell(cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        last=0; last_live=0
        while True:
            raw=await proc.stdout.readline()
            if not raw:break
            line=raw.decode('utf-8','ignore').strip(); pct=progress_from_ffmpeg(line,duration)
            if pct is not None: await set_progress(jid,pct); last=pct
            if time.time()-last_live>=LIVE_INTERVAL:
                last_live=time.time(); await app.bot.send_message(r["uid"],f"⚙️ `{jid[:8]}` {r['mode']} / {r['profile']}\n📈 Progress: {last or 5}%\n🎯 Output: MKV only",parse_mode='Markdown')
        rc=await proc.wait()
        if rc!=0 or not out.exists() or out.stat().st_size==0:raise RuntimeError(f"Worker/FFmpeg failed with exit code {rc}")
        if out.suffix.lower()!='.mkv':raise RuntimeError('Safety check failed: output is not MKV.')
        meta=ffprobe(out); digest=sha256(out); report=REPORTS/f"{jid}.json"
        report.write_text(json.dumps({"job_id":jid,"status":"done","output":out.name,"bytes":out.stat().st_size,"sha256":digest,"media":meta,"verified_mkv":True},indent=2),encoding='utf-8')
        c=db(); c.execute("UPDATE jobs SET status='done',progress=100,output=?,sha256=?,size=?,updated=? WHERE id=?",(str(out),digest,out.stat().st_size,int(time.time()),jid)); c.commit(); c.close(); event(jid,r["uid"],'done')
        await app.bot.send_message(r["uid"],f"✅ `{jid[:8]}` COMPLETE\n📦 `{out.name}`\n🎞️ MKV verified\n🔐 SHA256 `{digest}`",parse_mode='Markdown')
        if out.stat().st_size<=50*1024*1024: await app.bot.send_document(r["uid"],document=str(out),caption=f"🎬 {out.name}")
        else: await app.bot.send_message(r["uid"],"📦 Verified MKV is larger than Telegram cloud-bot upload limit. Keep/use the configured external uploader or storage worker for delivery.")
    except Exception as e:
        c=db(); c.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=?",(str(e)[:2000],int(time.time()),jid)); c.commit(); c.close(); event(jid,r["uid"],f'failed: {e}')
        await app.bot.send_message(r["uid"],f"❌ `{jid[:8]}` FAILED\n{str(e)[:1200]}",parse_mode='Markdown')


async def grant(update,context):
    if not is_owner(update.effective_user.id):return
    if len(context.args)<2:await update.message.reply_text('/grant USER_ID DAYS PLAN_CODE');return
    uid=int(context.args[0]);days=int(context.args[1]);plan=context.args[2] if len(context.args)>2 else 'ALL_2500'
    if plan not in PLANS:await update.message.reply_text('❌ Unknown plan.');return
    until=int(time.time())+days*86400;touch_user(uid);c=db();c.execute('INSERT OR REPLACE INTO entitlements(uid,plan,until) VALUES(?,?,?)',(uid,plan,until));c.execute('UPDATE users SET access_until=MAX(access_until,?) WHERE uid=?',(until,uid));c.commit();c.close();await update.message.reply_text(f'✅ Granted {PLANS[plan]["label"]} for {days} days.')

async def revoke(update,context):
    if not is_owner(update.effective_user.id):return
    if not context.args:await update.message.reply_text('/revoke USER_ID [PLAN_CODE]');return
    uid=int(context.args[0]);c=db()
    if len(context.args)>1:c.execute('DELETE FROM entitlements WHERE uid=? AND plan=?',(uid,context.args[1]))
    else:c.execute('DELETE FROM entitlements WHERE uid=?',(uid,))
    c.commit();c.close();await update.message.reply_text('✅ Access revoked.')

async def uploader(update,context):
    if not is_owner(update.effective_user.id):return
    if len(context.args)<2:await update.message.reply_text('/uploader USER_ID on|off');return
    c=db();c.execute('INSERT OR IGNORE INTO users(uid,created) VALUES(?,?)',(int(context.args[0]),int(time.time())));c.execute('UPDATE users SET uploader=? WHERE uid=?',(1 if context.args[1].lower()=='on' else 0,int(context.args[0])));c.commit();c.close();await update.message.reply_text('✅ Uploader flag updated.')

async def health(update,context):
    if not is_owner(update.effective_user.id):return
    await update.message.reply_text(f"VIKKY HEALTH\nffmpeg={bool(shutil.which('ffmpeg'))}\nffprobe={bool(shutil.which('ffprobe'))}\nDB={DB.exists()}\nQR={QR_PATH.exists()}\nworker={'external' if WORKER_CMD else 'MKV FFmpeg fallback'}\nowners={len(OWNER_IDS)}\noutput=MKV-only")

async def jobs(update,context):
    if not is_owner(update.effective_user.id):return
    c=db();rows=c.execute('SELECT id,uid,mode,profile,status,progress FROM jobs ORDER BY created DESC LIMIT 30').fetchall();c.close();await update.message.reply_text('\n'.join(f"{x['id'][:8]} | {x['uid']} | {x['mode']} | {x['profile']} | {x['status']} | {x['progress']}%" for x in rows) or 'No jobs.')

async def retry(update,context):
    if not is_owner(update.effective_user.id) or not context.args:return
    jid=context.args[0];c=db();r=c.execute('SELECT uid FROM jobs WHERE id=?',(jid,)).fetchone()
    if not r:c.close();await update.message.reply_text('❌ Job not found.');return
    c.execute("UPDATE jobs SET status='queued',progress=0,error='',updated=? WHERE id=?",(int(time.time()),jid));c.commit();c.close();asyncio.create_task(run_job(context.application,jid));await update.message.reply_text('🔁 Job requeued.')

async def cancel(update,context):
    uid=update.effective_user.id
    if not context.args:await update.message.reply_text('/cancel JOB_ID');return
    jid=context.args[0];c=db();r=c.execute('SELECT uid,status FROM jobs WHERE id=?',(jid,)).fetchone()
    if not r or (r['uid']!=uid and not is_owner(uid)):c.close();await update.message.reply_text('❌ Not allowed / not found.');return
    c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?",(int(time.time()),jid));c.commit();c.close();await update.message.reply_text('🛑 Job marked cancelled.')

async def cleanup_loop(app):
    # Bot API does not expose read receipts to bots. We therefore use a conservative 24h expiry for support chat messages.
    while True:
        try:
            cutoff=int(time.time())-CONTACT_DELETE_HOURS*3600
            c=db(); rows=c.execute('SELECT id,uid,owner_message_ids FROM support_requests WHERE updated<? AND status NOT IN (\'deleted\',)',(cutoff,)).fetchall()
            for r in rows:
                try:
                    await app.bot.delete_message(r['uid'], int(r['owner_message_ids'])) if r['owner_message_ids'].isdigit() else None
                except Exception: pass
                c.execute("UPDATE support_requests SET status='deleted',updated=? WHERE id=?",(int(time.time()),r['id']))
            c.commit();c.close()
        except Exception: pass
        await asyncio.sleep(3600)

async def error_handler(update,context):print('BOT_ERROR',repr(context.error))

async def post_init(app):
    asyncio.create_task(cleanup_loop(app))

def main():
    if not BOT_TOKEN:raise SystemExit('BOT_TOKEN is missing; use environment/GitHub Secrets.')
    if len(OWNER_IDS)!=2:raise SystemExit('Set exactly two OWNER_IDS.')
    init_db();app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    for cmd,fn in [("start",start),("encode",encode_cmd),("upscale",upscale_cmd),("hybrid",hybrid_cmd),("pay",pay),("status",status),("grant",grant),("revoke",revoke),("uploader",uploader),("health",health),("jobs",jobs),("retry",retry),("cancel",cancel),("reply",reply_support),("payments",payments)]:app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VIDEO,media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,media))
    app.add_error_handler(error_handler)
    print(f'{APP} running | MKV-only | manual payment verification | persistent SQLite queue')
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=='__main__':main()
