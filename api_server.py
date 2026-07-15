"""
api_server.py — lightweight FastAPI microservice that exposes the 5s replay
engine to the OpenAlgo React UI.

The backtest is CPU-heavy (pandas-style bar crunching + a synchronous psycopg2
pull), so the actual run is dispatched to a worker thread via asyncio.to_thread —
the ASGI event loop stays responsive and this service stays decoupled from the
live trading engine's CPU (it is a standalone process).

Run:
    uvicorn api_server:app --host 0.0.0.0 --port 8001
    # or: python api_server.py

Then from the Vite/React UI (http://localhost:5173):
    POST http://localhost:8001/api/v1/backtest/run
    { "strategy_name": "ema_retest_v134", "start_time": "2026-06-08", "end_time": "2026-06-20" }
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from run_5s_replay import SUPPORTED_STRATEGIES, run_replay

log = logging.getLogger("api_server")

app = FastAPI(
    title="Backtest 5s Replay Service",
    version="1.0.0",
    description="Standalone microservice wrapping the engine-agnostic 5s replay "
                "engine (SimulatedBroker + StrategyContext) for the OpenAlgo UI.",
)

# CORS. This service runs on a trusted LAN and is called from the OpenAlgo UI on
# arbitrary devices (e.g. http://192.168.1.190:5173, http://192.168.1.234:5173),
# so the default is to allow ALL origins. Override with a comma-separated
# BACKTEST_CORS_ORIGINS="http://host-a:5173,http://host-b:5173" to lock it down.
#
# NOTE: the CORS spec forbids "*" together with credentials, and Starlette will
# refuse to emit a usable Access-Control-Allow-Origin in that combination. This
# API uses no cookies/auth, so we disable allow_credentials whenever origins is
# the wildcard (the OpenAlgo UI's axios client sends no credentials either).
_origins_env = os.environ.get("BACKTEST_CORS_ORIGINS", "*").strip()
if _origins_env == "*":
    ALLOWED_ORIGINS = ["*"]
    ALLOW_CREDENTIALS = False
else:
    ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]
    ALLOW_CREDENTIALS = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# One backtest at a time per worker keeps CPU bounded and predictable; the await
# yields the event loop so health checks / other requests are still served.
_run_lock = asyncio.Lock()


# ── schemas ──────────────────────────────────────────────────────────────────
class BacktestRequest(BaseModel):
    strategy_name: str = Field("ema_crossover", examples=["ema_crossover", "ema_retest_v134"])
    start_time: Optional[str] = Field(None, description="ISO date/time, inclusive (default: full window)")
    end_time: Optional[str] = Field(None, description="ISO date/time, exclusive (default: full window)")
    symbol: Optional[str] = Field(None, description="Contract symbol (default: MNQ, the continuous front-month series)")
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="A strategy version's parameter_json (resolved by the UI from the "
                          "selected version). Remapped + applied for this run; unknown keys ignored.")


class TradeRow(BaseModel):
    entry_time: Optional[str]
    side: str
    entry_price: float
    qty: int
    exit_time: Optional[str]
    exit_price: Optional[float]
    exits: List[str]
    exit_reasons: List[str] = []      # granular trigger per exit (daily_loss_limit, session_end, …)
    realized_pnl: float
    breach: bool
    rescue: bool


class Metrics(BaseModel):
    total_pnl: float
    optimistic_pnl: float
    optimism_gap: float
    max_drawdown: float
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: Optional[float] = None
    expectancy: float = 0.0
    sharpe: Optional[float] = None
    tp_fills: int
    sl_fills: int
    buffer_breaches: int
    bar_close_rescues: int
    sub_bars_5s: int
    strategy_bars_1m: int


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    start: str
    end: str
    applied_params: Dict[str, Any] = {}
    ignored_params: List[str] = []
    metrics: Metrics
    trades: List[TradeRow]


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "strategies": sorted(SUPPORTED_STRATEGIES)}


@app.post("/api/v1/backtest/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> Any:
    if req.strategy_name not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown strategy '{req.strategy_name}'; "
                   f"supported: {sorted(SUPPORTED_STRATEGIES)}",
        )
    async with _run_lock:
        try:
            # Off-load the blocking/CPU-heavy run so the event loop stays free.
            result = await asyncio.to_thread(
                run_replay,
                strategy_name=req.strategy_name,
                symbol=req.symbol,
                start=req.start_time,
                end=req.end_time,
                parameters=req.parameters,
            )
        except ValueError as e:                       # bad strategy / empty data
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:                         # DB down, etc.
            log.exception("backtest run failed")
            raise HTTPException(status_code=500, detail=f"backtest failed: {e}")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8001, reload=False)
