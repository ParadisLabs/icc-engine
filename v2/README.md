# ICC V2 — Multi-Asset Intelligence Engine

ICC V2 is being developed alongside the existing ICC engine, not as a replacement commit. The current engine remains untouched while V2 establishes a new data contract, provider adapters, feature pipeline, strategy evaluation, historical memory, and demo execution boundary.

## Initial architecture

```text
Market venues / licensed providers
        |
Provider adapters (venue-specific)
        |
Normalized market-data contracts
        |
Quality checks + timestamp alignment
        |
Feature and market-flow calculations
        |
ICC setup hypotheses + historical validation
        |
Opportunity ranking + portfolio-level constraints
        |
Demo execution adapter
        |
Immutable event ledger + performance analysis
```

## First adapter: Binance public Spot REST

`icc_v2.data.binance_public.BinancePublicSpot` is the first integration spike. It uses public market endpoints only and does not accept API keys or submit orders. It exposes:

- exchange instrument metadata and trading status;
- 24-hour ticker statistics;
- OHLCV candles with actual exchange-reported base-asset volume and quote-asset volume;
- recent public trades;
- current order-book snapshots.

This first adapter is intentionally a **REST snapshot adapter**. It is not yet a streaming order-flow engine. A current depth snapshot cannot reconstruct historical depth changes, and REST polling must not be presented as continuous order flow. A later WebSocket adapter must maintain sequence-aware local books and capture trade events without gaps.

## Data semantics

- Every record carries venue, market type, instrument, event time and receive time where applicable.
- Candle `volume` is base-asset volume; `quote_volume` is quote-asset volume.
- Public trades preserve exchange trade ID, price, quantity, quote quantity, timestamp and buyer-is-maker flag. Aggressor-side interpretation must be documented and tested before use.
- Order-book snapshots are point-in-time bid/ask levels, not a consolidated market book.
- No synthetic volume, candle-range weighting or inferred global forex order book is allowed to masquerade as exchange-observed flow.
- Provider failures, rate limits, malformed payloads and stale data must fail visibly; no silent substitution.

## Scope and safety

- Initial adapter: Binance Spot public data only.
- No private account access, order placement, leverage changes or live trading.
- No broker/prop-firm credentials in this package.
- Future execution begins against an explicitly configured demo environment, with platform rules, a kill switch and a complete order/fill ledger.
- Crypto, FX, futures, equities and CFDs require separate market metadata and source-quality policies. They must not be treated as interchangeable.

## Run the adapter

From the repository root:

```bash
PYTHONPATH=v2 python -m unittest discover -s v2/tests -v
```

The adapter uses Python's standard library and has no mandatory third-party dependency.

## Planned next steps

1. Add unit tests for response parsing, retries, rate-limit handling and invalid symbols.
2. Add the WebSocket transport loop with reconnect, ping/pong, trade deduplication and automatic resnapshot on depth sequence gaps. The pure depth-book reconstruction primitive is now in place.
3. Add a normalized event store and data-quality monitoring.
4. Add instrument discovery across multiple exchanges, with per-venue capability metadata.
5. Build historical setup evaluation before enabling any demo execution.
6. Connect the demo execution adapter only after the selected prop firm's trial API and rules are verified.

## Fincept relationship

Fincept is an integration reference and possible connector host, not a required runtime dependency. ICC V2 owns its normalized contracts and can consume Fincept-provided data where the source, timestamp, licence and data semantics are known. Do not copy Fincept source code into this repository without resolving its licensing terms.


## Added V2 strategy and futures work

The current V2 branch now also includes:
- A public Binance USD-M perpetual adapter for active perpetual discovery, klines, aggregate trades and depth snapshots. Klines preserve exchange-reported base volume, quote volume, trade count and taker-buy volume fields.
- A rebuilt trend/sweep setup hypothesis using normalized closed bars, 15m signal conditions and 1h/daily confirmation. Actual relative volume is scored only when present; missing volume is never replaced with a fabricated neutral value.
- Conservative OHLC backtest primitives: next-bar-open entry, stop-first treatment when stop and target are both touched in one candle, explicit fee/slippage assumptions, MFE/MAE and expectancy/drawdown summaries.

These are research components only. A full FX adapter, live WebSocket transport, cross-asset universe scanner, durable V2 memory and walk-forward portfolio evaluation remain outstanding. FX spot has no single consolidated exchange order book; any broker tick volume or futures volume must be identified by source and market type.

The V2 test suite runs with:

```bash
PYTHONPATH=v2 python -m unittest discover -s v2/tests -v
```


## Binance Spot live stream transport

`icc_v2.data.binance_stream.BinanceSpotWebSocket` adds a read-only combined
trade and diff-depth stream consumer. Install the optional runtime dependency
with `pip install websocket-client`. The stream uses public endpoints only.

- Subscribes to trade and 100 ms diff-depth streams for an explicit symbol list.
- Deduplicates public trades by exchange trade ID and preserves the buyer-is-maker
  flag plus the corresponding aggressor-side interpretation.
- Buffers depth events and bridges them to a REST snapshot using the existing
  sequence-aware book reconstruction primitive.
- Emits depth only after the local book is synchronized. Sequence gaps invalidate
  the book and propagate an error so the caller reconnects and resnapshots.
- Bounds the bootstrap buffer and uses bounded exponential reconnect backoff.

This is an initial transport component, not yet a continuously running service,
persistent event store, or multi-venue feed manager. A socket session ending
invalidates its local books; consumers must treat the next session as a fresh
bootstrap. The event callback must persist or forward events if retention is
required. WebSocket transport tests use injected sockets and REST snapshots.

## Additional implementation status (development branch)

The current V2 development work also includes:
- Read-only Binance Spot WebSocket ingestion for public trades and diff-depth updates, with REST snapshot bootstrap, sequence-aware local books, trade deduplication, reconnect backoff, bounded depth buffering and resnapshot recovery. The stream consumer is optional and requires `websocket-client` at runtime.
- A bounded Spot universe shortlist using one exchange metadata request and one all-symbol 24-hour ticker snapshot. It filters active pairs by quote asset, excludes stablecoin/leveraged-token base assets, applies a minimum reported quote-turnover threshold, and caps the shortlist. This is a liquidity shortlist, **not** an ICC signal ranking.
- SQLite-backed setup memory with idempotent candidate recording, immutable finalized outcomes, persistence across process restarts and grouped expectancy/win-rate summaries. This stores evidence; it does not yet automatically tune strategy parameters.

The isolated feature-branch suite currently passes 39 tests. This is unit-test validation only: it does not establish profitability, validate a live exchange session, or prove feed availability under sustained load.

Still outstanding: a true cross-asset setup ranker, FX provider adapter with source-specific volume semantics, walk-forward portfolio evaluation, durable market-event ingestion/retention policy, and a demo-only execution adapter with risk controls and explicit human authorization.


### FX data semantics and practice adapter

A read-only OANDA practice candle adapter is now available in `icc_v2.data.oanda_fx`. It requires an OANDA practice API token supplied at runtime and is hard-restricted to the practice REST host. It requests instrument candles only; it does not access accounts, orders, positions or live endpoints.

OANDA's candle `volume` field represents the **number of prices created during the candle**, so ICC records it as `price_update_count` with `volume_kind="broker_price_update_count"`. It is not exchange-traded volume and must not be combined with Binance base/quote volume or futures contract volume. See the [OANDA candle API schema](https://github.com/oanda/v20-openapi/blob/master/yaml/separate/v20_instrument.yaml) and [OANDA authentication documentation](https://developer.oanda.com/rest-live-v20/authentication/).

### Walk-forward evaluation

The initial chronological walk-forward evaluator separates earlier candidate outcomes from later test blocks and admits training outcomes only when their simulated exits precede the first test signal. It reports training/test outcome metrics by fold. It is a setup-level evaluation utility, **not yet a portfolio simulator**: overlapping positions, capital allocation, cross-asset correlation, margin, and shared risk limits remain to be implemented.

The current isolated feature-branch test suite passes 46 tests. This is software validation only, not a profitability claim or a substitute for a sustained live-feed soak test.


### Spot and perpetual universe discovery

The liquidity shortlist now has separate Binance Spot and USD-M perpetual scanners. Each uses one instrument-metadata request and one all-symbol 24-hour ticker snapshot, preserves the market type, and ranks only within its own venue/market-type dataset. Quote turnover from Spot and perpetual markets must not be added together or treated as interchangeable.


### Initial portfolio risk simulation

A portfolio-level research simulator now admits candidate paths chronologically and enforces configurable per-trade risk, aggregate open-risk, maximum concurrent positions, UTC-day realized-loss and peak-to-equity drawdown limits. It applies the existing conservative per-trade OHLC simulator and reports realized equity and rejection reasons.

This remains a simplified portfolio model. It does not yet model instrument-specific margin, funding, liquidation, partial fills, spread/market impact, cross-asset correlation, or intrabar mark-to-market portfolio risk. Do not use its results as a live risk engine.
