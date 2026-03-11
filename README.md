# Nifty F&O Trading Bot — v5

**Professional-grade F&O intelligence system built on Zerodha Kite Connect.**

> Germany Edition — Designed for remote trading with IST-aware scheduling.

---

## Architecture

```
fnobot/
├── config/                 # Configuration & constants
│   ├── __init__.py
│   ├── settings.py         # All paths, thresholds, API keys, symbols
│   └── holidays.py         # NSE trading holiday calendar
│
├── core/                   # Runtime infrastructure
│   ├── __init__.py
│   ├── kite_client.py      # Kite Connect wrapper: login, caching, retries
│   ├── state.py            # BotState dataclass — all mutable runtime state
│   └── scheduler.py        # Market hours, schedule management
│
├── analysis/               # Market analysis engines
│   ├── __init__.py
│   ├── option_chain.py     # Fetch & analyse option chains (PCR, MaxPain, OI)
│   ├── oi_delta.py         # 15-min OI delta tracking & spike detection
│   ├── support_resistance.py  # S/R levels from OI + previous day H/L
│   ├── signals.py          # Signal generation (directional bias)
│   └── trade_setup.py      # Trade setup scoring engine (multi-factor)
│
├── indicators/             # Technical indicator modules (Phases 1–4)
│   ├── __init__.py
│   ├── vwap.py             # Phase 1 — VWAP + bands + weekly AVWAP
│   ├── technicals.py       # Phase 2 — Supertrend, EMA, RSI, HH/LL
│   ├── iv_tracker.py       # Phase 3 — IV per strike, straddle premium, skew
│   ├── oi_concentration.py # Phase 4 — OI walls, pinning score, concentration
│   └── scoring.py          # Unified scoring interface for all indicators
│
├── output/                 # Output & notification layer
│   ├── __init__.py
│   ├── telegram.py         # Telegram messaging (smart splitting, retry)
│   ├── excel_writer.py     # Excel logging engine (all sheets)
│   ├── message_builder.py  # Telegram message formatting
│   └── dashboard/
│       ├── __init__.py
│       ├── generator.py    # HTML dashboard generator
│       └── styles.css      # Dashboard CSS
│
├── data/                   # Data persistence layer
│   ├── __init__.py
│   ├── historic.py         # HistoricData.xlsx read/write
│   └── eod_fetcher.py      # Standalone EOD data fetcher
│
├── utils/                  # Shared utilities
│   ├── __init__.py
│   ├── logger.py           # Centralized logging setup
│   └── helpers.py          # Shared helper functions
│
├── scripts/                # Operational scripts
│   ├── start_bot.bat       # Windows launcher
│   ├── check_token.py      # Token validity check
│   └── backfill.py         # Historical data backfill
│
├── main.py                 # Entry point — CLI, orchestration
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variable template
```

## Quick Start

```bash
# 1. Clone / copy to your machine
# 2. Copy .env.example → .env and fill in your keys
# 3. Install dependencies
pip install -r requirements.txt

# 4. Daily login (each morning before market opens)
python main.py --login

# 5. Start the bot
python main.py

# 6. Or use the Windows launcher
scripts\start_bot.bat
```

## Key Design Principles

- **Single source of truth** for all config (`config/settings.py`)
- **No global mutable state** — everything flows through `BotState`
- **Structured logging** via Python's `logging` module
- **Retry with backoff** on all Kite API calls
- **Instrument caching** — NFO instruments fetched once per day
- **Smart Telegram splitting** — respects HTML tags
- **Holiday-aware scheduling** — skips NSE holidays

## Utility: LLM wrapper

A tiny helper is included (`fnobot/llm_wrapper.py`) that can be used to send
prompts to Claude Sonnet or OpenAI Opus (Responses API).  It doesn’t depend on
anything beyond ``requests`` and reads credentials from the environment:

A separate utility (`fnobot/convert_to_md.py`) is also available for
**converting Word, Excel, and PDF documents into Markdown**.  Run it like:

```powershell
python -m fnobot.convert_to_md "path\to\file.docx" "path\to\file.xlsx" "path\to\file.pdf"
```

If you’d rather not invoke it manually, there’s a built-in watch mode that
monitors directories and automatically converts any supported file that is
created or modified anywhere underneath them (recursive watch):

```powershell
# watch entire repo and subfolders
python -m fnobot.convert_to_md --watch .

# watch only the Market Data tree
python -m fnobot.convert_to_md --watch "Market Data"
```

The script will run until you press **Ctrl‑C**, converting every DOCX/XLSX/PDF
dropped or copied anywhere inside the watched directories.
The tool always writes a `.md` file adjacent to the source and is handy for
archiving reports or preparing documentation.
* ``ANTHROPIC_API_KEY`` for Claude
* ``OPENAI_API_KEY`` for Opus

Example usage::

    from fnobot.llm_wrapper import LLMClient

    client = LLMClient()
    print(client.claude("Amplitude of market noise?"))
    print(client.opus("Translate to German."))

In addition there's now a tiny CLI gateway that wraps the same functionality
and is suitable for use as a Copilot chat tool:

```bash
# basic Claude prompt via the CLI
python -m fnobot.claude_tool "What is the weather in Mumbai?"

# specify additional parameters
python -m fnobot.claude_tool --model claude-sonnet-4.6 --temperature 0.2 \
    "Explain VWAP"
```

When registered as a chat tool you can invoke it from the Copilot window like::

    @tool claude
    {
        "prompt": "Write a haiku about options",
        "temperature": 0.5
    }

and the tool will reply with the JSON response returned by Claude.

This makes it easy to experiment with external LLMs without modifying the main
bot code.

### Testing the wrapper

You can verify that the helper behaves as expected in two ways:

1. **Manual CLI** – set your key(s) and run from the workspace root::

       # using PowerShell
       $env:ANTHROPIC_API_KEY = "sk-..."
       python -m fnobot.llm_wrapper claude "What time is it?"

       # or with Opus
       $env:OPENAI_API_KEY = "sk-..."
       python -m fnobot.llm_wrapper opus "Ping"

   A successful call will print the JSON returned by the service.  If the key
   is missing you'll see the `RuntimeError` message defined in the code.

2. **Automated test** – a simple pytest file has been added at
   `tests/test_llm_wrapper.py`.  It checks that missing keys raise an error and
   performs a smoke network request when the appropriate API key is present.
   Run it with the normal test command:

       pip install -r requirements.txt           # if you haven't already
       pip install pytest
       pytest tests/test_llm_wrapper.py

   The network tests are skipped unless the corresponding environment variable
   is defined, so you can safely run the suite without having any keys set.


- **Type hints** throughout for IDE support and maintainability
