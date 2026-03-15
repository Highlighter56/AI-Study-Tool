from database import get_setting


def _clamp_int(value, default, min_value, max_value):
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def get_configured_timeout_minutes(default=10, min_value=5, max_value=30):
    raw = get_setting("timeout_minutes", str(default))
    return _clamp_int(raw, default, min_value, max_value)


def get_configured_timeout_seconds(default=10, min_value=5, max_value=30):
    return get_configured_timeout_minutes(default, min_value, max_value) * 60
