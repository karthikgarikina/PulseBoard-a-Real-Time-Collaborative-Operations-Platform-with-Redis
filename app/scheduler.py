import asyncio
import time
from contextlib import suppress

from redis.asyncio import Redis

from app.config import settings
from app.redis_client import close_redis, redis_client


async def move_due_jobs(redis: Redis) -> int:
    now = time.time()
    jobs = await redis.zrangebyscore(settings.scheduled_jobs_key, min="-inf", max=now, start=0, num=50)
    moved = 0
    for job in jobs:
        removed = await redis.zrem(settings.scheduled_jobs_key, job)
        if removed:
            await redis.lpush(settings.queue_jobs_key, job)
            moved += 1
            print(f"scheduled job moved to {settings.queue_jobs_key}: {job}", flush=True)
    return moved


async def main() -> None:
    redis = redis_client
    print(f"scheduler polling {settings.scheduled_jobs_key}", flush=True)
    while True:
        await move_due_jobs(redis)
        await asyncio.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        with suppress(RuntimeError):
            asyncio.run(close_redis())
