import asyncio
from contextlib import suppress

from app.config import settings
from app.redis_client import close_redis, redis_client
from app.services import json_load, parse_channels


async def main() -> None:
    channels = parse_channels(settings.subscriber_channels)
    if not channels:
        raise RuntimeError("SUBSCRIBER_CHANNELS must include at least one Redis channel.")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels)
    print(f"subscriber listening on: {', '.join(channels)}", flush=True)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            print(
                {
                    "channel": message.get("channel"),
                    "payload": json_load(message.get("data", "{}")),
                },
                flush=True,
            )
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        with suppress(RuntimeError):
            asyncio.run(close_redis())
