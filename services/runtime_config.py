"""运行时配置（全局，MongoDB持久化 + TTL缓存）"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Literal, Optional, TypedDict, cast

from utils.logger import logger


RuntimeMode = Literal["low", "high", "custom"]


class RuntimeModules(TypedDict, total=False):
    kg_extract_enabled: bool
    kg_retrieve_enabled: bool
    query_analyze_enabled: bool
    query_rewrite_enabled: bool
    citation_check_enabled: bool
    legacy_deep_research_html_enabled: bool
    rerank_enabled: bool
    ocr_image_enabled: bool
    table_parse_enabled: bool
    embedding_enabled: bool


class RuntimeParams(TypedDict, total=False):
    retrieval_fusion_strategy: str
    context_budget: int
    kg_concurrency: int
    kg_chunk_timeout_s: int
    kg_max_chunks: int
    embedding_batch_size: int
    embedding_concurrency: int
    ocr_concurrency: int
    http_log_level: str
    http_log_request_level: str
    http_log_success_level: str
    http_log_slow_level: str
    http_log_client_error_level: str
    http_log_server_error_level: str
    http_log_slow_threshold_s: float
    http_log_success_enabled: bool
    http_log_include_query: bool
    http_log_include_client_ip: bool
    http_log_include_request_body: bool
    http_log_request_body_max_chars: int


class RuntimeConfig(TypedDict, total=False):
    mode: RuntimeMode
    modules: RuntimeModules
    params: RuntimeParams
    updated_at: str


_DEFAULT_LOW: RuntimeConfig = {
    "mode": "low",
    "modules": {
        "kg_extract_enabled": False,
        "kg_retrieve_enabled": False,
        "query_analyze_enabled": False,
        "query_rewrite_enabled": False,
        "citation_check_enabled": True,
        "legacy_deep_research_html_enabled": True,
        "rerank_enabled": False,
        "ocr_image_enabled": False,
        "table_parse_enabled": False,
        # 基础能力必须保留：embedding 永远开启（但可调参）
        "embedding_enabled": True,
    },
    "params": {
        "retrieval_fusion_strategy": "rrf",
        "context_budget": 30_000,
        "kg_concurrency": 1,
        "kg_chunk_timeout_s": 60,
        "kg_max_chunks": 0,
        "embedding_batch_size": 16,
        "embedding_concurrency": 1,
        "ocr_concurrency": 1,
        "http_log_level": "INFO",
        "http_log_request_level": "INFO",
        "http_log_success_level": "INFO",
        "http_log_slow_level": "WARNING",
        "http_log_client_error_level": "WARNING",
        "http_log_server_error_level": "ERROR",
        "http_log_slow_threshold_s": 1.0,
        "http_log_success_enabled": False,
        "http_log_include_query": True,
        "http_log_include_client_ip": True,
        "http_log_include_request_body": False,
        "http_log_request_body_max_chars": 1000,
    },
}

_DEFAULT_HIGH: RuntimeConfig = {
    "mode": "high",
    "modules": {
        "kg_extract_enabled": True,
        "kg_retrieve_enabled": True,
        "query_analyze_enabled": True,
        "query_rewrite_enabled": True,
        "citation_check_enabled": True,
        "legacy_deep_research_html_enabled": True,
        "rerank_enabled": True,
        "ocr_image_enabled": True,
        "table_parse_enabled": True,
        "embedding_enabled": True,
    },
    "params": {
        "retrieval_fusion_strategy": "rrf",
        "context_budget": 30_000,
        "kg_concurrency": 3,
        "kg_chunk_timeout_s": 150,
        # 默认不强行截断（0 表示不限制，交给 UI/用户）
        "kg_max_chunks": 0,
        "embedding_batch_size": 50,
        "embedding_concurrency": 2,
        "ocr_concurrency": 1,
        "http_log_level": "INFO",
        "http_log_request_level": "INFO",
        "http_log_success_level": "INFO",
        "http_log_slow_level": "WARNING",
        "http_log_client_error_level": "WARNING",
        "http_log_server_error_level": "ERROR",
        "http_log_slow_threshold_s": 1.0,
        "http_log_success_enabled": False,
        "http_log_include_query": True,
        "http_log_include_client_ip": True,
        "http_log_include_request_body": False,
        "http_log_request_body_max_chars": 1000,
    },
}


def apply_preset(mode: RuntimeMode) -> RuntimeConfig:
    if mode == "low":
        return cast(RuntimeConfig, {**_DEFAULT_LOW})
    if mode == "high":
        return cast(RuntimeConfig, {**_DEFAULT_HIGH})
    return {"mode": "custom", "modules": {"embedding_enabled": True}, "params": {}}


def _merge(base: RuntimeConfig, override: Optional[RuntimeConfig]) -> RuntimeConfig:
    if not override:
        return base
    merged: RuntimeConfig = {**base}
    if "mode" in override and override["mode"] in ("low", "high", "custom"):
        merged["mode"] = override["mode"]
    b_mod = dict(base.get("modules") or {})
    o_mod = dict(override.get("modules") or {})
    b_par = dict(base.get("params") or {})
    o_par = dict(override.get("params") or {})
    b_mod.update(o_mod)
    b_par.update(o_par)
    merged["modules"] = cast(RuntimeModules, b_mod)
    merged["params"] = cast(RuntimeParams, b_par)
    if "updated_at" in override:
        merged["updated_at"] = override["updated_at"]
    return merged


def _normalize(cfg: RuntimeConfig) -> RuntimeConfig:
    mode = cast(RuntimeMode, cfg.get("mode") or "custom")
    if mode not in ("low", "high", "custom"):
        mode = "custom"

    base = apply_preset(mode) if mode in ("low", "high") else apply_preset("custom")
    merged = _merge(base, cfg)

    # 强制基础能力：embedding 不能关
    modules = dict(merged.get("modules") or {})
    modules["embedding_enabled"] = True
    merged["modules"] = cast(RuntimeModules, modules)

    return merged


_CACHE_LOCK = threading.Lock()
_CACHE: Optional[RuntimeConfig] = None
_CACHE_TS: float = 0.0
_CACHE_TTL_S: float = 10.0


def set_cache_ttl(seconds: int) -> None:
    global _CACHE_TTL_S
    _CACHE_TTL_S = float(max(1, int(seconds)))


async def get_runtime_config(force_refresh: bool = False) -> RuntimeConfig:
    """异步读取（Motor）- 用于 API / 检索路径。"""
    global _CACHE, _CACHE_TS
    now = time.time()
    with _CACHE_LOCK:
        if not force_refresh and _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL_S:
            return cast(RuntimeConfig, dict(_CACHE))

    try:
        from database.mongodb import mongodb
        collection = mongodb.get_collection("app_settings")
        doc = await collection.find_one({"_id": "runtime_config"})
        stored = cast(Optional[RuntimeConfig], doc.get("value") if doc else None)
        cfg = _normalize(stored or {})
    except Exception as e:
        logger.warning(f"读取运行时配置失败，使用默认 high: {e}")
        cfg = _normalize(apply_preset("high"))

    with _CACHE_LOCK:
        _CACHE = cfg
        _CACHE_TS = now
    return cast(RuntimeConfig, dict(cfg))


def get_runtime_config_sync(force_refresh: bool = False) -> RuntimeConfig:
    """同步读取（PyMongo）- 用于后台入库线程等同步路径。"""
    global _CACHE, _CACHE_TS
    now = time.time()
    with _CACHE_LOCK:
        if not force_refresh and _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL_S:
            return cast(RuntimeConfig, dict(_CACHE))

    try:
        from database.mongodb import mongodb_client

        if mongodb_client.db is None:
            mongodb_client.connect()
        col = mongodb_client.get_collection("app_settings")
        doc = col.find_one({"_id": "runtime_config"})
        stored = cast(Optional[RuntimeConfig], (doc or {}).get("value"))
        cfg = _normalize(stored or {})
    except Exception as e:
        logger.warning(f"读取运行时配置失败（sync），使用默认 high: {e}")
        cfg = _normalize(apply_preset("high"))

    with _CACHE_LOCK:
        _CACHE = cfg
        _CACHE_TS = now
    return cast(RuntimeConfig, dict(cfg))


async def upsert_runtime_config(patch: RuntimeConfig) -> RuntimeConfig:
    """合并更新并写入 MongoDB（Motor）。"""
    from utils.timezone import beijing_now
    from database.mongodb import mongodb

    current = await get_runtime_config(force_refresh=True)
    next_mode = cast(RuntimeMode, patch.get("mode") or current.get("mode") or "custom")
    base = apply_preset(next_mode) if next_mode in ("low", "high") else apply_preset("custom")
    merged = _merge(base, patch)
    merged = _normalize(merged)
    merged["updated_at"] = beijing_now().isoformat()

    collection = mongodb.get_collection("app_settings")
    await collection.update_one(
        {"_id": "runtime_config"},
        {"$set": {"value": merged, "updated_at": beijing_now()}},
        upsert=True,
    )

    # 刷新缓存
    with _CACHE_LOCK:
        global _CACHE, _CACHE_TS
        _CACHE = merged
        _CACHE_TS = time.time()

    return merged
