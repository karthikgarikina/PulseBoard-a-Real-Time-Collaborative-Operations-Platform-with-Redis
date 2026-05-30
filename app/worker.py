import asyncio
from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.config import settings
from app.redis_client import close_redis, redis_client
from app.services import json_load


async def ensure_consumer_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            settings.stream_events_key,
            settings.stream_events_group,
            id="0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def consume_stream(redis: Redis) -> None:
    await ensure_consumer_group(redis)
    print(
        f"worker listening to stream {settings.stream_events_key} "
        f"group={settings.stream_events_group} consumer={settings.worker_consumer_name}",
        flush=True,
    )
    while True:
        rows = await redis.xreadgroup(
            settings.stream_events_group,
            settings.worker_consumer_name,
            streams={settings.stream_events_key: ">"},
            count=10,
            block=5000,
        )
        for _, messages in rows:
            for message_id, fields in messages:
                print(f"stream event {message_id}: {fields}", flush=True)
                await redis.xack(settings.stream_events_key, settings.stream_events_group, message_id)


async def consume_jobs(redis: Redis) -> None:
    print(f"worker listening to list queue {settings.queue_jobs_key}", flush=True)
    while True:
        result = await redis.brpop(settings.queue_jobs_key, timeout=5)
        if not result:
            continue
        _, raw_job = result
        print(f"job processed: {json_load(raw_job)}", flush=True)


async def main() -> None:
    redis = redis_client
    await asyncio.gather(consume_stream(redis), consume_jobs(redis))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        with suppress(RuntimeError):
            asyncio.run(close_redis())
