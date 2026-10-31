"""Start one explicitly configured experimental speech API process."""
from __future__ import annotations

import argparse
import os

from .app import SpeechApplication
from .settings import SpeechSettings
from .rkvoice_backend import RkvoiceKokoroBackend


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        settings = SpeechSettings.from_env()
        backend = RkvoiceKokoroBackend.from_env()
    except (ValueError, OSError):
        parser.error("speech configuration is unavailable or invalid")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "2")
    import uvicorn
    uvicorn.run(SpeechApplication(backend, settings), host=args.host, port=args.port,
                workers=1, lifespan="on", ws="none", log_level="warning", access_log=False,
                server_header=False, limit_concurrency=16)


if __name__ == "__main__":
    main()
