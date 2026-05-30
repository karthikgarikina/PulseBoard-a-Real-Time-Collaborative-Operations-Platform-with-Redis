import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis

from app.config import settings
from app.redis_client import get_redis
from app.redis_keys import attendance_key, dau_key, rate_limit_key, session_key


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_day() -> str:
    return utc_now().date().isoformat()


def json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def json_load(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    if isinstance(loaded, dict):
        return loaded
    return {"value": loaded}


def parse_day(day: str | None = None) -> date:
    if not day:
        return utc_now().date()
    return date.fromisoformat(day)


def parse_channels(raw: str) -> list[str]:
    return [channel.strip() for channel in raw.split(",") if channel.strip()]


def new_token() -> str:
    return uuid.uuid4().hex


async def create_session(redis: Redis, user_id: str) -> str:
    token = new_token()
    await redis.setex(session_key(token), settings.session_ttl_seconds, user_id)
    return token


async def get_user_for_session(redis: Redis, token: str) -> str | None:
    return await redis.get(session_key(token))


async def enforce_rate_limit(redis: Redis, user_id: str) -> dict[str, int]:
    now = int(time.time())
    window = settings.rate_limit_window_seconds
    window_start = now - (now % window)
    key = rate_limit_key(user_id, window_start)

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)

    ttl = await redis.ttl(key)
    if count > settings.rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "limit": settings.rate_limit_requests,
                "window_seconds": window,
                "retry_after_seconds": max(ttl, 0),
            },
        )

    return {
        "limit": settings.rate_limit_requests,
        "remaining": max(settings.rate_limit_requests - count, 0),
        "reset_seconds": max(ttl, 0),
    }


async def rate_limit_snapshot(redis: Redis, user_id: str) -> dict[str, int]:
    now = int(time.time())
    window = settings.rate_limit_window_seconds
    window_start = now - (now % window)
    key = rate_limit_key(user_id, window_start)
    count = int(await redis.get(key) or 0)
    ttl = await redis.ttl(key)
    return {
        "limit": settings.rate_limit_requests,
        "used": count,
        "remaining": max(settings.rate_limit_requests - count, 0),
        "reset_seconds": max(ttl, 0),
    }


async def record_daily_activity(redis: Redis, user_id: str, day: date | None = None) -> None:
    active_day = day or utc_now().date()
    day_key = active_day.isoformat()
    month_key = active_day.strftime("%Y-%m")
    await redis.pfadd(dau_key(day_key), user_id)
    await redis.setbit(attendance_key(user_id, month_key), active_day.day, 1)


async def current_user_id(
    redis: Redis = Depends(get_redis),
    x_session_token: str | None = Header(None, alias="X-Session-Token"),
) -> str:
    if not x_session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Session-Token header.",
        )

    user_id = await get_user_for_session(redis, x_session_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    await enforce_rate_limit(redis, user_id)
    await record_daily_activity(redis, user_id)
    return user_id


def due_timestamp(run_at: datetime | None, delay_seconds: int | None) -> float:
    if run_at is not None:
        normalized = run_at if run_at.tzinfo else run_at.replace(tzinfo=UTC)
        return normalized.timestamp()
    return (utc_now() + timedelta(seconds=delay_seconds or 0)).timestamp()
