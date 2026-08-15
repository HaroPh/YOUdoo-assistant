"""Entry point for the ERP backend.

On Windows, psycopg3's async mode is incompatible with the ProactorEventLoop
("Psycopg cannot use the 'ProactorEventLoop'..."). uvicorn 0.46 hardcodes the
ProactorEventLoop for single-process Windows via its loop *factory* (it creates
the loop directly, ignoring the asyncio event-loop *policy*). So we cannot fix
this by setting a policy — we must drive uvicorn's ASGI server inside a
SelectorEventLoop we create ourselves.

Run:  python run.py     (from the backend/ directory)
"""
import asyncio
import logging
import os
import sys

from uvicorn import Config, Server


def main() -> None:
    # Dòng này thuộc về ĐIỂM VÀO TIẾN TRÌNH, không phải cấp module — cùng lý
    # do đã ghi ở mcp-servers/odoo/server.py: đặt ở cấp module sẽ gắn handler
    # vào root logger của mọi tiến trình pytest/công cụ chỉ `import run`.
    #
    # uvicorn.Config dùng log_config mặc định, và cấu hình đó CHỈ chạm các
    # logger tên "uvicorn*" — root logger không được đụng tới. Không có dòng
    # dưới đây, toàn bộ 68 chỗ fail_read/fail_write (logger.exception) chỉ ra
    # được stderr nhờ handler `lastResort` của Python: WARNING trở lên, không
    # timestamp, không level, không tên logger — và im lặng biến mất nếu sau
    # này ai đó thêm một dictConfig. stderr của tiến trình backend được
    # start-dev.ps1 chuyển vào logs/backend_err.log.
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = Config(
        "src.main:app",
        host=os.environ.get("BACKEND_HOST", "0.0.0.0"),
        port=int(os.environ.get("BACKEND_PORT", "8002")),
    )
    server = Server(config)

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    else:
        server.run()


if __name__ == "__main__":
    main()
