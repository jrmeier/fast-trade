# Roadmap

North star from the README: *If backtests are fast, strategies are cheap.*

Fast Trade should stay a **fast, YAML-driven research loop** — not a full trading terminal or a generic ML platform. The strongest path is programmable, agent-friendly backtesting infrastructure.

## Where We Are Today

Three layers that mostly work well together:

| Layer | What exists | Maturity |
|---|---|---|
| **Core engine** | YAML strategies → indicators → enter/exit logic → rich summary metrics | Strong; recently optimized (~3x on hot paths) |
| **Data + CLI** | Archive download (Binance/Coinbase), `ft backtest`, saved runs, logs | Solid |
| **Research tooling** | Evolver (GA), regime models, HMM screener, FXMacroData, MCP server | Growing, uneven |

Recent history reinforces a specific bias:

- **2.1.0** added agent-facing tools (MCP, HMM screen, macro context).
- **Terminal UI was removed** — a deliberate simplification toward headless CLI + agents.
- **`Live.plan.md` exists but `fast_trade/live/` does not** — live execution is planned, not shipped.
- **Issue #20 (AutoML)** is still open and aligns with community interest in mass strategy search.

So the project is pivoting from “interactive terminal app” toward **programmable, agent-friendly backtesting infrastructure**.

## Recommended Direction

### 1. Double down on the core loop (highest ROI)

Make this the product:

```text
download data → define strategy in YAML → backtest fast → filter with rules → iterate / evolve → save & compare runs
```

That loop is already differentiated by:

- Low ceremony (YAML datapoints + logic, no Python boilerplate)
- Speed (recent action-engine and simulation work)
- Rich built-in metrics and rules filtering
- Tight archive integration

**Next investments here:**

- Batch / parallel backtest runner (`run_parallel_example.py` suggests this was started)
- Better “strategy search” UX on top of the evolver — grid search, walk-forward, out-of-sample splits
- Stronger saved-run comparison (`ft backtests list/show` is a start; diffing summaries across runs would help a lot)

This directly answers issue #20 without jumping straight to XGBoost: **use fast backtests as the search engine**, not ML as the strategy itself.

### 2. Lean into the agent/MCP angle (differentiator)

The README already positions MCP as a first-class surface. That’s a smart niche: most backtest libraries are library-only; few expose **`ft backtest`**, **`hmm_screen`**, and **`fxmacrodata_macro_context`** to agents.

**Worth expanding:**

- MCP tools for `evolve`, `backtests list/show`, and batch parameter sweeps
- Structured JSON outputs (not just CLI stdout parsing)
- Example agent workflows: “screen universe → backtest top N → evolve best → report”

This fits the post-terminal direction and matches how the project is already used (closed-source live data + MCP).

### 3. Complete the research → paper path before live trading

`Live.plan.md` describes a full WebSocket live stack (aggregator, DuckDB, executor). That’s a large jump in scope and operational risk.

A more coherent sequence:

```text
Fast backtest → Walk-forward / evolve → Paper portfolio on candle close → Live WS execution
```

`ft portfolio` already exists (paper, stateful, JSONL logs). The gap is connecting it cleanly to:

- Archive or REST candle updates (not full tick streaming yet)
- The same compiled action logic used in backtests
- Scheduled re-evaluation on new bars

That gives **backtest ↔ paper parity** without building the entire live stack at once. Live WebSocket execution should be phase 2+, probably Binance US or Coinbase first, paper-only initially — exactly as `Live.plan.md` suggests.

### 4. Grow ML carefully — as search and context, not as a black box

The ML pieces fit best when they **augment** the YAML engine:

| Tool | Good use | Risky use |
|---|---|---|
| **Evolver (PyGAD)** | Tune indicator params, freq, stop loss | Overfitting without OOS validation |
| **HMM screener** | Rank symbols / regimes before backtesting | Replacing strategy logic entirely |
| **Regime models** | Filter when a strategy should run | Opaque “ML decides trades” |
| **FXMacroData** | Context for FX/macro-aware strategies | Unrelated to crypto backtests |

For issue #20, a pragmatic path is:

1. **Indicator × parameter grid** over existing transformers
2. **Paired-indicator search** (community suggestion)
3. **Optional** label peaks/troughs and train a classifier — but keep execution in the existing enter/exit engine

Avoid becoming “yet another AutoML trading framework.” The edge is **speed + declarative strategies + agent tooling**.

### 5. Deprioritize or avoid (for now)

- **Rebuilding the interactive terminal** — removed for good reasons (complexity, CI pain, limited value)
- **Competing with full bots** (Freqtrade, Jesse, etc.) on live order management
- **Broad exchange support** before one exchange’s paper path is rock-solid
- **Heavy dependencies** (Numba, TA-Lib, XGBoost) unless gated as optional extras

## Concrete Roadmap

### Near term (stabilize 2.1, sharpen the loop)

1. Ship 2.1.0 (release prep)
2. Document an end-to-end “research workflow” (screen → backtest → evolve → compare)
3. Add batch backtest + summary ranking CLI
4. Extend MCP with evolve and backtest-comparison tools

### Medium term (close the simulation gap)

5. Candle-close paper runner wired to archive updates + portfolio
6. Walk-forward / train-test split in evolver config
7. Optional Numba JIT for simulation kernel (already teed up in `RUN_ANALYSIS_PLAN.md`)

### Long term (only if paper path is solid)

8. Implement `fast_trade/live/` per `Live.plan.md`, paper first
9. Hyperliquid integration (already referenced in HMM screen)

## Strategic Positioning

**Position fast-trade as the fastest path from idea → tested YAML strategy → iterated improvement, with agents and paper trading as first-class citizens — not as a live trading bot or AutoML platform.**

That stays true to the original motivation, builds on recent work (MCP, performance, HMM, evolver), and avoids the scope creep that the terminal and full live stack would reintroduce.

## Priority Forks

The highest-leverage axes, if choosing where to focus next:

1. **Research platform** — batch search, walk-forward, better run comparison
2. **Agent infrastructure** — MCP-first workflows
3. **Paper → live bridge** — portfolio runner + eventual WebSocket stack

## Related Docs

- `Live.plan.md` (repo root) — live WebSocket execution plan
- `ACTION_ENGINE_PLAN.md` — action-path optimization notes
- `RUN_ANALYSIS_PLAN.md` — simulation-loop optimization notes
- Issue [#20](https://github.com/jrmeier/fast-trade/issues/20) — AutoML / strategy search discussion
