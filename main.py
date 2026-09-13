from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from hydrogram import Client, enums, filters, idle
from hydrogram.handlers import CallbackQueryHandler, MessageHandler
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config.weekly_quota import (
    ensure_schema as ensure_quota_schema,
    get_usage as quota_usage,
    can_consume as quota_can_consume,
    consume as quota_consume,
)
from workers.downloader import download_url, extract_url

load_dotenv()

APP = "VIKKY Encoder"
BASE = Path(__file__).resolve().parent
DB = BASE / "config" / "vikky.db"
TEMP = BASE / "temp"
OUT = BASE / "outputs"
REPORTS = BASE / "logs"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(CHANNEL_ID_RAW) if re.fullmatch(r"-?\d+", CHANNEL_ID_RAW) else (CHANNEL_ID_RAW or None)
MAX_INPUT_GB = float(os.getenv("VIKKY_MAX_INPUT_GB", "60"))
WORKER_CMD = os.getenv("VIKKY_WORKER_CMD", "").strip()
LIVE_INTERVAL = max(2, int(os.getenv("VIKKY_LIVE_INTERVAL", "5")))
FAMPAY_UPI = os.getenv("FAMPAY_UPI", "").strip()
WEEKLY_QUOTA_GB = float(os.getenv("VIKKY_WEEKLY_QUOTA_GB", "200"))
WEEKLY_QUOTA_TASKS = max(1, int(os.getenv("VIKKY_WEEKLY_QUOTA_TASKS", "15")))
MAX_WORKERS = max(1, int(os.getenv("VIKKY_MAX_WORKERS", "1")))
AI_CMD = os.getenv("VIKKY_AI_CMD", "").strip()
REALESRGAN_DIR = os.getenv("REALESRGAN_DIR", str(BASE / "third_party" / "Real-ESRGAN")).strip()

PLANS = {
    "ENCODE_300": {"label": "Encoding - Rs 300", "days": 30, "kind": "encode"},
    "UP2K_350": {"label": "2K Upscale - Rs 350", "days": 30, "kind": "upscale_2k"},
    "UP4K_500": {"label": "4K Upscale - Rs 500", "days": 30, "kind": "upscale_4k"},
    "UP8K_1400": {"label": "8K Upscale - Rs 1400", "days": 30, "kind": "upscale_8k"},
    "ALL_2500": {"label": "Monthly Full Bot Access - Rs 2500", "days": 30, "kind": "all"},
}

MODES = {
    "encode": ["SMART", "3GB", "4GB", "5GB", "6GB", "7GB", "8GB", "CUSTOM"],
    "upscale": ["2K_AI", "4K_AI", "8K_AI"],
    "hybrid": ["4K_HYBRID", "8K_HYBRID"],
}

for p in (TEMP, OUT, REPORTS, DB.parent):
    p.mkdir(parents=True, exist_ok=True)

active_jobs: set[str] = set()
worker_sem = asyncio.Semaphore(MAX_WORKERS)
worker_tasks: set[asyncio.Task] = set()


def db():
    c = sqlite3.connect(DB, timeout=60)
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
    CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, uid INTEGER, provider TEXT, url TEXT, status TEXT, created INTEGER NOT NULL);
    """)
    ensure_quota_schema(c)
    cols = {r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()}
    for name, ddl in (
        ("plan", "ALTER TABLE payments ADD COLUMN plan TEXT NOT NULL DEFAULT 'ALL_2500'"),
        ("updated", "ALTER TABLE payments ADD COLUMN updated INTEGER NOT NULL DEFAULT 0"),
        ("proof_file", "ALTER TABLE payments ADD COLUMN proof_file TEXT DEFAULT ''"),
        ("proof_message_id", "ALTER TABLE payments ADD COLUMN proof_message_id INTEGER DEFAULT 0"),
    ):
        if name not in cols:
            c.execute(ddl)
    c.execute("UPDATE payments SET updated=created WHERE updated=0")
    # Jobs interrupted during a process restart become queued again.
    c.execute("UPDATE jobs SET status='queued', updated=? WHERE status='processing'", (int(time.time()),))
    c.commit()
    c.close()


def is_owner(uid: int) -> bool:
    return int(uid) in OWNER_IDS


def entitlement_ok(uid: int, kind: str) -> bool:
    if is_owner(uid):
        return True
    now = int(time.time())
    c = db()
    rows = c.execute("SELECT plan,until FROM entitlements WHERE uid=? AND until>?", (uid, now)).fetchall()
    c.close()
    for r in rows:
        if r["plan"] == "ALL_2500": return True
        if r["plan"] == "ENCODE_300" and kind == "encode": return True
        if r["plan"] == "UP2K_350" and kind == "upscale_2k": return True
        if r["plan"] == "UP4K_500" and kind == "upscale_4k": return True
        if r["plan"] == "UP8K_1400" and kind == "upscale_8k": return True
    return False


def touch_user(uid: int):
    c = db(); c.execute("INSERT OR IGNORE INTO users(uid,created) VALUES(?,?)", (uid, int(time.time()))); c.commit(); c.close()


def event(jid: str, uid: int, text: str):
    c = db(); c.execute("INSERT INTO events(job_id,uid,event,created) VALUES(?,?,?,?)", (jid, uid, text[:1000], int(time.time()))); c.commit(); c.close()


def safe_name(name: str) -> str:
    stem = Path(name or "video").stem
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .")[:160] or "video"


def ffprobe(path: Path) -> dict:
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        return json.loads(p.stdout or "{}")
    except Exception:
        return {}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def kb(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows])


def plain_kwargs():
    # Hydrogram's disabled parse mode prevents dynamic underscores from being parsed.
    return {"parse_mode": enums.ParseMode.DISABLED}


def plan_keyboard():
    return kb([
        [(PLANS["ENCODE_300"]["label"], "buy:ENCODE_300")],
        [(PLANS["UP2K_350"]["label"], "buy:UP2K_350")],
        [(PLANS["UP4K_500"]["label"], "buy:UP4K_500")],
        [(PLANS["UP8K_1400"]["label"], "buy:UP8K_1400")],
        [(PLANS["ALL_2500"]["label"], "buy:ALL_2500")],
        [("Contact Admin", "support")],
        [("Close", "cancel")],
    ])


def owner_home_keyboard():
    return kb([
        [("Encode", "cmd:encode"), ("Upscale", "cmd:upscale")],
        [("Hybrid", "cmd:hybrid"), ("Jobs", "jobs")],
        [("Payment Requests", "payments"), ("Health", "health")],
    ])


async def start(client, message):
    uid = message.from_user.id; touch_user(uid)
    if is_owner(uid):
        await message.reply_text("VIKKY Encoder - OWNER\n\nLifetime FREE access.\nEncoding, 2K, 4K, 8K and Hybrid are unlocked.", reply_markup=owner_home_keyboard(), **plain_kwargs())
    else:
        await message.reply_text("VIKKY Encoder\n\nEncoding - 2K - 4K - 8K - Hybrid\nFinal output: MKV only\n\nPaid processing is required. Payment is manual verification only.", reply_markup=plan_keyboard(), **plain_kwargs())


async def pay(client, message):
    if is_owner(message.from_user.id):
        await message.reply_text("Owner access is lifetime FREE. No payment is required.", **plain_kwargs()); return
    await message.reply_text("Select the service you want to purchase:", reply_markup=plan_keyboard(), **plain_kwargs())


async def show_payment_request(q, client, plan_code):
    uid = q.from_user.id; plan = PLANS[plan_code]; touch_user(uid)
    if is_owner(uid):
        await q.edit_message_text("Owner access is lifetime FREE. Payment is disabled for owners.", **plain_kwargs()); return
    pid = uuid.uuid4().hex[:12].upper(); now = int(time.time()); payload = f"VIKKY-{pid}"
    c = db(); c.execute("INSERT INTO payments(id,uid,plan,payload,status,created,updated) VALUES(?,?,?,?,?,?,?)", (pid, uid, plan_code, payload, "awaiting_payment", now, now)); c.commit(); c.close()
    payline = FAMPAY_UPI or "Payment ID is not configured yet"
    await q.edit_message_text(f"{plan['label']}\n\nFamPay / UPI ID:\n{payline}\n\nRequest: {pid}\n\nPay externally, then press I have Paid and send proof.\nAccess activates only after owner verification.\nNo QR code is used.", reply_markup=kb([[("I have Paid", f"paid:{pid}")], [("Contact Admin", "support")], [("Plans", "paymenu")]]), **plain_kwargs())
    for oid in OWNER_IDS:
        try:
            await client.send_message(oid, f"PAYMENT REQUEST {pid}\nUser: {uid}\nPlan: {plan['label']}\nStatus: awaiting payment", **plain_kwargs())
        except Exception:
            pass


async def mark_paid(q, client, pid):
    uid=q.from_user.id; c=db(); r=c.execute("SELECT * FROM payments WHERE id=? AND uid=?",(pid,uid)).fetchone(); c.close()
    if not r: await q.edit_message_text("Payment request not found.", **plain_kwargs()); return
    c=db(); c.execute("UPDATE payments SET status='proof_pending',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    await q.edit_message_text(f"Request {pid} is ready. Send your payment proof as a screenshot/photo or transaction text.", **plain_kwargs())


async def proof_media(client, message) -> bool:
    uid = message.from_user.id; text = (message.text or message.caption or "").strip()
    c=db(); r=c.execute("SELECT * FROM payments WHERE uid=? AND status='proof_pending' ORDER BY updated DESC LIMIT 1",(uid,)).fetchone(); c.close()
    if not r: return False
    stored = ""
    media = message.photo or message.document
    if media:
        obj = message.photo[-1] if message.photo else message.document
        path = TEMP / f"payment_{r['id']}_{message.id}"
        try:
            await message.download(file_name=str(path))
            stored = str(path)
        except Exception:
            stored = ""
    elif text:
        stored = text[:2000]
    else:
        return False
    c=db(); c.execute("UPDATE payments SET status='proof_submitted',proof_file=?,proof_message_id=?,updated=? WHERE id=?",(stored,message.id,int(time.time()),r['id'])); c.commit(); c.close()
    await message.reply_text(f"Payment proof received for {r['id']}. Access remains locked until owner verification.", **plain_kwargs())
    buttons=[[InlineKeyboardButton("VERIFY + GRANT", callback_data=f"paidapprove:{r['id']}")],[InlineKeyboardButton("REJECT", callback_data=f"paidreject:{r['id']}")]]
    for oid in OWNER_IDS:
        try:
            await client.send_message(oid, f"PAYMENT PROOF {r['id']}\nUser: {uid}\nPlan: {PLANS[r['plan']]['label']}\nVerify manually before granting.", reply_markup=InlineKeyboardMarkup(buttons), **plain_kwargs())
        except Exception: pass
    return True


async def support_start(q, client):
    await q.edit_message_text("Send your support message now.", reply_markup=kb([[('Cancel','cancel')]]), **plain_kwargs())


async def support_message(client, message) -> bool:
    # Support mode is intentionally simple: a user sends /support first, then the next text is routed.
    if not message.from_user: return False
    uid=message.from_user.id
    if not getattr(message, "text", None): return False
    c=db(); pending=c.execute("SELECT id FROM support_requests WHERE uid=? AND status='waiting' ORDER BY created DESC LIMIT 1",(uid,)).fetchone(); c.close()
    if not pending: return False
    rid=pending["id"]; text=message.text[:4000]; now=int(time.time())
    c=db(); c.execute("UPDATE support_requests SET text=?,status='open',updated=? WHERE id=?",(text,now,rid)); c.commit(); c.close()
    await message.reply_text(f"Support request {rid} sent to Admin.", **plain_kwargs())
    for oid in OWNER_IDS:
        try: await client.send_message(oid, f"SUPPORT {rid}\nUser: {uid}\n\n{text}\n\nReply with /reply {rid} your message", **plain_kwargs())
        except Exception: pass
    return True


async def support_cmd(client, message):
    uid=message.from_user.id; rid=uuid.uuid4().hex[:10].upper(); now=int(time.time()); touch_user(uid)
    c=db(); c.execute("INSERT INTO support_requests(id,uid,text,status,created,updated) VALUES(?,?,?,?,?,?)",(rid,uid,"", "waiting",now,now)); c.commit(); c.close()
    await message.reply_text(f"Support request {rid} created. Send your message now.", **plain_kwargs())


async def reply_support(client, message):
    if not is_owner(message.from_user.id): return
    args=message.text.split(maxsplit=2) if message.text else []
    if len(args)<3: await message.reply_text("Usage: /reply REQUEST_ID message", **plain_kwargs()); return
    rid,msg=args[1],args[2]; c=db(); r=c.execute("SELECT uid FROM support_requests WHERE id=?",(rid,)).fetchone(); c.close()
    if not r: await message.reply_text("Request not found.", **plain_kwargs()); return
    await client.send_message(r["uid"], f"Admin reply:\n\n{msg}", **plain_kwargs())
    await message.reply_text("Reply sent.", **plain_kwargs())


async def paid_approve(q, client, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone(); c.close()
    if not r or r["status"] not in ("proof_submitted", "proof_pending"):
        await q.edit_message_text("Proof is not submitted or request already processed.", **plain_kwargs()); return
    buttons=[[InlineKeyboardButton(p["label"], callback_data=f"grantconfirm:{pid}:{code}")] for code,p in PLANS.items()]
    await q.edit_message_text(f"VERIFY PAYMENT\nRequest: {pid}\nUser: {r['uid']}\n\nSelect the plan to grant:", reply_markup=InlineKeyboardMarkup(buttons), **plain_kwargs())


async def confirm_grant(q, client, pid, plan_code):
    if not is_owner(q.from_user.id) or plan_code not in PLANS: return
    c=db(); r=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if not r or r["status"] not in ("proof_submitted", "proof_pending"):
        c.close(); await q.edit_message_text("Already processed or not ready.", **plain_kwargs()); return
    until=int(time.time())+PLANS[plan_code]["days"]*86400
    c.execute("INSERT OR REPLACE INTO entitlements(uid,plan,until) VALUES(?,?,?)",(r["uid"],plan_code,until))
    c.execute("UPDATE users SET access_until=MAX(access_until,?) WHERE uid=?",(until,r["uid"]))
    c.execute("UPDATE payments SET status='verified',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    await client.send_message(r["uid"], f"Payment verified.\n\n{PLANS[plan_code]['label']}\nAccess active for 30 days.", **plain_kwargs())
    await q.edit_message_text(f"VERIFIED + ACCESS GRANTED\nRequest {pid}\nGranted: {PLANS[plan_code]['label']}", **plain_kwargs())


async def paid_reject(q, client, pid):
    if not is_owner(q.from_user.id): return
    c=db(); r=c.execute("SELECT uid FROM payments WHERE id=?",(pid,)).fetchone(); c.execute("UPDATE payments SET status='rejected',updated=? WHERE id=?",(int(time.time()),pid)); c.commit(); c.close()
    if r: await client.send_message(r["uid"], f"Payment proof {pid} was not verified. No access was granted.", **plain_kwargs())
    await q.edit_message_text(f"Payment rejected: {pid}", **plain_kwargs())


async def menu(client, message, mode):
    uid=message.from_user.id
    if mode=="encode" and not entitlement_ok(uid,"encode"):
        await message.reply_text("Encoding access is not active.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    if mode=="upscale" and not any(entitlement_ok(uid,k) for k in ("upscale_2k","upscale_4k","upscale_8k")):
        await message.reply_text("Upscale access is not active.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    if mode=="hybrid" and not any(entitlement_ok(uid,k) for k in ("upscale_4k","upscale_8k")):
        await message.reply_text("Hybrid requires 4K or 8K access.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    await message.reply_text(f"Select {mode} profile:",reply_markup=kb([[(x,f"profile:{mode}:{x}")] for x in MODES[mode]]+[[('Home','home'),('Cancel','cancel')]]),**plain_kwargs())


async def callback(client, q):
    await q.answer(); uid=q.from_user.id; data=q.data or ""
    if data=="home": await start_callback(q,client); return
    if data=="cancel": await q.message.reply_text("Cancelled.", **plain_kwargs()); return
    if data in ("pay","paymenu"): await q.edit_message_text("Select the service you want to purchase:",reply_markup=plan_keyboard(),**plain_kwargs()); return
    if data=="support": await support_start(q,client); return
    if data.startswith("buy:"): await show_payment_request(q,client,data.split(":",1)[1]); return
    if data.startswith("paid:"): await mark_paid(q,client,data.split(":",1)[1]); return
    if data.startswith("paidapprove:"): await paid_approve(q,client,data.split(":",1)[1]); return
    if data.startswith("grantconfirm:"):
        _,pid,plan=data.split(":",2); await confirm_grant(q,client,pid,plan); return
    if data.startswith("paidreject:"): await paid_reject(q,client,data.split(":",1)[1]); return
    if data=="health" and is_owner(uid):
        await q.edit_message_text(f"VIKKY HEALTH\nffmpeg={bool(shutil.which('ffmpeg'))}\nffprobe={bool(shutil.which('ffprobe'))}\naria2c={bool(shutil.which('aria2c'))}\nyt-dlp={bool(shutil.which('yt-dlp'))}\nDB={DB.exists()}\nowners={len(OWNER_IDS)}\nHydrogram=enabled\nAIWorker={bool(AI_CMD or Path(REALESRGAN_DIR).exists())}", **plain_kwargs()); return
    if data=="jobs" and is_owner(uid): await jobs_callback(q,client); return
    if data=="payments" and is_owner(uid): await payments_callback(q,client); return
    if data.startswith("cmd:"): await menu_callback(q,client,data.split(":",1)[1]); return
    if data.startswith("profile:"):
        _,mode,profile=data.split(":",2)
        needed="encode" if mode=="encode" else ("upscale_2k" if profile=="2K_AI" else "upscale_4k" if profile.startswith("4K") else "upscale_8k")
        if not entitlement_ok(uid,needed): await q.edit_message_text("This profile is not included in your active purchase.",reply_markup=plan_keyboard(),**plain_kwargs()); return
        selections[uid] = {"mode":mode,"profile":profile}
        await q.edit_message_text(f"Selected: {profile}\n\nSend the source video/file now.\nOr send a direct HTTP(S) video URL.\nFinal output: MKV.",reply_markup=kb([[('Back',f'cmd:{mode}'),('Cancel','cancel')]]),**plain_kwargs()); return


selections: dict[int, dict[str,str]] = {}

async def start_callback(q,client):
    if is_owner(q.from_user.id): await q.edit_message_text("OWNER / LIFETIME FREE\nEverything is unlocked.",reply_markup=owner_home_keyboard(),**plain_kwargs())
    else: await q.edit_message_text("VIKKY Encoder\n\nChoose your service:",reply_markup=plan_keyboard(),**plain_kwargs())

async def menu_callback(q,client,mode):
    uid=q.from_user.id
    if mode=="encode" and not entitlement_ok(uid,"encode"): await q.edit_message_text("Encoding access required.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    if mode=="upscale" and not any(entitlement_ok(uid,k) for k in ("upscale_2k","upscale_4k","upscale_8k")): await q.edit_message_text("Paid access required.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    if mode=="hybrid" and not any(entitlement_ok(uid,k) for k in ("upscale_4k","upscale_8k")): await q.edit_message_text("4K/8K access required.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    await q.edit_message_text(f"Select {mode} profile:",reply_markup=kb([[(x,f"profile:{mode}:{x}")] for x in MODES[mode]]+[[('Home','home'),('Cancel','cancel')]]),**plain_kwargs())

async def payments_callback(q,client):
    c=db(); rows=c.execute("SELECT id,uid,plan,status FROM payments ORDER BY created DESC LIMIT 20").fetchall(); c.close()
    if not rows: await q.edit_message_text("No payment requests.",reply_markup=owner_home_keyboard(),**plain_kwargs()); return
    await q.edit_message_text("Payment Requests\n\n"+"\n".join(f"{r['id']} | {r['uid']} | {r['plan']} | {r['status']}" for r in rows),reply_markup=owner_home_keyboard(),**plain_kwargs())

async def jobs_callback(q,client):
    c=db(); rows=c.execute("SELECT id,uid,mode,profile,status,progress FROM jobs ORDER BY created DESC LIMIT 30").fetchall(); c.close()
    text="\n".join(f"{x['id'][:8]} | {x['uid']} | {x['mode']} | {x['profile']} | {x['status']} | {x['progress']}%" for x in rows) or "No jobs."
    await q.edit_message_text(text,reply_markup=owner_home_keyboard(),**plain_kwargs())


async def quota(client,message):
    uid=message.from_user.id
    if is_owner(uid): await message.reply_text("Owner: unlimited quota.",**plain_kwargs()); return
    c=db(); u=quota_usage(c,uid); c.close(); used=u["used_bytes"]/1024**3; remain=max(0,WEEKLY_QUOTA_GB-used)
    await message.reply_text(f"Weekly quota\n\nReset: Saturday 00:00 Asia/Kolkata\nUsed: {used:.2f} GB / {WEEKLY_QUOTA_GB:.2f} GB\nRemaining: {remain:.2f} GB\nTasks: {u['used_tasks']} / {WEEKLY_QUOTA_TASKS}",**plain_kwargs())


async def accept_job(client, message, local_path: Path, sel: dict[str,str]):
    uid=message.from_user.id; size=local_path.stat().st_size
    if size > MAX_INPUT_GB*1024**3: raise RuntimeError(f"Input exceeds {MAX_INPUT_GB:g} GB ceiling")
    if not is_owner(uid):
        c=db(); allowed=quota_can_consume(c,uid,size,int(WEEKLY_QUOTA_GB*1024**3),WEEKLY_QUOTA_TASKS); usage=quota_usage(c,uid); c.close()
        if not allowed: raise RuntimeError(f"Weekly quota exhausted. Used {usage['used_bytes']/1024**3:.2f} GB / {WEEKLY_QUOTA_GB:.2f} GB")
    meta=ffprobe(local_path)
    if not meta: raise RuntimeError("FFprobe could not read the media")
    duration=float(meta.get("format",{}).get("duration") or 0); jid=uuid.uuid4().hex
    now=int(time.time())
    c=db(); c.execute("INSERT INTO jobs(id,uid,mode,profile,status,progress,input,output,error,created,updated,duration,size) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,uid,sel["mode"],sel["profile"],"queued",0,str(local_path),"","",now,now,duration,size)); c.commit(); c.close(); event(jid,uid,"queued")
    await message.reply_text(f"Queued {jid[:8]}. Processing will start automatically.",**plain_kwargs())
    schedule_job(client,jid)


async def media(client,message):
    if await proof_media(client,message): return
    if await support_message(client,message): return
    uid=message.from_user.id; sel=selections.get(uid)
    if not sel: return
    if not entitlement_ok(uid,"encode" if sel["mode"]=="encode" else ("upscale_2k" if sel["profile"]=="2K_AI" else "upscale_4k" if sel["profile"].startswith("4K") else "upscale_8k")):
        await message.reply_text("This profile is not included in your active purchase.",**plain_kwargs()); return
    work=TEMP/f"input_{uuid.uuid4().hex}"; work.mkdir(parents=True,exist_ok=True)
    try:
        if message.document or message.video:
            obj=message.document or message.video
            name=getattr(obj,"file_name",None) or f"video_{message.id}.mkv"
            dest=work/(safe_name(name) + ("" if Path(name).suffix else ".mkv"))
            await message.download(file_name=str(dest))
        else:
            url=extract_url(message.text or message.caption)
            if not url: return
            dest=work/"input.mkv"
            await message.reply_text("Downloading URL... aria2c first, yt-dlp fallback.",**plain_kwargs())
            status_msg = await message.reply_text("Download starting...", **plain_kwargs())
            async def _download_status(text: str):
                try:
                    await client.edit_message_text(message.chat.id, status_msg.id, text, **plain_kwargs())
                except Exception:
                    pass
            await download_url(
                url,
                dest,
                max_bytes=int(MAX_INPUT_GB*1024**3),
                progress_cb=_download_status,
            )
        await accept_job(client,message,dest,sel)
    except Exception as e:
        shutil.rmtree(work,ignore_errors=True)
        await message.reply_text(f"Input failed: {str(e)[:1200]}",**plain_kwargs())


def progress_from_ffmpeg(line: str, duration: float):
    m=re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",line)
    if m and duration:
        sec=int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3))
        return max(5,min(98,int(sec/duration*90)+5))
    m=re.search(r"(?<!\d)(\d{1,3})%(?!\d)", line)
    if m:
        return max(1,min(99,int(m.group(1))))
    return None

async def set_progress(jid,pct):
    c=db(); c.execute("UPDATE jobs SET progress=?,updated=? WHERE id=?",(max(0,min(99,int(pct))),int(time.time()),jid)); c.commit(); c.close()


def build_ffmpeg_command(inp: Path, out: Path, profile: str):
    return ["ffmpeg","-hide_banner","-y","-i",str(inp),"-map","0","-c:v","libx265","-preset","medium","-crf","18","-pix_fmt","yuv420p10le","-c:a","copy","-c:s","copy","-c:d","copy","-f","matroska",str(out)]


def build_ai_command(inp: Path, out: Path, profile: str):
    import shlex
    if AI_CMD:
        return AI_CMD.format(input=str(inp), output=str(out), mode="upscale", profile=profile)
    return " ".join([
        shlex.quote(sys.executable), shlex.quote(str(BASE / 'workers' / 'ai_worker.py')),
        '--input', shlex.quote(str(inp)), '--output', shlex.quote(str(out)),
        '--profile', shlex.quote(profile), '--realesrgan-dir', shlex.quote(REALESRGAN_DIR),
    ])

def load_uploader_functions():
    try:
        manager=importlib.import_module("uploaders.manager")
        upload=getattr(manager,"upload_with_fallback")
    except Exception:
        upload=None
    try:
        delivery=importlib.import_module("uploaders.delivery")
    except Exception:
        delivery=None
    return upload, delivery

async def deliver(client, jid, uid, out: Path, digest: str):
    upload, delivery = load_uploader_functions()
    if not upload:
        raise RuntimeError("uploaders.manager.upload_with_fallback is not available")
    result = await asyncio.to_thread(upload, str(out))
    if asyncio.iscoroutine(result): result = await result
    if isinstance(result, dict):
        url=result.get("url") or result.get("link") or result.get("download_url")
        provider=result.get("provider") or result.get("name") or "unknown"
    elif isinstance(result,(tuple,list)) and len(result)>=2:
        provider,url=result[0],result[1]
    else:
        provider="external"; url=str(result)
    if not url or not re.match(r"^https?://",url): raise RuntimeError("Uploader returned an invalid URL")
    now=int(time.time()); c=db(); c.execute("INSERT INTO deliveries(job_id,uid,provider,url,status,created) VALUES(?,?,?,?,?,?)",(jid,uid,str(provider),url,"sent",now)); c.commit(); c.close()
    text=f"Result ready\nProvider: {provider}\nDownload: {url}\nJob: {jid[:8]}\nSHA256: {digest}"
    if delivery:
        fn=getattr(delivery,"deliver_result",None)
        if fn:
            try:
                r=fn(client,uid,CHANNEL_ID,text,job_id=jid,provider=provider,url=url)
                if asyncio.iscoroutine(r): await r
                return url
            except TypeError:
                pass
    await client.send_message(uid,text,**plain_kwargs())
    if CHANNEL_ID:
        try: await client.send_message(CHANNEL_ID,text,**plain_kwargs())
        except Exception: pass
    return url


async def run_job(client,jid):
    if jid in active_jobs: return
    active_jobs.add(jid)
    async with worker_sem:
        c=db(); r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone(); c.close()
        if not r: active_jobs.discard(jid); return
        inp=Path(r["input"]); out=OUT/f"{safe_name(inp.name)}.{r['profile']}.By.VIKKY.mkv"
        try:
            c=db(); c.execute("UPDATE jobs SET status='processing',progress=2,updated=? WHERE id=?",(int(time.time()),jid)); c.commit(); c.close(); event(jid,r["uid"],"processing")
            duration=float(r["duration"] or 0)
            is_ai = r["profile"].endswith("_AI") or r["profile"].endswith("_HYBRID")
            if is_ai:
                cmd=build_ai_command(inp,out,r["profile"])
                proc=await asyncio.create_subprocess_shell(cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            elif WORKER_CMD:
                cmd=WORKER_CMD.format(input=str(inp),output=str(out),mode=r["mode"],profile=r["profile"])
                proc=await asyncio.create_subprocess_shell(cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            else:
                proc=await asyncio.create_subprocess_exec(*build_ffmpeg_command(inp,out,r["profile"]),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            status_msg=None; last=5; last_live=0; last_line=''
            try:
                status_msg=await client.send_message(r["uid"],f"Job {jid[:8]}\n{r['mode']} / {r['profile']}\nStarting...",**plain_kwargs())
            except Exception:
                pass
            while True:
                raw=await proc.stdout.readline()
                if not raw: break
                line=raw.decode("utf-8","ignore").strip(); last_line=line[-300:]
                pct=progress_from_ffmpeg(line,duration)
                if pct:
                    last=pct; await set_progress(jid,pct)
                cc=db(); cr=cc.execute("SELECT status FROM jobs WHERE id=?",(jid,)).fetchone(); cc.close()
                if cr and cr["status"]=="cancelled":
                    try: proc.terminate()
                    except Exception: pass
                    raise RuntimeError("Job cancelled by user")
                if status_msg and time.time()-last_live>=LIVE_INTERVAL:
                    last_live=time.time()
                    try:
                        await client.edit_message_text(r["uid"],status_msg.id,f"Job {jid[:8]}\n{r['mode']} / {r['profile']}\nProgress: {last}%\nEngine: {'AI/GPU' if is_ai else 'FFmpeg'}",**plain_kwargs())
                    except Exception: pass
            rc=await proc.wait()
            if rc!=0 or not out.exists() or out.stat().st_size==0: raise RuntimeError(f"Processing worker failed with exit code {rc}. Last output: {last_line}")
            if status_msg:
                try: await client.edit_message_text(r["uid"],status_msg.id,f"Job {jid[:8]}\nProcessing complete. Validating MKV...",**plain_kwargs())
                except Exception: pass
            meta=ffprobe(out)
            if not meta: raise RuntimeError("Output validation failed")
            digest=sha256(out); size=out.stat().st_size
            report=REPORTS/f"{jid}.json"; report.write_text(json.dumps({"job_id":jid,"output":str(out),"bytes":size,"sha256":digest,"media":meta,"verified_mkv":out.suffix.lower()=='.mkv'},indent=2),encoding="utf-8")
            c=db(); c.execute("UPDATE jobs SET status='uploading',progress=99,output=?,sha256=?,size=?,updated=? WHERE id=?",(str(out),digest,size,int(time.time()),jid)); c.commit(); c.close()
            await deliver(client,jid,r["uid"],out,digest)
            if not is_owner(r["uid"]):
                c=db(); quota_consume(c,r["uid"],size); c.close()
            c=db(); c.execute("UPDATE jobs SET status='done',progress=100,updated=? WHERE id=?",(int(time.time()),jid)); c.commit(); c.close(); event(jid,r["uid"],"done")
            await client.send_message(r["uid"],f"Job {jid[:8]} complete. External result link has been sent.",**plain_kwargs())
        except Exception as e:
            c=db(); c.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=?",(str(e)[:2000],int(time.time()),jid)); c.commit(); c.close(); event(jid,r["uid"],f"failed: {e}")
            try: await client.send_message(r["uid"],f"Job {jid[:8]} failed.\n{str(e)[:1200]}",**plain_kwargs())
            except Exception: pass
        finally:
            active_jobs.discard(jid)
            try:
                c = db(); final = c.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone(); c.close()
                final_status = final["status"] if final else "failed"
                if final_status in ("done", "cancelled"):
                    if inp.parent.name.startswith("input_"): shutil.rmtree(inp.parent, ignore_errors=True)
                    if out.exists(): out.unlink(missing_ok=True)
            except Exception:
                pass


def schedule_job(client,jid):
    if jid in active_jobs: return
    task=asyncio.create_task(run_job(client,jid)); worker_tasks.add(task); task.add_done_callback(worker_tasks.discard)

async def recover_queued_jobs(client):
    c=db(); rows=c.execute("SELECT id FROM jobs WHERE status IN ('queued','processing','uploading') ORDER BY created ASC").fetchall(); c.close()
    for r in rows: schedule_job(client,r["id"])

async def grant(client,message):
    if not is_owner(message.from_user.id): return
    args=message.text.split() if message.text else []
    if len(args)<3: await message.reply_text("Usage: /grant USER_ID DAYS PLAN_CODE",**plain_kwargs()); return
    uid=int(args[1]); days=int(args[2]); plan=args[3] if len(args)>3 else "ALL_2500"
    if plan not in PLANS: await message.reply_text("Unknown plan.",**plain_kwargs()); return
    until=int(time.time())+days*86400; touch_user(uid); c=db(); c.execute("INSERT OR REPLACE INTO entitlements(uid,plan,until) VALUES(?,?,?)",(uid,plan,until)); c.execute("UPDATE users SET access_until=MAX(access_until,?) WHERE uid=?",(until,uid)); c.commit(); c.close(); await message.reply_text(f"Granted {PLANS[plan]['label']} for {days} days.",**plain_kwargs())

async def revoke(client,message):
    if not is_owner(message.from_user.id): return
    args=message.text.split() if message.text else []
    if len(args)<2: await message.reply_text("Usage: /revoke USER_ID [PLAN_CODE]",**plain_kwargs()); return
    uid=int(args[1]); c=db();
    if len(args)>2: c.execute("DELETE FROM entitlements WHERE uid=? AND plan=?",(uid,args[2]))
    else: c.execute("DELETE FROM entitlements WHERE uid=?",(uid,))
    c.commit(); c.close(); await message.reply_text("Access revoked.",**plain_kwargs())

async def status(client,message):
    uid=message.from_user.id; touch_user(uid)
    if is_owner(uid): await message.reply_text("Owner - lifetime FREE access.",**plain_kwargs()); return
    c=db(); rows=c.execute("SELECT plan,until FROM entitlements WHERE uid=? AND until>?",(uid,int(time.time()))).fetchall(); c.close()
    if not rows: await message.reply_text("No active paid access.",reply_markup=plan_keyboard(),**plain_kwargs()); return
    await message.reply_text("Active services:\n"+"\n".join(f"{PLANS[r['plan']]['label']} until {datetime.fromtimestamp(r['until'],timezone.utc).date().isoformat()}" for r in rows),**plain_kwargs())

async def jobs_cmd(client,message):
    if not is_owner(message.from_user.id): return
    c=db(); rows=c.execute("SELECT id,uid,mode,profile,status,progress FROM jobs ORDER BY created DESC LIMIT 30").fetchall(); c.close(); await message.reply_text("\n".join(f"{x['id'][:8]} | {x['uid']} | {x['mode']} | {x['profile']} | {x['status']} | {x['progress']}%" for x in rows) or "No jobs.",**plain_kwargs())

async def retry(client,message):
    if not is_owner(message.from_user.id): return
    args=message.text.split() if message.text else []
    if len(args)<2: return
    jid=args[1]; c=db(); r=c.execute("SELECT id FROM jobs WHERE id=?",(jid,)).fetchone();
    if not r: c.close(); await message.reply_text("Job not found.",**plain_kwargs()); return
    c.execute("UPDATE jobs SET status='queued',progress=0,error='',updated=? WHERE id=?",(int(time.time()),jid)); c.commit(); c.close(); schedule_job(client,jid); await message.reply_text("Job requeued.",**plain_kwargs())

async def cancel(client,message):
    args=message.text.split() if message.text else []
    if len(args)<2: await message.reply_text("Usage: /cancel JOB_ID",**plain_kwargs()); return
    jid=args[1]; uid=message.from_user.id; c=db(); r=c.execute("SELECT uid FROM jobs WHERE id=?",(jid,)).fetchone()
    if not r or (r["uid"]!=uid and not is_owner(uid)): c.close(); await message.reply_text("Not allowed / not found.",**plain_kwargs()); return
    c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?",(int(time.time()),jid)); c.commit(); c.close(); await message.reply_text("Job cancelled.",**plain_kwargs())

async def health(client,message):
    if not is_owner(message.from_user.id): return
    await message.reply_text(f"VIKKY HEALTH\nffmpeg={bool(shutil.which('ffmpeg'))}\nffprobe={bool(shutil.which('ffprobe'))}\naria2c={bool(shutil.which('aria2c'))}\nyt-dlp={bool(shutil.which('yt-dlp'))}\nDB={DB.exists()}\nHydrogram=enabled\nOwners={len(OWNER_IDS)}",**plain_kwargs())

async def error_handler(client, update, error):
    print("BOT_ERROR", repr(error))


def build_app():
    app=Client(
        "vikky_encoder",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        parse_mode=enums.ParseMode.DISABLED,
    )
    app.set_parse_mode(enums.ParseMode.DISABLED)
    for command, fn in {
        "start":start,"pay":pay,"encode":lambda c,m:menu(c,m,"encode"),"upscale":lambda c,m:menu(c,m,"upscale"),"hybrid":lambda c,m:menu(c,m,"hybrid"),
        "status":status,"quota":quota,"grant":grant,"revoke":revoke,"jobs":jobs_cmd,"retry":retry,"cancel":cancel,"health":health,"support":support_cmd,"reply":reply_support,
    }.items():
        app.add_handler(MessageHandler(fn, filters.command(command)))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(media, filters.photo | filters.document | filters.video))
    app.add_handler(MessageHandler(media, filters.text & ~filters.command("start")))
    return app


def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN is missing; use environment/GitHub Secrets.")
    if not API_ID or not API_HASH: raise SystemExit("API_ID/API_HASH are required by Hydrogram; keep them in environment/GitHub Secrets.")
    if len(OWNER_IDS)!=2: raise SystemExit("Set exactly two OWNER_IDS.")
    init_db()
    backoff=5
    while True:
        app=build_app()
        async def runner():
            await app.start()
            await recover_queued_jobs(app)
            print(f"{APP} running | Hydrogram | Python 3.14 | MKV-only | persistent SQLite queue")
            try:
                await idle()
            finally:
                await app.stop()
        try:
            asyncio.run(runner())
            backoff=5
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print("BOT_RUNTIME_RESTART", repr(exc), flush=True)
            time.sleep(backoff)
            backoff=min(backoff*2, 60)

if __name__=="__main__":
    main()
