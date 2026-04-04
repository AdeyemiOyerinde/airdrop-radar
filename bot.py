"""
AirdropRadar Telegram Bot
Monitors testnets, airdrops, and crypto opportunities across multiple sources.
"""

import asyncio
import json
import os
import logging
from datetime import datetime, time
from typing import Optional
import httpx
from dotenv import load_dotenv
load_dotenv()  # loads variables from .env file automatically
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import anthropic

# ── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
AUTHORIZED_USER_ID = int(os.environ["TELEGRAM_USER_ID"])  # Your Telegram user ID

# Tracking file (persists your positions between restarts)
DATA_FILE = "tracked_airdrops.json"

# ── INTELLIGENCE SOURCES ─────────────────────────────────────────────────────
# These URLs are passed to Claude so it fetches live data directly from the source
SOURCES = {
    # Airdrop trackers
    "dropstab":         "https://dropstab.com",
    "airdrops_io":      "https://airdrops.io",
    "alphadrops":       "https://alphadrops.net",
    "oneclickcrypto":   "https://oneclickcrypto.com/airdrop-tracker",
    "dappradar":        "https://dappradar.com/airdrops",
    "earni_fi":         "https://earni.fi",
    # Quest platforms
    "layer3":           "https://layer3.xyz/quests",
    # Funding / VC data
    "cryptorank":       "https://cryptorank.io/funding-rounds",
    "icodrops":         "https://icodrops.com",
    "icoanalytics":     "https://icoanalytics.org",
    "crunchbase_crypto": "https://www.crunchbase.com/discover/organization.companies/field/organizations/categories/cryptocurrency",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── DATA LAYER ───────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"tracked": [], "notes": {}}


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── CLAUDE AI HELPER ─────────────────────────────────────────────────────────
async def ask_claude(system_prompt: str, user_message: str, deep: bool = False) -> str:
    """Call Claude with web search. deep=True allows multiple search rounds."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    max_tokens = 2500 if deep else 1500

    messages = [{"role": "user", "content": user_message}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    # Agentic loop — keep going until Claude stops calling tools
    for _ in range(6 if deep else 2):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        # Collect assistant turn
        messages.append({"role": "assistant", "content": response.content})

        # If Claude is done (no more tool calls), extract text and return
        if response.stop_reason == "end_turn":
            result = ""
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    result += block.text
            return result.strip()

        # Otherwise feed tool results back and continue
        tool_results = []
        has_tool_use = False
        for block in response.content:
            if block.type == "tool_use":
                has_tool_use = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": ""  # web_search handles its own results internally
                })
        if not has_tool_use:
            break
        # For web_search the SDK handles results automatically; just continue
        # Extract any text so far and return if stop_reason was end_turn above
        result = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                result += block.text
        if result.strip():
            return result.strip()

    # Fallback: extract whatever text exists
    result = ""
    for block in response.content:
        if hasattr(block, "text") and block.text:
            result += block.text
    return result.strip()


SYSTEM_PROMPT = """You are AirdropRadar, an elite crypto intelligence assistant. Today is March 2026.

━━━━━━━━━━━━━━━━━━━━━━━━━
SCORING FRAMEWORK (apply to every project)
━━━━━━━━━━━━━━━━━━━━━━━━━

Score each project across 5 metrics, then assign a tier (S / A / B / C):

[METRIC 1 — VC BACKING] (Heaviest weight / gatekeeper metric)
- Count Tier 1 VCs: a16z crypto, Paradigm, Sequoia, Polychain, Founders Fund, Coinbase Ventures, Dragonfly, Bain Capital Crypto, and equivalents.
- 2+ Tier 1 VCs = strong signal → pushes toward S/A.
- 1 Tier 1 VC = decent → B/A depending on other metrics.
- Mid-tier only or undisclosed = weak → stays B/C unless other metrics compensate heavily.
- Internal/corporate backing (e.g. Coinbase → Base, Circle → Arc) = extremely strong equivalent.
- Low VC count rarely allows entry above B unless other metrics compensate heavily.

[METRIC 2 — NARRATIVE / META LEADERSHIP]
- Hot 2026 metas: prediction markets, privacy/FHE/ZK, decentralized AI/compute, stablecoins/payments infra, consumer L2s.
- Being THE first-mover or category leader in a hot meta is a strong S/A multiplier.
- Being just "a" project in a crowded or cold niche caps at B/C even with decent other metrics.
- Examples of strong narrative fits: privacy (Seismic, Inco, Fhenix, Zama), AI infra (Nous, Ritual, Openmind), consumer L2 (Base, Abstract), payments (Tempo, Arc).

[METRIC 3 — FUNDING AMOUNT]
- Threshold: $7M+ minimum. Strongly prefer $25M+.
- High raise = VC skin-in-the-game + better token economics potential → boosts to S/A.
- Below $7M or undisclosed = B/C unless elite team or meta strength compensates.
- Corporate-backed projects (Base, Arc) score max here due to parent-company scale.

[METRIC 4 — TEAM & COMMUNITY]
- Elite pedigree: ex-Paradigm, quant hedge funds, AI researchers, Coinbase/Circle alumni, MIT/Stanford ties → pushes higher.
- Solid but less known teams → B/C.
- HARD REQUIREMENT: Active community (Discord roles, quests, X engagement, consistent updates). Ghost/inactive communities = deprioritize or drop entirely.

[METRIC 5 — PRODUCT & FARMING VIABILITY]
- Real utility, live testnet or advanced stage, unique tech (FHE, AI model serving, prediction trading, confidential compute).
- Must have clear, actionable farming tasks: quests, testnet interactions, Discord roles, yapping/InfoFi, waitlists, daily check-ins.
- Mature products with live activity score higher. Early/me-too products score lower.

━━━━━━━━━━━━━━━━━━━━━━━━━
TIER DEFINITIONS
━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 S — Near-perfect on most/all metrics. Narrative dominance, huge upside, confirmed/rumored airdrop.
🥇 A — Strong on 4+ metrics. VC + meta + funding combo. High conviction.
🥈 B — Solid but has gaps (fewer VCs or more competition).
🥉 C — Viable on 2–3 metrics. Active community. Worth time if bandwidth allows.
❌ EXCLUDE — Does not meet C threshold. Drop silently — never mention it.

━━━━━━━━━━━━━━━━━━━━━━━━━
$0-COST FILTER (always applied)
━━━━━━━━━━━━━━━━━━━━━━━━━
ONLY include projects farmable with ZERO capital:
- Allowed: faucet testnet, free deployments, quests, Discord roles, social tasks, waitlists.
- Excluded: anything needing deposits, real-gas volume, or bridging funds.
ALLOWED CATEGORIES ONLY: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets, privacy/FHE/ZK, decentralized AI/compute, stablecoins/payments infra, consumer L2s.
Silently exclude any project outside these categories.

━━━━━━━━━━━━━━━━━━━━━━━━━
LIST FORMAT (for testnet/funding lists)
━━━━━━━━━━━━━━━━━━━━━━━━━
[BADGE] ProjectName — $XXM raised — one sentence max.
Example: 🥇 Inco Network — $5M — Privacy L1 with FHE, testnet live.
No scores, no star ratings, no extra sections. Just the list.

DETAIL FORMAT (when user asks about a specific project)
━━━━━━━━━━━━━━━━━━━━━━━━━
[BADGE] ProjectName
💰 $XM raised | VCs: Name1, Name2
🌐 Meta: category
⚙️ Tasks: task1, task2, task3
🔗 link

━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━
- ALWAYS use web search — never rely on training data.
- HARD BLOCK: Never post any project that has gone mainnet, done TGE, or completed airdrop distribution.
- HARD BLOCK: Never post any project that does not qualify for at least tier C.
- If mainnet/TGE/airdrop status is uncertain, search to confirm before including.
- All messages must be as short as possible — cut every word that doesn't add information.
- No filler: no "I'll search...", "Great question!", "Sure!", "Let me look that up...". Go straight to the answer.
- Never ask clarifying questions. Execute and return results.
- Never say you cannot fetch websites. Use web search instead."""



# ── MESSAGE HELPER ────────────────────────────────────────────────────────────
async def send_long(target, text: str, **kwargs):
    """Split messages that exceed Telegram's 4096 char limit and send in chunks."""
    limit = 4000
    if len(text) <= limit:
        await target.reply_text(text, **kwargs)
        return
    # Split on double newline to keep sections intact
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    for i, chunk in enumerate(chunks):
        prefix = f"_(part {i+1}/{len(chunks)})_\n\n" if len(chunks) > 1 else ""
        await target.reply_text(prefix + chunk, **kwargs)


# ── COMMAND HANDLERS ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    keyboard = [
        [InlineKeyboardButton("🔍 New Testnets", callback_data="testnets"),
         InlineKeyboardButton("📋 My Positions", callback_data="positions")],
        [InlineKeyboardButton("💰 Recent Funding", callback_data="funding"),
         InlineKeyboardButton("📰 Airdrop News", callback_data="news")],
        [InlineKeyboardButton("➕ Track Airdrop", callback_data="track_prompt"),
         InlineKeyboardButton("📊 Daily Digest", callback_data="digest")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚡ *AirdropRadar Online*\n\n"
        "Your personal crypto intelligence layer. What do you need?",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-form messages — relay to Claude with web search."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    user_text = update.message.text
    data = load_data()
    tracked = data.get("tracked", [])

    # Add tracked airdrops context
    context_note = ""
    if tracked:
        context_note = f"\n\nUser is currently tracking: {', '.join(tracked)}"

    await update.message.chat.send_action("typing")

    response = await ask_claude(
        SYSTEM_PROMPT + context_note,
        user_text
    )

    await send_long(update.message, response, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != AUTHORIZED_USER_ID:
        return

    data = load_data()
    action = query.data

    if action == "testnets":
        await query.message.chat.send_action("typing")
        response = await ask_claude(
            SYSTEM_PROMPT,
            "Search for free $0 testnets in these categories: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets. "
            "Search queries: 'free Layer1 testnet airdrop 2026', 'free AI crypto testnet 2026', 'free DeFi testnet airdrop 2026', "
            "'free DePIN testnet 2026', 'free RWA crypto testnet 2026', 'free SocialFi testnet 2026', "
            "'free Perp DEX testnet airdrop 2026', 'free prediction market testnet 2026', 'free L2 testnet airdrop 2026'. "
            "Score each with the framework. Include only S/A/B/C. Exclude mainnet/TGE/airdrop-done. Exclude any outside the allowed categories. "
            "Format each line: [BADGE] Name — $XM — category — one sentence. Min 8 projects."
        )
        await send_long(query.message, f"🧪 *Active Testnets*\n\n{response}", parse_mode="Markdown")

    elif action == "positions":
        tracked = data.get("tracked", [])
        if not tracked:
            await query.message.reply_text(
                "📋 You're not tracking any airdrops yet.\n\nSend me `/track ProjectName` to add one!"
            )
        else:
            await query.message.chat.send_action("typing")
            response = await ask_claude(
                SYSTEM_PROMPT,
                f"Search for latest status on: {', '.join(tracked)}. "
                "For each: any deadlines, new tasks, or airdrop/TGE updates. "
                "If a project already did TGE/airdrop, flag it clearly so farming can stop. "
                "Keep each entry to 2-3 lines max."
            )
            await send_long(query.message, f"📋 *Your Positions Update*\n\n{response}", parse_mode="Markdown")

    elif action == "funding":
        await query.message.chat.send_action("typing")
        response = await ask_claude(
            SYSTEM_PROMPT,
            "Search for newly funded projects in: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets. "
            "Queries: 'Layer1 crypto funding 2026', 'AI crypto startup raised 2026', 'DeFi funding round 2026', "
            "'DePIN startup raised 2026', 'RWA crypto funding 2026', 'SocialFi funding 2026', "
            "'prediction market crypto raised 2026', 'L2 funding round 2026'. "
            "Score each with the framework. Include only S/A/B/C. Exclude mainnet/TGE/airdrop-done. Exclude outside allowed categories. "
            "Format: [BADGE] Name — $XM raised — category — one sentence + free farming path if exists."
        )
        await send_long(query.message, f"💰 *Recent Funding Rounds*\n\n{response}", parse_mode="Markdown")

    elif action == "news":
        tracked = data.get("tracked", [])
        await query.message.chat.send_action("typing")
        query_text = (
            f"Search for the latest news about these projects: {', '.join(tracked)}. "
            "Include any airdrop announcements, snapshot dates, or major updates."
            if tracked else
            "Search for the top airdrop and testnet news from the past 48 hours. "
            "What's trending on crypto Twitter and Discord right now?"
        )
        response = await ask_claude(SYSTEM_PROMPT, query_text)
        await send_long(query.message, f"📰 *Latest Airdrop News*\n\n{response}", parse_mode="Markdown")

    elif action == "track_prompt":
        await query.message.reply_text(
            "➕ *Track a new airdrop*\n\nSend me:\n`/track ProjectName`\n\nExample: `/track ZkSync`",
            parse_mode="Markdown"
        )

    elif action == "digest":
        await send_daily_digest(query.message.chat_id, context.application)


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a project to tracking list."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: `/track ProjectName`", parse_mode="Markdown")
        return

    project = " ".join(context.args).strip()
    data = load_data()

    if project.lower() in [p.lower() for p in data["tracked"]]:
        await update.message.reply_text(f"⚠️ *{project}* is already in your tracking list.", parse_mode="Markdown")
        return

    data["tracked"].append(project)
    save_data(data)

    # Get quick intel on this project
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Search for latest info on {project}. Score it using the framework. "
        f"If it went mainnet, did TGE, or distributed airdrop already — say so and stop. "
        f"If it qualifies (S/A/B/C): use the detail format — badge, funding, VCs, meta, tasks, link. "
        f"If it does not qualify for any tier — say it doesn't meet the criteria in one line."
    )

    await update.message.reply_text(
        f"✅ *{project}* added to tracking!\n\n{response}",
        parse_mode="Markdown"
    )


async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a project from tracking list."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: `/untrack ProjectName`", parse_mode="Markdown")
        return

    project = " ".join(context.args).strip()
    data = load_data()

    original = data["tracked"][:]
    data["tracked"] = [p for p in data["tracked"] if p.lower() != project.lower()]

    if len(data["tracked"]) == len(original):
        await update.message.reply_text(f"❌ *{project}* wasn't in your list.", parse_mode="Markdown")
    else:
        save_data(data)
        await update.message.reply_text(f"🗑️ *{project}* removed from tracking.", parse_mode="Markdown")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all tracked projects."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    data = load_data()
    tracked = data.get("tracked", [])

    if not tracked:
        await update.message.reply_text("📋 No projects tracked yet. Use `/track ProjectName` to start.")
        return

    listing = "\n".join([f"  {i+1}. {p}" for i, p in enumerate(tracked)])
    await update.message.reply_text(
        f"📋 *Tracked Projects ({len(tracked)})*\n\n{listing}\n\n"
        f"Use `/untrack Name` to remove one.",
        parse_mode="Markdown"
    )


# ── DAILY DIGEST ──────────────────────────────────────────────────────────────
async def send_daily_digest(chat_id: int, app: Application):
    """Send the morning intelligence digest."""
    data = load_data()
    tracked = data.get("tracked", [])

    tracked_section = f"tracking {', '.join(tracked)}" if tracked else "no specific projects yet"

    prompt = (
        f"Morning digest — March 2026. Tracking: {tracked_section}.\n"
        "Search web for each section. Be ultra short — bullet points only.\n\n"
        "🔴 URGENT — tracked projects with deadlines in next 72h (task/snapshot/quest expiry).\n"
        "💰 NEW FUNDING — raises from past 24h. S/A/B/C badge + one line each. Skip non-qualifiers.\n"
        "📰 NEWS — airdrop/TGE announcements. Flag any tracked project that already distributed.\n"
        "🆕 ONE NEW PICK — single best $0 testnet found today. List format only."
    )

    try:
        response = await ask_claude(SYSTEM_PROMPT, prompt)
        now = datetime.now().strftime("%A, %B %d")
        await app.bot.send_message(
            chat_id=chat_id,
            text=f"☀️ *AirdropRadar Morning Digest — {now}*\n\n{response}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Daily digest failed: {e}")



async def testnets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        "Search for free $0 testnets in these categories: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets. "
        "Search queries: 'free Layer1 testnet airdrop 2026', 'free AI crypto testnet airdrop 2026', 'free DeFi testnet 2026', "
        "'free DePIN testnet 2026', 'free RWA crypto testnet 2026', 'free SocialFi testnet 2026', "
        "'free Perp DEX testnet airdrop 2026', 'free prediction market testnet 2026', 'free L2 testnet airdrop 2026'. "
        "Score each with the framework. Include only S/A/B/C. Exclude mainnet/TGE/airdrop-done. Exclude outside allowed categories. "
        "Format each line: [BADGE] Name — $XM — category — one sentence. Min 8 projects."
    )
    await send_long(update.message, f"🧪 *Active Testnets*\n\n{response}", parse_mode="Markdown")


async def funding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        "Search for newly funded projects in: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets. "
        "Queries: 'Layer1 crypto funding 2026', 'AI crypto startup raised 2026', 'DeFi funding round 2026', "
        "'DePIN startup raised 2026', 'RWA crypto funding 2026', 'SocialFi funding 2026', "
        "'prediction market crypto raised 2026', 'L2 funding round 2026'. "
        "Score each with the framework. Include only S/A/B/C. Exclude mainnet/TGE/airdrop-done. Exclude outside allowed categories. "
        "Format: [BADGE] Name — $XM raised — category — one sentence + free farming path if exists."
    )
    await send_long(update.message, f"💰 *Recent Funding Rounds*\n\n{response}", parse_mode="Markdown")


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    data = load_data()
    tracked = data.get("tracked", [])
    await update.message.chat.send_action("typing")
    query_text = (
        f"Search for the latest news about these projects: {', '.join(tracked)}. "
        "Include any airdrop announcements, snapshot dates, or major updates."
        if tracked else
        "Search for the top airdrop and testnet news from the past 48 hours. "
        "What is trending on crypto Twitter and Discord right now?"
    )
    response = await ask_claude(SYSTEM_PROMPT, query_text)
    await send_long(update.message, f"📰 *Latest Airdrop News*\n\n{response}", parse_mode="Markdown")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    data = load_data()
    tracked = data.get("tracked", [])
    if not tracked:
        await update.message.reply_text(
            "📋 You are not tracking any airdrops yet.\n\nUse `/track ProjectName` to add one!",
            parse_mode="Markdown"
        )
        return
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Give me the latest status update on these airdrops/testnets I am positioned for: "
        f"{', '.join(tracked)}. Include any recent news, snapshot dates, task deadlines, or distribution updates."
    )
    await send_long(update.message, f"📋 *Your Positions Update*\n\n{response}", parse_mode="Markdown")


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    await update.message.chat.send_action("typing")
    await send_daily_digest(update.message.chat_id, context.application)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    help_text = (
        "⚡ *AirdropRadar Commands*\n\n"
        "/start — Open the main menu\n"
        "/track [name] — Add a project to your watchlist\n"
        "/untrack [name] — Remove a project from your watchlist\n"
        "/list — View all tracked projects\n"
        "/testnets — Find free active testnet opportunities\n"
        "/funding — Latest crypto funding rounds (7 days)\n"
        "/news — Latest airdrop and testnet news\n"
        "/positions — Status update on your tracked projects\n"
        "/digest — Trigger your morning intelligence briefing\n"
        "/tracker — Live airdrop data from Dropstab & Layer3\n"
        "/vcs [name] — Confirmed VC backers for a project\n"
        "/faucet [name] — Verify live faucet and active quests\n"
        "/weekly — Weekly farming summary for all tracked projects\n"
        "/stopcheck — Auto-suggest which projects to stop farming\n"
        "/help — Show this message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def tracker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pull real-time airdrop tracker data from Dropstab and Layer3."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        "Search all major airdrop trackers for $0 opportunities in: Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, Prediction Markets. "
        "Run these searches: 'airdrops.io top airdrops March 2026', 'alphadrops DeFi L2 AI airdrop 2026', "
        "'oneclickcrypto confirmed potential airdrop 2026', 'dappradar airdrops 2026', "
        "'layer3 free quests March 2026', 'dropstab upcoming airdrops 2026'. "
        "Only include projects in allowed categories. Exclude anything needing capital. "
        "Sections — one line each: "
        "\n🔴 CONFIRMED — name | category | est. value | key task "
        "\n🟡 POINTS/POTENTIAL — name | category | farming method "
        "\n🎯 LAYER3 QUESTS — quest name | category | reward "
        "Apply $0-cost filter. No questions — search and return.",
        deep=True
    )
    await send_long(update.message, "📡 *Live Tracker Data*\n\n" + response, parse_mode="Markdown")


async def vcs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Look up confirmed VC backers for a specific project."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/vcs ProjectName`\nExample: `/vcs Ritual`",
            parse_mode="Markdown"
        )
        return
    project = " ".join(context.args).strip()
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Find the confirmed investor/VC list for {project}. "
        f"Search: '{project} investors', '{project} funding round backers', '{project} crunchbase', '{project} site:cryptorank.io'. "
        f"Also check {SOURCES['cryptorank']} and {SOURCES['icodrops']} for {project}. "
        "List every confirmed backer with their tier (Tier 1 / Tier 2 / Strategic). "
        "Include total amount raised and round details if available. "
        "Format: investor name — tier — round they joined. "
        "Only include confirmed backers — no speculation.",
        deep=True
    )
    await send_long(update.message, f"🏦 *VC Backers — {project}*\n\n" + response, parse_mode="Markdown")


async def faucet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify live testnet faucets and active quests for a project."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/faucet ProjectName`\nExample: `/faucet Monad`",
            parse_mode="Markdown"
        )
        return
    project = " ".join(context.args).strip()
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Verify the current testnet status for {project} as of March 2026. Search: "
        f"'{project} testnet faucet 2026', '{project} testnet quests active', '{project} discord quests', "
        f"'{project} site:layer3.xyz', '{project} site:galxe.com'. "
        "Confirm: (1) Is the testnet currently live or paused? "
        "(2) Faucet link — is it working and what is the daily claim amount? "
        "(3) Active quests on Layer3, Galxe, or official Discord — list each with steps and reward. "
        "(4) Any upcoming quest deadlines or snapshot dates. "
        "Flag anything that requires spending real money. Only report verified, live information.",
        deep=True
    )
    await send_long(update.message, f"🚰 *Faucet & Quests — {project}*\n\n" + response, parse_mode="Markdown")


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a weekly farming summary report."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    data = load_data()
    tracked = data.get("tracked", [])
    tracked_section = ", ".join(tracked) if tracked else "no projects tracked"
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Weekly farming report for: {tracked_section}.\n"
        "Search for updates on each. For each project give:\n"
        "- Status: still active / TGE done / airdrop distributed\n"
        "- Any new tasks or quests added this week\n"
        "- Airdrop timeline update (closer, confirmed, delayed)\n"
        "- Worth continuing to farm? Yes / No / Maybe\n"
        "Keep each project to 3 lines max. Flag anything that already airdropped.",
        deep=True
    )
    now = datetime.now().strftime("%B %d, %Y")
    await send_long(update.message, f"📊 *Weekly Report — {now}*\n\n" + response, parse_mode="Markdown")


async def stopcheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-suggest which tracked projects to stop farming."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    data = load_data()
    tracked = data.get("tracked", [])
    if not tracked:
        await update.message.reply_text("📋 No tracked projects. Use `/track Name` to add some.")
        return
    await update.message.chat.send_action("typing")
    response = await ask_claude(
        SYSTEM_PROMPT,
        f"Evaluate these projects and tell me which ones I should STOP farming: {', '.join(tracked)}.\n"
        "Search for current status of each. Flag a project as STOP if any of these apply:\n"
        "1. Already did TGE or airdrop distribution\n"
        "2. Went mainnet with no airdrop announced\n"
        "3. Project abandoned / team gone quiet for 3+ months\n"
        "4. Airdrop rumored to exclude testnet farmers\n"
        "5. Opportunity cost too low vs effort\n"
        "Format: \n🛑 STOP: ProjectName — reason in one line\n"
        "✅ KEEP: ProjectName — reason in one line\n"
        "Be decisive. If unclear, lean toward KEEP but note the risk.",
        deep=True
    )
    await send_long(update.message, "🔍 *Stop Farming Check*\n\n" + response, parse_mode="Markdown")

# ── SCHEDULER ─────────────────────────────────────────────────────────────────
def setup_scheduler(app: Application, user_id: int):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=8,
        minute=0,
        args=[user_id, app],
        id="daily_digest",
    )
    scheduler.start()
    logger.info("Scheduler started — daily digest at 08:00")
    return scheduler


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("untrack", untrack_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("testnets", testnets_command))
    app.add_handler(CommandHandler("funding", funding_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tracker", tracker_command))
    app.add_handler(CommandHandler("vcs", vcs_command))
    app.add_handler(CommandHandler("faucet", faucet_command))
    app.add_handler(CommandHandler("weekly", weekly_command))
    app.add_handler(CommandHandler("stopcheck", stopcheck_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start scheduler
    setup_scheduler(app, AUTHORIZED_USER_ID)

    logger.info("AirdropRadar bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()