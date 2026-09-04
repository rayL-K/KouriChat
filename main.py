"""KouriChat 1.5 主程序入口。

执行方式：
    python main.py              # 直接启动（默认加载/自动初始化 kourichat.toml）
    python main.py --config ... # 指定配置文件启动
    python main.py init         # 手动生成配置模板
    python main.py run          # 显式运行 run 子命令
"""

from __future__ import annotations

from kourichat.main import main

if __name__ == "__main__":
    raise SystemExit(main())
