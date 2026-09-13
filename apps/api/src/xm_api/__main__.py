from __future__ import annotations

import os

import uvicorn

from xm_core.db.session import ensure_psycopg_compatible_loop


def main() -> None:
    ensure_psycopg_compatible_loop()
    uvicorn.run(
        "xm_api.app:create_app",
        factory=True,
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104 - container listens on all interfaces
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
