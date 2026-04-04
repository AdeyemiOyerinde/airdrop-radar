# ⚡ AirdropRadar

A personal Telegram bot that monitors crypto testnets and airdrops, scores them using a structured VC/narrative/funding framework, and delivers daily intelligence briefings — powered by Claude AI with live web search.

---

## What It Does

- Discovers free ($0-cost) testnet opportunities across Layer 1, Layer 2, RWA, SocialFi, AI, DeFi, DePIN, Perpetual DEX, and Prediction Market categories
- Scores and filters every project across 5 metrics: VC backing, narrative fit, funding amount, team quality, and farming viability
- Blocks any project that has gone mainnet, completed a TGE, or already distributed its airdrop
- Tracks your farming positions and alerts you to deadlines, new tasks, and status changes
- Sends an automated 8AM morning digest every day
- Tells you when to stop farming a project

---

## Scoring Framework

Every project is evaluated across 5 metrics and assigned a tier:

| Tier | Meaning |
|------|---------|
| 🏆 S | Near-perfect across all metrics. Narrative dominance, massive upside, confirmed/rumored airdrop |
| 🥇 A | Strong on 4+ metrics. High conviction VC + meta + funding combo |
| 🥈 B | Solid but with gaps — fewer VCs or more competition |
| 🥉 C | Viable on 2–3 metrics. Active community, worth farming if you have bandwidth |
| ❌ Excluded | Below C threshold or outside allowed categories — silently dropped |

Projects outside the 9 allowed categories or requiring any capital to farm are excluded regardless of score.

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Open the main menu with quick-action buttons |
| `/testnets` | Find free active testnet opportunities (scored and filtered) |
| `/funding` | Latest crypto funding rounds from the past 7 days |
| `/news` | Latest airdrop and testnet news |
| `/tracker` | Live airdrop data pulled from Dropstab, Airdrops.io, Layer3, DappRadar, and more |
| `/track [name]` | Add a project to your watchlist and get an instant intel brief |
| `/untrack [name]` | Remove a project from your watchlist |
| `/list` | View all projects you are currently tracking |
| `/positions` | Status update on all your tracked projects |
| `/vcs [name]` | Get the confirmed VC backer list for any project |
| `/faucet [name]` | Verify live faucet status and active quests for a project |
| `/weekly` | Weekly farming summary report for all tracked projects |
| `/stopcheck` | Auto-suggest which tracked projects to stop farming |
| `/digest` | Manually trigger the morning intelligence briefing |
| `/help` | Show all available commands |

---

## Intelligence Sources

**Airdrop Trackers**
- [Dropstab](https://dropstab.com)
- [Airdrops.io](https://airdrops.io)
- [AlphaDrops](https://alphadrops.net)
- [OneClickCrypto](https://oneclickcrypto.com/airdrop-tracker)
- [DappRadar](https://dappradar.com/airdrops)
- [Earni.fi](https://earni.fi)

**Quest Platforms**
- [Layer3](https://layer3.xyz/quests)

**Funding & VC Data**
- [CryptoRank](https://cryptorank.io/funding-rounds)
- [ICODrops](https://icodrops.com)
- [ICOAnalytics](https://icoanalytics.org)
- [Crunchbase](https://www.crunchbase.com)

---

## Tech Stack

- **Python 3.9+**
- **python-telegram-bot** — Telegram bot framework
- **Anthropic API (Claude Haiku 4.5)** — AI with live web search
- **APScheduler** — Daily 8AM digest scheduling
- **python-dotenv** — Environment variable management

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/airdrop-radar.git
cd airdrop-radar
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get your credentials

- **Telegram Bot Token** — Message [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token
- **Telegram User ID** — Message [@userinfobot](https://t.me/userinfobot), copy your numeric ID
- **Anthropic API Key** — Get one at [console.anthropic.com](https://console.anthropic.com)

### 4. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_USER_ID=your_numeric_id_here
ANTHROPIC_API_KEY=your_api_key_here
```

### 5. Run the bot

```bash
python bot.py
```

---

## Running 24/7

For persistent uptime, deploy to a VPS and use PM2 or systemd.

**PM2 (recommended):**
```bash
npm install -g pm2
pm2 start bot.py --interpreter python3 --name airdrop-radar
pm2 save
pm2 startup
```

**Set timezone for correct digest timing (Lagos example):**
```bash
timedatectl set-timezone Africa/Lagos
```

**Free hosting options:**
- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) — Always-free VM
- [Hetzner CX11](https://www.hetzner.com/cloud) — ~€4/month

---

## Security

The bot only responds to your Telegram user ID. Any message from a different user is silently ignored.

**Important:** Never commit your `.env` file. It is already included in `.gitignore`.

If your bot token is ever exposed publicly, revoke it immediately via [@BotFather](https://t.me/BotFather) using `/revoke`.

---

## Project Structure

```
airdrop-radar/
├── bot.py                  # Main bot — all logic, commands, and scheduler
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .gitignore              # Excludes .env and tracked_airdrops.json
└── tracked_airdrops.json   # Auto-generated — persists your watchlist
```

---

## License

MIT License — free to use, modify, and distribute.

---

Built by [@sir-oh](https://github.com/sir-oh)
