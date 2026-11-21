"""可选本地/远端稠密向量编码器（P1 混合检索语义通道）。

设计原则：
- 零强制重型依赖：未开启 `settings.retrieval_use_vector` 或未安装向量库时，
  `embed_texts()` 安静返回 None，检索自动运行在纯 FTS5 通道，不报错；
- 开启后优先尝试本地 `fastembed` / `sentence_transformers`（如 BAAI/bge-small-zh-v1.5），
  其次回退到 OpenAI 兼容 `/embeddings` 接口；
- 提供紧凑的 float32 BLOB 编解码与零依赖余弦相似度计算，直接落盘 SQLite `chunks.embedding`。
"""
from __future__ import annotations

import math
import struct
from typing import Sequence

from .config import settings

_local_model = None
_local_model_failed = False


def pack_vector(vec: Sequence[float]) -> bytes:
    """将浮点向量序列化为紧凑 little-endian float32 BLOB。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> list[float]:
    """将 SQLite BLOB 反序列化为浮点列表。"""
    if not blob:
        return []
    dim = len(blob) // 4
    return list(struct.unpack(f"<{dim}f", blob))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)


def _load_local_model():
    global _local_model, _local_model_failed
    if _local_model is not None or _local_model_failed:
        return _local_model
    model_name = getattr(settings, "embedding_model_name", "BAAI/bge-small-zh-v1.5")
    try:
        from fastembed import TextEmbedding  # type: ignore

        _local_model = ("fastembed", TextEmbedding(model_name=model_name))
        return _local_model
    except Exception:
        pass
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _local_model = ("st", SentenceTransformer(model_name))
        return _local_model
    except Exception:
        _local_model_failed = True
        return None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """批量生成归一化向量；未启用向量通道或后端不可用时返回 None。"""
    if not texts or not getattr(settings, "retrieval_use_vector", False):
        return None

    model_entry = _load_local_model()
    if model_entry is not None:
        kind, model = model_entry
        if kind == "fastembed":
            return [list(map(float, v)) for v in model.embed(texts)]
        vecs = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]

    api_base = getattr(settings, "embedding_api_base", "") or getattr(settings, "llm_base_url", "")
    api_key = getattr(settings, "embedding_api_key", "") or getattr(settings, "llm_api_key", "")
    if not api_base or not api_key:
        return None
    try:
        import httpx

        resp = httpx.post(
            f"{api_base.rstrip('/')}/embeddings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": getattr(settings, "embedding_model_name", "BAAI/bge-small-zh-v1.5"),
                "input": texts,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        items = sorted(resp.json()["data"], key=lambda x: x["index"])
        return [list(map(float, it["embedding"])) for it in items]
    except Exception:
        return None
