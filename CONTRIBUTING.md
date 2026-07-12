# Contributing

Thanks for your interest in the Agentic Trading Desk!

## Development Setup

```bash
# Clone
git clone https://github.com/Oft3r/agentic-trading-desk.git
cd agentic-trading-desk

# Backend
cd trading-desk
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r agent/requirements.txt

# Frontend
cd frontend
npm install

# Database
docker compose up -d db redis
cd backend && alembic upgrade head

# Start dev servers
docker compose up -d
```

## Running Tests

```bash
cd trading-desk
pytest backend/tests/
pytest agent/tests/
```

## Code Style

- Python: follow PEP 8. The core indicator engine (`scripts/indicators.py`, `scripts/score.py`) is stdlib-only by design.
- TypeScript: follow the existing patterns in the frontend. Use `typescript` for type safety.
- Commit messages: concise and descriptive. Present tense.

## Guardrails

- Never commit `.env` files or credentials
- The `scripts/ibkr_webapi.py` client is read-only by design. Don't add order-placing capabilities without explicit discussion.
- Macro data sources are Investing.com and U.S. Treasury.gov only
- All trading decisions must pass through the three-pillar or momentum-dip scoring engine — no gut feelings

## Questions?

Open an issue or reach out to the maintainer.
