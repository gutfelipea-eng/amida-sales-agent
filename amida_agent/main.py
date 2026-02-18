"""Amida AI Sales Agent — main entry point."""

import uvicorn

from amida_agent.config import settings
from amida_agent.database import init_db


def main():
    print("Amida AI Sales Agent starting...")
    init_db()
    print(f"Dashboard: http://{settings.dashboard_host}:{settings.dashboard_port}")
    uvicorn.run(
        "amida_agent.web.app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
