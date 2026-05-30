import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)


def _redis_url() -> str:
    explicit_url = os.getenv("REDIS_URL")
    if explicit_url:
        return explicit_url

    host = os.getenv("REDIS_HOST", "redis")
    port = _env_int("REDIS_PORT", 6379)
    db = _env_int("REDIS_DB", 0)
    password = os.getenv("REDIS_PASSWORD", "")
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "PulseBoard")
    app_env: str = os.getenv("APP_ENV", "development")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = _env_int("API_PORT", 8000)

    redis_url: str = _redis_url()

    session_ttl_seconds: int = _env_int("SESSION_TTL_SECONDS", 3600)
    rate_limit_requests: int = _env_int("RATE_LIMIT_REQUESTS", 60)
    rate_limit_window_seconds: int = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    feed_max_items: int = _env_int("FEED_MAX_ITEMS", 100)

    stream_events_key: str = os.getenv("STREAM_EVENTS_KEY", "stream:events")
    stream_events_group: str = os.getenv("STREAM_EVENTS_GROUP", "pulseboard-workers")
    queue_jobs_key: str = os.getenv("QUEUE_JOBS_KEY", "queue:jobs")
    scheduled_jobs_key: str = os.getenv("SCHEDULED_JOBS_KEY", "schedule:jobs")

    worker_consumer_name: str = os.getenv("WORKER_CONSUMER_NAME", "worker-1")
    scheduler_poll_seconds: int = _env_int("SCHEDULER_POLL_SECONDS", 5)
    lock_ttl_seconds: int = _env_int("LOCK_TTL_SECONDS", 60)
    subscriber_channels: str = os.getenv(
        "SUBSCRIBER_CHANNELS",
        "channel:demo:messages,channel:demo:typing",
    )


settings = Settings()
