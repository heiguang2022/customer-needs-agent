"""本地产品目录加载。"""

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from customer_needs_agent.models import Product


@lru_cache(maxsize=1)
def load_catalog(path: Path | None = None) -> tuple[Product, ...]:
    """加载并验证产品目录；任何坏数据都会在启动或首次查询时尽早暴露。"""

    if path is None:
        resource = files("customer_needs_agent").joinpath("data/products.json")
        raw = json.loads(resource.read_text(encoding="utf-8"))
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Product.model_validate(item) for item in raw)
