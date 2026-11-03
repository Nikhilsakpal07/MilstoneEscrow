# MilestoneEscrow

**MilestoneEscrow** is an autonomous freelance escrow platform built with **FastAPI**, **Next.js (App Router)**, **PayPal Sandbox REST API**, and an autonomous **Google Antigravity AI QA Agent** powered by Google Gemini.

---

## Features

- **PayPal Escrow Authorization**: Funds are authorized and held securely in escrow upon bounty creation (`intent: "authorize"`).
- **Autonomous QA Agent**: Powered by Google Antigravity & Gemini (`gemini-2.5-pro`), the agent clones freelancer GitHub submissions into isolated sandboxes, runs dependencies, executes test suites, and evaluates code strictly against acceptance criteria.
- **Automated Settlement & Payout**:
  - If evaluation passes: Authorized funds are captured via PayPal API and instantly paid out to the freelancer's PayPal email via PayPal Payouts.
  - If evaluation fails: Funds remain locked in escrow with detailed audit logs saved to PostgreSQL.
- **Modern Next.js Frontend**:
  - Interactive AG Grid dashboard with real-time color-coded bounty statuses (`LOCKED`, `COMPLETED`, `REJECTED`).
  - Integrated PayPal buttons with dynamic order authorization.
  - Freelancer submission portal with live animated evaluation loading indicators.

---

## Tech Stack

- **Backend**: Python 3, FastAPI, SQLAlchemy, PostgreSQL, Requests
- **Payments**: PayPal Sandbox REST API (`/v2/checkout/orders`, `/v2/payments/authorizations`, `/v1/payments/payouts`)
- **AI Agent**: Google Antigravity Python SDK (`google.antigravity`), Google Gemini (`gemini-2.5-pro` / `gemini-2.5-flash`)
- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, `ag-grid-react`, `@paypal/react-paypal-js`

---

## Project Structure

```
├── app/                              # Next.js App Router frontend
│   ├── Providers.tsx                 # PayPal script provider
│   ├── layout.tsx                    # Root layout & navbar
│   ├── globals.css                   # Tailwind & AG Grid CSS
│   ├── page.tsx                      # Dashboard with AG Grid
│   ├── create/
│   │   └── page.tsx                  # Bounty creation with PayPal Buttons
│   └── bounty/
│       └── [id]/
│           └── submit/
│               └── page.tsx          # Submission portal & AI audit display
├── database.py                       # PostgreSQL connection & SessionLocal
├── main.py                           # FastAPI routes & PayPal webhook listener
├── models.py                         # SQLAlchemy models (Bounty, Escrow, AuditLog)
├── paypal_client.py                  # PayPal REST API interactions (auth, capture, payout)
├── qa_agent.py                       # Antigravity QA evaluation agent
├── test_agent.py                     # Standalone test script for the QA agent
├── package.json                      # Frontend dependencies
├── tsconfig.json                     # TypeScript configuration
├── tailwind.config.js                # Tailwind CSS configuration
├── .env.example                      # Environment variable templates
└── README.md
```

---

## Getting Started

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/Nikhilsakpal07/MilstoneEscrow.git
cd MilstoneEscrow

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary requests python-dotenv google-antigravity google-genai

# Configure environment variables
cp .env.example .env
# Edit .env with your PostgreSQL, PayPal Sandbox, and Gemini API credentials

# Run FastAPI backend
uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
# Install Node dependencies
npm install

# Configure frontend environment variables
cp .env.example .env.local
# Set NEXT_PUBLIC_PAYPAL_CLIENT_ID to your PayPal Sandbox Client ID

# Start Next.js development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to access the dashboard.

