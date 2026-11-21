"""应用配置：只从环境变量 / .env 读取，禁止硬编码密钥。

P0-P3 进化升级：新增 SQLite WAL 锁超时、滑动窗口切块、FTS5/向量混合检索与
视频队列超时熔断/有限重试配置项，全部带向后兼容默认值。
"""
from pathlib import Path

from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parents[2]  # 项目根目录


class Settings(BaseSettings):
    # LLM (OpenAI 兼容协议)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # 服务
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # LLM 调用参数
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 2048

    # 入库切块（P1：长段落 Token/字符上限滑动切分 + 重叠窗口）
    chunk_max_chars: int = 500
    chunk_overlap_chars: int = 80

    # 检索（P1：SQLite FTS5 BM25 + 可选本地向量 + RRF 融合）
    retrieval_top_k: int = 5
    retrieval_bm25_weight: float = 0.6
    retrieval_tfidf_weight: float = 0.4
    retrieval_rrf_k: int = 60
    retrieval_use_vector: bool = False
    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    embedding_api_base: str = ""
    embedding_api_key: str = ""

    # 视频队列（全局单并发 + P0 超时熔断与有限重试）
    video_queue_max_concurrent: int = 1
    video_queue_max_queue: int = 50
    video_task_timeout_seconds: int = 180
    video_task_max_retries: int = 1

    # TTS（视频配音）：edge-tts (免费、免 Key) 或 openai
    tts_provider: str = "edge-tts"
    openai_tts_api_key: str = ""
    openai_tts_voice: str = "alloy"
    edge_tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # 存储（P0 WAL 并发锁等待超时）
    storage_uploads_dir: str = "storage/uploads"
    storage_videos_dir: str = "storage/videos"
    database_url: str = "sqlite:///storage/app.db"
    db_busy_timeout_ms: int = 5000

    # 前端
    frontend_port: int = 5173

    class Config:
        env_file = str(_ROOT / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
