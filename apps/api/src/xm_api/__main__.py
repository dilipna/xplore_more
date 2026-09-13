"""API entrypoint and key administration.

xm-api                                   serve (HOST, PORT)
xm-api keys create --name NAME [--rate N] create a key; the plaintext is printed once
xm-api keys revoke --name NAME           revoke a key (takes effect within 60 s on every instance)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import uvicorn

from xm_api.auth import create_key, revoke_key
from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings


def _serve() -> None:
    uvicorn.run(
        "xm_api.app:create_app",
        factory=True,
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104 - container listens on all interfaces
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        # uvicorn's "asyncio" loop setup creates a ProactorEventLoop on Windows regardless of the
        # policy, which psycopg async cannot use; "none" keeps the selector policy set in main().
        loop="none" if sys.platform == "win32" else "asyncio",
    )


async def _keys(action: str, name: str, rate: int) -> int:
    engine = make_engine(get_settings())
    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            if action == "create":
                key = await create_key(session, name, rate)
                print(json.dumps({"name": name, "rate_per_minute": rate, "api_key": key}))
                print("Store this key now; only its hash is kept.", file=sys.stderr)
                return 0
            revoked = await revoke_key(session, name)
            print(json.dumps({"name": name, "revoked": revoked}))
            return 0 if revoked else 1
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    ensure_psycopg_compatible_loop()
    parser = argparse.ArgumentParser(prog="xm-api")
    sub = parser.add_subparsers(dest="command")
    keys = sub.add_parser("keys", help="manage API keys")
    keys.add_argument("action", choices=["create", "revoke"])
    keys.add_argument("--name", required=True)
    keys.add_argument("--rate", type=int, default=120, help="requests per minute")
    args = parser.parse_args(argv)
    if args.command == "keys":
        return asyncio.run(_keys(args.action, args.name, args.rate))
    _serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
