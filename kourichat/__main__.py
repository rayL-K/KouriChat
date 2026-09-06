"""支持 python -m kourichat 启动。"""

from __future__ import annotations

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
