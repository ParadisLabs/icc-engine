"""cTrader Open API demo adapter boundary for ICC V2.

Uses Spotware's official ctrader-open-api Python SDK. The adapter is deliberately
demo-only and read-only in this increment: it can construct an authenticated
transport and account-auth requests, but it cannot submit or modify orders.
No credentials are read from source files.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode


class CTraderConfigurationError(ValueError):
    """Missing or unsafe cTrader configuration."""


class CTraderExecutionDisabled(RuntimeError):
    """Order actions are intentionally unavailable in the current release."""


@dataclass(frozen=True)
class CTraderDemoConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    access_token: str
    account_id: int
    environment: str = "demo"

    def __post_init__(self) -> None:
        for name in ("client_id", "client_secret", "redirect_uri", "access_token"):
            if not getattr(self, name) or not getattr(self, name).strip():
                raise CTraderConfigurationError(f"{name} is required")
        if self.account_id <= 0:
            raise CTraderConfigurationError("account_id must be positive")
        if self.environment.lower() != "demo":
            raise CTraderConfigurationError("ICC cTrader adapter is restricted to demo accounts")


class CTraderDemoAdapter:
    """Create Spotware SDK requests for a demo account; never sends orders."""

    venue = "ctrader"
    environment = "demo"
    market_type = "broker_cfd"

    def __init__(self, config: CTraderDemoConfig):
        if config.environment.lower() != "demo":
            raise CTraderConfigurationError("demo environment required")
        self.config = config

    @staticmethod
    def authorization_url(client_id: str, redirect_uri: str, *, scope: str = "accounts") -> str:
        if scope not in {"accounts", "trading"}:
            raise CTraderConfigurationError("scope must be accounts or trading")
        if not client_id or not redirect_uri:
            raise CTraderConfigurationError("client_id and redirect_uri are required")
        query = urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "product": "web",
        })
        return "https://id.ctrader.com/my/settings/openapi/grantingaccess/?" + query

    def build_client(self):
        """Return an SDK client pointed exclusively at Spotware's demo endpoint."""
        try:
            from ctrader_open_api import Client, EndPoints, TcpProtocol
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional dependency: pip install ctrader-open-api"
            ) from exc
        return Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)

    def application_auth_request(self):
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
        request = ProtoOAApplicationAuthReq()
        request.clientId = self.config.client_id
        request.clientSecret = self.config.client_secret
        return request

    def account_list_request(self):
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetAccountListByAccessTokenReq
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = self.config.access_token
        return request

    def account_auth_request(self):
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAccountAuthReq
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = self.config.account_id
        request.accessToken = self.config.access_token
        return request

    def submit_order(self, *_args, **_kwargs):
        raise CTraderExecutionDisabled(
            "cTrader order submission is disabled; demo execution requires a separately reviewed release"
        )

    def amend_order(self, *_args, **_kwargs):
        raise CTraderExecutionDisabled("cTrader order modification is disabled")

    def close_position(self, *_args, **_kwargs):
        raise CTraderExecutionDisabled("cTrader position actions are disabled")
