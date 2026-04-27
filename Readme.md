# Oga Assistant — SME Inventory Agent

An AI-powered inventory management system for Nigerian small and medium businesses. Built with FastAPI, SQLite, and Google Gemini.

## What it does

- Tracks stock levels across all products
- Alerts when items fall below reorder thresholds
- Analyses sales velocity over the last 7, 14, or 30 days
- Suggests what to restock, how much to order, from which supplier, and estimated cost in Naira
- Records new stock arrivals
- Conversational interface — owners ask questions in plain English

## Project structure

```
sme-agent/
├── backend/
│   ├── main.py                  # FastAPI server
│   ├── schemas.py               # Pydantic data models
│   ├── agent/
│   │   ├── inventory_agent.py   # Gemini LLM agent + agentic loop
│   │   └── tools.py             # Agent tools (check_stock, reorder, etc.)
│   └── database/
│       ├── models.py            # SQLite table definitions
│       ├── crud.py              # Database operations
│       └── seed.py              # Sample Nigerian provisions store data
├── frontend/
│   └── index.html               # Chat UI
├── requirements.txt
└── .env                         # API keys (never commit this)
```

## Security

Never commit your `.env` file. It contains your API key and must stay local.
The `.gitignore` already excludes it. If you accidentally expose a key,
revoke it immediately at aistudio.google.com/apikey and generate a new one.

## Setup

### 1. Clone and create virtual environment
```bash
git clone <repo-url>
cd sme-agent
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
Create a `.env` file in the root:
```
GEMINI_API_KEY=your-key-here
```
Get a free API key at: https://aistudio.google.com/apikey

### 4. Set up the database
```bash
cd backend/database
python seed.py
```

### 5. Run the server
```bash
cd backend
uvicorn main:app --reload
```

### 6. Open the app
Visit http://127.0.0.1:8000 in your browser.

## Example questions to ask

- "What is running low in the store?"
- "What should I restock this week and how much will it cost?"
- "How has Indomie been selling this week?"
- "Show me all stock levels"
- "I just received 20 bags of Dangote Rice"

## Tech stack

| Layer     | Technology          |
|-----------|---------------------|
| Backend   | Python, FastAPI      |
| Database  | SQLite               |
| AI Agent  | Google Gemini 2.5 Flash |
| Frontend  | HTML, CSS, JavaScript |

## Roadmap

- [ ] Finance agent — profit tracking, expense management
- [ ] Sales agent — customer inquiry handling
- [ ] Orchestrator — single interface across all agents
- [ ] WhatsApp integration
- [ ] Multi-business support