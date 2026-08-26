"""Cycling Coach 后端 CLI 入口

直接跑: python -m cycling_coach
或: pyinstaller --name=cycling-coach backend.spec
"""
import uvicorn

from cycling_coach.config.config import settings


def main() -> None:
    host = getattr(settings, "backend_host", "127.0.0.1")
    port = int(getattr(settings, "backend_port", 8765))
    log_level = getattr(settings, "log_level", "info")
    uvicorn.run(
        "cycling_coach.api.main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
