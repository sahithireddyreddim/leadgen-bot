# B2B Lead Generation System

An autonomous, AI-powered B2B lead generation pipeline that finds companies with document-heavy operations, researches them, and sends personalized cold outreach emails.

**100% free to run** – uses Groq (free LLM), DuckDuckGo (free search), and your choice of free email provider.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     PIPELINE                            │
│                                                         │
│  Agent 1          Agent 2          Agent 3              │
│  Lead Finder  →  Research      →  Outreach              │
│                                                         │
│  DuckDuckGo      Groq LLM          Groq LLM             │
│  web search      (free tier)       (free tier)          │
│  (no API key)    + web scraping    + email sending      │
│       ↓               ↓                 ↓               │
│   SQLite DB      Fit Score ≥ 60    Gmail/Brevo/Resend   │
└─────────────────────────────────────────────────────────┘
```

---

## Free Tools Used

| Tool | Purpose | Free Limit |
|------|---------|------------|
| [Groq](https://console.groq.com) | LLM for research + email writing | ~14,400 req/day |
| [DuckDuckGo Search](https://pypi.org/project/duckduckgo-search/) | Lead discovery | Unlimited |
| [Gmail SMTP](https://myaccount.google.com/apppasswords) | Email sending | 500/day |
| [Brevo](https://www.brevo.com) | Email sending (alternative) | 300/day |
| [Resend](https://resend.com) | Email sending (alternative) | 100/day |
| [Hunter.io](https://hunter.io) | Email finder (optional) | 25/month |
| SQLite | Database | Unlimited |
| [Render.com](https://render.com) | Cloud deployment | 750 hrs/month |

---

## Quick Start (Local)

### Step 1 – Clone/Extract and Install

```bash
cd b2b-lead-gen
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 – Configure

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
GROQ_API_KEY=your_key_here          # Get free at console.groq.com
SENDER_EMAIL=you@gmail.com
SENDER_NAME=Your Name
EMAIL_PROVIDER=gmail
GMAIL_APP_PASSWORD=xxxx_xxxx_xxxx   # See below
DAILY_TARGET=10
```

**Getting a Gmail App Password:**
1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Security → 2-Step Verification (enable if not done)
3. Security → App passwords → Create → Name it "Lead Gen"
4. Copy the 16-character password into `.env`

### Step 3 – Run

```bash
# Full pipeline (find → research → email)
python main.py

# Test without sending emails first (recommended first time)
python main.py --dry-run

# Run specific stages
python main.py --stage find       # Just find leads
python main.py --stage research   # Just research
python main.py --stage outreach   # Just send emails

# Set custom target
python main.py --target 5 --dry-run
```

### Step 4 – Monitor via Dashboard

```bash
python dashboard.py
# Open http://localhost:5000
```

---

## Deployment on Render.com (Free)

### Prerequisites
- GitHub account
- Render.com account (free at [render.com](https://render.com))

### Steps

**1. Push to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/b2b-lead-gen.git
git push -u origin main
```

**2. Deploy to Render**
1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New → Blueprint**
3. Connect your GitHub repo
4. Render will detect `render.yaml` automatically

**3. Set Environment Variables**

In the Render dashboard, for both services, add:
- `GROQ_API_KEY` → your Groq API key
- `SENDER_EMAIL` → your email
- `SENDER_NAME` → your name
- `GMAIL_APP_PASSWORD` → Gmail app password
- `EMAIL_PROVIDER` → `gmail`

**4. Access Dashboard**

Your dashboard will be at: `https://b2b-lead-gen-dashboard.onrender.com`

**Free Tier Note:** Render's free tier spins down after 15 min inactivity. The cron job will still run on schedule. To keep the dashboard always-on, consider [Fly.io free tier](https://fly.io).

---

## Alternative Deployments

### Fly.io (always-on free tier)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
fly auth login
fly launch
fly secrets set GROQ_API_KEY=your_key SENDER_EMAIL=you@gmail.com ...
fly deploy
```

### GitHub Actions (Scheduled, no server needed)

Create `.github/workflows/pipeline.yml`:

```yaml
name: Run Lead Gen Pipeline

on:
  schedule:
    - cron: '0 9 * * 1-5'   # 9 AM UTC, Mon-Fri
  workflow_dispatch:          # Manual trigger

jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python main.py --target 10
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_NAME: ${{ secrets.SENDER_NAME }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          EMAIL_PROVIDER: gmail
          DAILY_TARGET: "10"
```

Add secrets in GitHub → Settings → Secrets → Actions.

---

## Scaling Up (100–200 emails/day)

1. **Increase `DAILY_TARGET`** in `.env` to `100` or `200`
2. **Email Provider**: Switch to Brevo (300/day free) for higher volume
3. **Reduce `DELAY_BETWEEN_EMAILS`** to `15` seconds (still safe)
4. **Run twice daily**: Add a second cron schedule `0 14 * * 1-5` (2 PM UTC)

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | – | **Required.** Free at console.groq.com |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `SENDER_EMAIL` | – | **Required.** Your sending email |
| `SENDER_NAME` | – | **Required.** Your display name |
| `EMAIL_PROVIDER` | `gmail` | `gmail` \| `brevo` \| `resend` |
| `GMAIL_APP_PASSWORD` | – | 16-char app password (Gmail only) |
| `BREVO_SMTP_USER` | – | Brevo SMTP username |
| `BREVO_SMTP_PASSWORD` | – | Brevo SMTP password |
| `RESEND_API_KEY` | – | Resend API key |
| `DAILY_TARGET` | `10` | Emails to send per run |
| `MIN_FIT_SCORE` | `60` | Minimum score to send outreach |
| `DELAY_BETWEEN_EMAILS` | `30` | Seconds between emails |
| `HUNTER_API_KEY` | – | Optional. Hunter.io email finder |
| `GOOGLE_API_KEY` | – | Optional. Google Custom Search |
| `GOOGLE_CSE_ID` | – | Optional. Google search engine ID |

---

## Project Structure

```
b2b-lead-gen/
├── agents/
│   ├── lead_finder.py      # Agent 1: DuckDuckGo search
│   ├── research_agent.py   # Agent 2: Groq analysis
│   └── outreach_agent.py   # Agent 3: Email generation + sending
├── utils/
│   ├── scraper.py          # Web scraping utilities
│   ├── email_finder.py     # Contact email discovery
│   ├── email_sender.py     # Gmail / Brevo / Resend
│   └── database.py         # SQLite operations
├── config/
│   └── settings.py         # Environment-based config
├── data/                   # SQLite DB + logs (git-ignored)
├── main.py                 # Pipeline CLI
├── dashboard.py            # Flask monitoring dashboard
├── requirements.txt
├── .env.example            # Copy to .env and fill in
├── Dockerfile
├── render.yaml             # Render.com deployment
└── README.md
```

---

## FAQ

**Q: Will my emails land in spam?**
A: Use Gmail with a warmed-up account. Keep `DELAY_BETWEEN_EMAILS=30`, stay under 50/day initially. Use your real name and a genuine email address.

**Q: Can I customize the industries targeted?**
A: Yes – edit the `INDUSTRY_QUERIES` list in `agents/lead_finder.py`.

**Q: The LLM isn't generating good emails.**
A: Check your `GROQ_API_KEY` is valid. The fallback template is used when Groq is unavailable.

**Q: How do I check what was sent?**
A: Open the dashboard at `http://localhost:5000` or check `data/leads.db` with any SQLite viewer.

**Q: Can I add my own lead list?**
A: Yes – insert directly into the database or extend `lead_finder.py` to read from a CSV.
