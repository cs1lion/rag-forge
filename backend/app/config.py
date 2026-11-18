"""应用配置：只从环境变量 / .env 读取，禁止硬编码密钥。

字段与 .env.example 一一对应；LLM 走 OpenAI 兼容协议（LLM_BASE_URL）。
.env 位于项目根目录（本文件的上两级），用绝对路径定位，避免受 cwd 影响。
"""
from pathlib import Path

from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parents[2]  # 项目根目录


class Settings(BaseSettings):
    # LLM（OpenAI 兼容协议）
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # 服务
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # LLM 调用参数
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 2048

    # 检索（本地混合：BM25 + TF-IDF，零外部 Embedding）
    retrieval_top_k: int = 5
    retrieval_bm25_weight: float = 0.6
    retrieval_tfidf_weight: float = 0.4

    # 视频队列（全局单并发）
    video_queue_max_concurrent: int = 1
    video_queue_max_queue: int = 50

    # TTS（视频配音）：edge-tts（免费、免 Key）或 openai
    tts_provider: str = "edge-tts"
    openai_tts_api_key: str = ""
    openai_tts_voice: str = "alloy"
    edge_tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # 存储
    storage_uploads_dir: str = "storage/uploads"
    storage_videos_dir: str = "storage/videos"
    database_url: str = "sqlite:///storage/app.db"

    # 前端
    frontend_port: int = 5173

    class Config:
        env_file = str(_ROOT / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
