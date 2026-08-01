"""``python -m gpu_hub`` -- run the hub with the configured host/port."""

from __future__ import annotations

import logging

import uvicorn

from .config import config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    uvicorn.run(
        "gpu_hub.main:app",
        host=config.host,
        port=config.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
