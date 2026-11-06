# ICC V2 execution boundary

Broker-neutral execution contracts and demo-only safety gates. Live trading is unsupported by this package. Execution remains disabled by default until an explicit demo adapter, account-environment verification, and operator configuration are added.

## cTrader adapter (demo-only foundation)

`ctrader.py` uses Spotware's official `ctrader-open-api` Python SDK
(`v2/requirements-ctrader.txt`). It pins the transport to the cTrader demo
endpoint and provides application-auth, account-list and account-auth request
builders plus the OAuth authorization URL helper.

The current increment intentionally has **no order submission, amendment or
position-close implementation**. Those methods fail closed. Do not interpret
this adapter foundation as an active trading connection.

For the first authorization, use the `accounts` OAuth scope (read-only).
Only after connection, account identity, symbol metadata, volume units,
minimum/step sizes, market status, quotes, stop-distance rules and risk checks
are verified should a separately reviewed demo-trading scope be considered.
Never request or store a live-account token in this workflow.

The future runtime configuration must be stored in GitHub Actions Secrets,
not committed to the repository:
- `CTRADER_CLIENT_ID`
- `CTRADER_CLIENT_SECRET`
- `CTRADER_REDIRECT_URI`
- `CTRADER_ACCESS_TOKEN`
- `CTRADER_ACCOUNT_ID`

These are documentation for a later authorized connection; no secrets are
required or consumed by the current CI tests. The user must create a cTrader
Open API application and explicitly authorize the demo account before any
connection can occur.
