def session_key(token: str) -> str:
    return f"session:{token}"


def rate_limit_key(user_id: str, window_start: int) -> str:
    return f"rate_limit:{user_id}:{window_start}"


def feed_key(user_id: str) -> str:
    return f"feed:{user_id}"


def workspace_members_key(workspace_id: str) -> str:
    return f"workspace:{workspace_id}:members"


def user_workspaces_key(user_id: str) -> str:
    return f"user:{user_id}:workspaces"


def user_profile_key(user_id: str) -> str:
    return f"user:{user_id}"


def channel_messages_topic(channel_id: str) -> str:
    return f"channel:{channel_id}:messages"


def channel_typing_topic(channel_id: str) -> str:
    return f"channel:{channel_id}:typing"


def lock_key(name: str) -> str:
    return f"lock:{name}"


def dau_key(day: str) -> str:
    return f"analytics:dau:{day}"


def attendance_key(user_id: str, month: str) -> str:
    return f"attendance:{user_id}:{month}"
