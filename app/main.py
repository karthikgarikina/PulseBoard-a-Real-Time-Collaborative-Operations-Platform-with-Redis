from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.config import settings
from app.redis_client import close_redis, get_redis, redis_client
from app.redis_keys import (
    attendance_key,
    channel_messages_topic,
    channel_typing_topic,
    dau_key,
    feed_key,
    lock_key,
    session_key,
    user_profile_key,
    user_workspaces_key,
    workspace_members_key,
)
from app.schemas import (
    AttendanceRequest,
    EventRequest,
    FeedEventRequest,
    JobRequest,
    LocationRequest,
    LockAcquireRequest,
    LockReleaseRequest,
    LoginRequest,
    LoginResponse,
    MessageRequest,
    ProfileRequest,
    ReputationRequest,
    ScheduledJobRequest,
    TypingRequest,
    WorkspaceInvitationRequest,
)
from app.services import (
    create_session,
    current_user_id,
    due_timestamp,
    get_user_for_session,
    json_dump,
    json_load,
    new_token,
    parse_day,
    record_daily_activity,
    rate_limit_snapshot,
    utc_now,
)


RedisDep = Annotated[Redis, Depends(get_redis)]


async def require_user(
    user_id: Annotated[str, Depends(current_user_id)],
) -> str:
    return user_id


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_redis()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health(redis: RedisDep) -> dict[str, Any]:
    pong = await redis.ping()
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "redis": "ok" if pong else "unavailable",
    }


@app.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, redis: RedisDep) -> LoginResponse:
    user_id = payload.user_id or payload.email
    profile_key = user_profile_key(user_id)
    profile: dict[str, str] = {
        "email": payload.email,
        "role": payload.role,
        "updated_at": utc_now().isoformat(),
    }
    if payload.name:
        profile["name"] = payload.name
    await redis.hset(profile_key, mapping=profile)

    token = await create_session(redis, user_id)
    await record_daily_activity(redis, user_id)
    return LoginResponse(
        session_token=token,
        user_id=user_id,
        ttl_seconds=settings.session_ttl_seconds,
    )


@app.get("/auth/session/{token}")
async def inspect_session(token: str, redis: RedisDep) -> dict[str, Any]:
    key = session_key(token)
    user_id = await get_user_for_session(redis, token)
    ttl = await redis.ttl(key)
    return {"token": token, "user_id": user_id, "ttl_seconds": ttl}


@app.delete("/auth/session/{token}")
async def delete_session(token: str, redis: RedisDep) -> dict[str, Any]:
    deleted = await redis.delete(session_key(token))
    return {"deleted": bool(deleted)}


@app.get("/rate-limit/status")
async def rate_limit_status(
    redis: RedisDep,
    user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    status_payload = await rate_limit_snapshot(redis, user_id)
    return {"user_id": user_id, **status_payload}


@app.put("/users/{user_id}/profile")
async def upsert_profile(
    user_id: str,
    payload: ProfileRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one profile field is required.")
    updates["updated_at"] = utc_now().isoformat()
    await redis.hset(user_profile_key(user_id), mapping=updates)
    return {"user_id": user_id, "profile": await redis.hgetall(user_profile_key(user_id))}


@app.get("/users/{user_id}/profile")
async def get_profile(
    user_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    profile = await redis.hgetall(user_profile_key(user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found.")
    return {"user_id": user_id, "profile": profile}


@app.get("/users/{user_id}/profile/{field}")
async def get_profile_field(
    user_id: str,
    field: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    value = await redis.hget(user_profile_key(user_id), field)
    if value is None:
        raise HTTPException(status_code=404, detail="Profile field not found.")
    return {"user_id": user_id, "field": field, "value": value}


@app.get("/users/{user_id}/profile-fields")
async def get_profile_fields(
    user_id: str,
    fields: Annotated[list[str], Query(min_length=1)],
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    values = await redis.hmget(user_profile_key(user_id), fields)
    return {"user_id": user_id, "fields": dict(zip(fields, values, strict=True))}


@app.get("/users/{user_id}/exists")
async def profile_exists(
    user_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    return {"user_id": user_id, "exists": bool(await redis.exists(user_profile_key(user_id)))}


@app.post("/users/{user_id}/feed")
async def add_feed_event(
    user_id: str,
    payload: FeedEventRequest,
    redis: RedisDep,
    actor_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    event = {
        "type": payload.type,
        "actor_id": payload.actor_id or actor_id,
        "workspace_id": payload.workspace_id,
        "data": payload.data,
        "created_at": utc_now().isoformat(),
    }
    key = feed_key(user_id)
    await redis.lpush(key, json_dump(event))
    await redis.ltrim(key, 0, settings.feed_max_items - 1)
    return {"user_id": user_id, "event": event}


@app.get("/users/{user_id}/feed")
async def get_feed(
    user_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
    limit: int = Query(100, ge=1, le=100),
) -> dict[str, Any]:
    entries = await redis.lrange(feed_key(user_id), 0, limit - 1)
    return {"user_id": user_id, "feed": [json_load(entry) for entry in entries]}


@app.post("/presence/online")
async def mark_online(
    redis: RedisDep,
    user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    await redis.sadd("online_users", user_id)
    return {"user_id": user_id, "online": True}


@app.post("/presence/offline")
async def mark_offline(
    redis: RedisDep,
    user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    await redis.srem("online_users", user_id)
    return {"user_id": user_id, "online": False}


@app.get("/presence/online")
async def online_users(
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    return {"users": sorted(await redis.smembers("online_users"))}


@app.get("/presence/{user_id}")
async def is_online(
    user_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    return {"user_id": user_id, "online": bool(await redis.sismember("online_users", user_id))}


@app.post("/workspaces/{workspace_id}/members/{user_id}")
async def add_workspace_member(
    workspace_id: str,
    user_id: str,
    redis: RedisDep,
    actor_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    await redis.sadd(workspace_members_key(workspace_id), user_id)
    await redis.sadd(user_workspaces_key(user_id), workspace_id)
    event = {
        "type": "workspace.member_added",
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "created_at": utc_now().isoformat(),
    }
    await redis.lpush(feed_key(user_id), json_dump(event))
    await redis.ltrim(feed_key(user_id), 0, settings.feed_max_items - 1)
    return {"workspace_id": workspace_id, "user_id": user_id, "member": True}


@app.delete("/workspaces/{workspace_id}/members/{user_id}")
async def remove_workspace_member(
    workspace_id: str,
    user_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    await redis.srem(workspace_members_key(workspace_id), user_id)
    await redis.srem(user_workspaces_key(user_id), workspace_id)
    return {"workspace_id": workspace_id, "user_id": user_id, "member": False}


@app.get("/workspaces/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> list[str]:
    return sorted(await redis.smembers(workspace_members_key(workspace_id)))


@app.get("/workspaces/common")
async def common_workspaces(
    user_a: str,
    user_b: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    workspaces = await redis.sinter(user_workspaces_key(user_a), user_workspaces_key(user_b))
    return {"user_a": user_a, "user_b": user_b, "workspaces": sorted(workspaces)}


@app.post("/workspaces/{workspace_id}/invitations/{user_id}/accept")
async def accept_workspace_invitation(
    workspace_id: str,
    user_id: str,
    payload: WorkspaceInvitationRequest,
    redis: RedisDep,
    actor_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    event = {
        "type": "workspace.invitation_accepted",
        "workspace_id": workspace_id,
        "actor_id": payload.actor_id or actor_id,
        "note": payload.note,
        "created_at": utc_now().isoformat(),
    }
    pipe = redis.pipeline(transaction=True)
    pipe.sadd(workspace_members_key(workspace_id), user_id)
    pipe.sadd(user_workspaces_key(user_id), workspace_id)
    pipe.lpush(feed_key(user_id), json_dump(event))
    pipe.ltrim(feed_key(user_id), 0, settings.feed_max_items - 1)
    await pipe.execute()
    return {"workspace_id": workspace_id, "user_id": user_id, "accepted": True}


@app.post("/channels/{channel_id}/messages")
async def publish_message(
    channel_id: str,
    payload: MessageRequest,
    redis: RedisDep,
    session_user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    sender_id = payload.user_id or session_user_id
    message = {
        "channel_id": channel_id,
        "user_id": sender_id,
        "content": payload.content,
        "metadata": payload.metadata,
        "created_at": utc_now().isoformat(),
    }
    topic = channel_messages_topic(channel_id)
    await redis.publish(topic, json_dump(message))
    await redis.zincrby("trending:channels", 1, channel_id)
    await redis.xadd(settings.stream_events_key, {"type": "channel.message_created", "payload": json_dump(message)})
    return {"topic": topic, "message": message}


@app.post("/channels/{channel_id}/typing")
async def publish_typing(
    channel_id: str,
    payload: TypingRequest,
    redis: RedisDep,
    session_user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    event = {
        "channel_id": channel_id,
        "user_id": payload.user_id or session_user_id,
        "is_typing": payload.is_typing,
        "created_at": utc_now().isoformat(),
    }
    topic = channel_typing_topic(channel_id)
    await redis.publish(topic, json_dump(event))
    return {"topic": topic, "event": event}


@app.websocket("/ws/channels/{channel_id}")
async def channel_websocket(websocket: WebSocket, channel_id: str) -> None:
    await websocket.accept()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_messages_topic(channel_id), channel_typing_topic(channel_id))
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            await websocket.send_json(
                {
                    "channel": message.get("channel"),
                    "payload": json_load(message.get("data", "{}")),
                }
            )
    except WebSocketDisconnect:
        return
    finally:
        await pubsub.unsubscribe(channel_messages_topic(channel_id), channel_typing_topic(channel_id))
        await pubsub.aclose()


@app.post("/events")
async def add_event(
    payload: EventRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    event_id = await redis.xadd(
        settings.stream_events_key,
        {"type": payload.type, "payload": json_dump(payload.payload), "created_at": utc_now().isoformat()},
    )
    return {"stream": settings.stream_events_key, "event_id": event_id}


@app.post("/jobs")
async def enqueue_job(
    payload: JobRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    job = {"type": payload.type, "payload": payload.payload, "created_at": utc_now().isoformat()}
    await redis.lpush(settings.queue_jobs_key, json_dump(job))
    return {"queue": settings.queue_jobs_key, "job": job}


@app.post("/jobs/scheduled")
async def schedule_job(
    payload: ScheduledJobRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    run_at = due_timestamp(payload.run_at, payload.delay_seconds)
    job = {
        "type": payload.type,
        "payload": payload.payload,
        "scheduled_for": run_at,
        "created_at": utc_now().isoformat(),
    }
    await redis.zadd(settings.scheduled_jobs_key, {json_dump(job): run_at})
    return {"schedule": settings.scheduled_jobs_key, "job": job}


@app.get("/analytics/trending")
async def trending_channels(
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
    limit: int = Query(10, ge=1, le=100),
) -> list[dict[str, Any]]:
    rows = await redis.zrevrange("trending:channels", 0, limit - 1, withscores=True)
    return [{"channel_id": channel_id, "score": score} for channel_id, score in rows]


@app.post("/analytics/reputation/{user_id}")
async def increment_reputation(
    user_id: str,
    payload: ReputationRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    score = await redis.zincrby("reputation:users", payload.delta, user_id)
    return {"user_id": user_id, "score": score}


@app.get("/analytics/reputation")
async def top_reputation(
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
    limit: int = Query(10, ge=1, le=100),
) -> list[dict[str, Any]]:
    rows = await redis.zrevrange("reputation:users", 0, limit - 1, withscores=True)
    return [{"user_id": user_id, "score": score} for user_id, score in rows]


@app.post("/locks/{name}/acquire")
async def acquire_lock(
    name: str,
    payload: LockAcquireRequest,
    redis: RedisDep,
    session_user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    owner = payload.owner or f"{session_user_id}:{new_token()}"
    ttl = payload.ttl_seconds or settings.lock_ttl_seconds
    acquired = await redis.set(lock_key(name), owner, nx=True, ex=ttl)
    return {"lock": lock_key(name), "owner": owner, "acquired": bool(acquired), "ttl_seconds": ttl}


@app.post("/locks/{name}/release")
async def release_lock(
    name: str,
    payload: LockReleaseRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    key = lock_key(name)
    current_owner = await redis.get(key)
    if current_owner != payload.owner:
        return {"lock": key, "released": False, "reason": "owner_mismatch_or_expired"}
    await redis.delete(key)
    return {"lock": key, "released": True}


@app.post("/analytics/dau")
async def track_dau(
    payload: AttendanceRequest,
    redis: RedisDep,
    user_id: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    day = parse_day(payload.date)
    await record_daily_activity(redis, user_id, day)
    return {"key": dau_key(day.isoformat()), "user_id": user_id}


@app.get("/analytics/dau/{day}")
async def dau_count(
    day: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    key = dau_key(parse_day(day).isoformat())
    count = await redis.pfcount(key)
    return {"key": key, "count": count}


@app.post("/attendance/{user_id}/active")
async def mark_attendance(
    user_id: str,
    payload: AttendanceRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    day = parse_day(payload.date)
    key = attendance_key(user_id, day.strftime("%Y-%m"))
    await redis.setbit(key, day.day, 1)
    return {"key": key, "user_id": user_id, "day_offset": day.day, "active": True}


@app.get("/attendance/{user_id}/{day}")
async def attendance_for_day(
    user_id: str,
    day: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    parsed_day = parse_day(day)
    key = attendance_key(user_id, parsed_day.strftime("%Y-%m"))
    active = await redis.getbit(key, parsed_day.day)
    return {"key": key, "user_id": user_id, "day_offset": parsed_day.day, "active": bool(active)}


@app.get("/attendance/{user_id}/{month}/count")
async def attendance_count(
    user_id: str,
    month: str,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    key = attendance_key(user_id, month)
    count = await redis.bitcount(key)
    return {"key": key, "active_days": count}


@app.put("/geo/users/{user_id}")
async def update_location(
    user_id: str,
    payload: LocationRequest,
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    await redis.geoadd("geo:active_users", [payload.longitude, payload.latitude, user_id])
    return {
        "key": "geo:active_users",
        "user_id": user_id,
        "longitude": payload.longitude,
        "latitude": payload.latitude,
    }


@app.get("/geo/nearby")
async def nearby_users(
    longitude: float,
    latitude: float,
    radius_km: Annotated[float, Query(gt=0)],
    redis: RedisDep,
    _: Annotated[str, Depends(require_user)],
) -> dict[str, Any]:
    users = await redis.geosearch(
        "geo:active_users",
        longitude=longitude,
        latitude=latitude,
        radius=radius_km,
        unit="km",
        sort="ASC",
    )
    return {"key": "geo:active_users", "users": users}
