"""
Clean up embeds and components from a ticket before they are rendered.

Both come straight from Discord (see discord-api-docs, resources/message "Embed Object" and
components/reference), but the payload is user supplied, so every value is checked and
anything unknown or malformed is dropped instead of breaking the page.
"""

import re

from datetime import datetime, UTC

re_video = re.compile(r"\.(mp4|webm|mov)(?:$|\?)", re.IGNORECASE)

# https://discord.com/developers/docs/components/reference#component-object-component-types
ACTION_ROW = 1
BUTTON = 2
STRING_SELECT = 3
USER_SELECT = 5
ROLE_SELECT = 6
MENTIONABLE_SELECT = 7
CHANNEL_SELECT = 8
SECTION = 9
TEXT_DISPLAY = 10
THUMBNAIL = 11
MEDIA_GALLERY = 12
FILE = 13
SEPARATOR = 14
CONTAINER = 17

SELECTS = (STRING_SELECT, USER_SELECT, ROLE_SELECT, MENTIONABLE_SELECT, CHANNEL_SELECT)
SELECT_PLACEHOLDERS = {
    USER_SELECT: "Select a user",
    ROLE_SELECT: "Select a role",
    MENTIONABLE_SELECT: "Select a user or role",
    CHANNEL_SELECT: "Select a channel",
}

# Which components may appear where, straight from the docs
ROOT_CHILDREN = (ACTION_ROW, SECTION, TEXT_DISPLAY, MEDIA_GALLERY, FILE, SEPARATOR, CONTAINER)
CONTAINER_CHILDREN = (ACTION_ROW, SECTION, TEXT_DISPLAY, MEDIA_GALLERY, FILE, SEPARATOR)

# https://discord.com/developers/docs/components/reference#button-button-styles
BUTTON_STYLES = {1: "primary", 2: "secondary", 3: "success", 4: "danger", 5: "link", 6: "premium"}


def _text(value, limit: int | None = None) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:limit] if limit else value


def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_url(value) -> str | None:
    """ Only http(s) links are allowed, no javascript: and friends """
    value = _text(value)
    if value and value.lower().startswith(("https://", "http://")):
        return value
    return None


def colour_hex(value) -> str | None:
    """ Discord's integer colours as #rrggbb """
    value = _int(value)
    if value is None or not 0 <= value <= 0xFFFFFF:
        return None
    return f"#{value:06x}"


def file_size(value) -> str | None:
    """ Bytes as a readable size, like Discord shows under files """
    size = _int(value)
    if not size or size < 0:
        return None
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size} {unit}" if unit == "bytes" else f"{size:.2f} {unit}"
        size /= 1024
    return None


def format_timestamp(value) -> str | None:
    """ ISO8601 from Discord, shown the same way as the message timestamps """
    value = _text(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M (UTC)")


def _media(value) -> dict | None:
    """ Embed image/thumbnail/video or an unfurled media item """
    if not isinstance(value, dict):
        return None
    url = safe_url(value.get("url")) or safe_url(value.get("proxy_url"))
    if not url:
        return None
    content_type = _text(value.get("content_type")) or ""
    return {
        "url": url,
        "description": _text(value.get("description"), 1024),
        "is_video": content_type.startswith("video/") or bool(re_video.search(url)),
    }


def _emoji(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    name = _text(value.get("name"))
    emoji_id = _int(value.get("id"))
    if emoji_id:
        ext = "gif" if value.get("animated") else "png"
        return {"name": name or "emoji", "url": f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"}
    if name:
        return {"name": name, "url": None}
    return None


# ── Embeds ──────────────────────────────────────────────────────────────────

def _field_rows(fields: list[dict], has_thumbnail: bool) -> list[list[dict]]:
    """ Group inline fields into rows like Discord, max 3 per row (2 next to a thumbnail) """
    per_row = 2 if has_thumbnail else 3
    rows: list[list[dict]] = []
    current: list[dict] = []

    for field in fields:
        if not field["inline"]:
            if current:
                rows.append(current)
                current = []
            rows.append([field])
            continue

        current.append(field)
        if len(current) == per_row:
            rows.append(current)
            current = []

    if current:
        rows.append(current)
    return rows


def normalize_embed(raw) -> dict | None:
    """ One embed object, None when it has nothing to show """
    if not isinstance(raw, dict):
        return None

    author = None
    if isinstance(raw.get("author"), dict) and (name := _text(raw["author"].get("name"), 256)):
        author = {
            "name": name,
            "url": safe_url(raw["author"].get("url")),
            "icon_url": safe_url(raw["author"].get("icon_url")) or safe_url(raw["author"].get("proxy_icon_url")),
        }

    footer = None
    if isinstance(raw.get("footer"), dict) and (text := _text(raw["footer"].get("text"), 2048)):
        footer = {
            "text": text,
            "icon_url": safe_url(raw["footer"].get("icon_url")) or safe_url(raw["footer"].get("proxy_icon_url")),
        }

    provider = None
    if isinstance(raw.get("provider"), dict) and (name := _text(raw["provider"].get("name"))):
        provider = {"name": name, "url": safe_url(raw["provider"].get("url"))}

    fields = []
    for field in raw.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name, value = _text(field.get("name"), 256), _text(field.get("value"), 1024)
        if name or value:
            fields.append({"name": name, "value": value, "inline": field.get("inline") is not False})

    embed = {
        "type": _text(raw.get("type")) or "rich",
        "title": _text(raw.get("title"), 256),
        "description": _text(raw.get("description"), 4096),
        "url": safe_url(raw.get("url")),
        "colour": colour_hex(raw.get("color")),
        "timestamp": format_timestamp(raw.get("timestamp")),
        "author": author,
        "footer": footer,
        "provider": provider,
        "image": _media(raw.get("image")),
        "thumbnail": _media(raw.get("thumbnail")),
        "video": _media(raw.get("video")),
    }
    embed["field_rows"] = _field_rows(fields, bool(embed["thumbnail"]))

    has_text = any(embed[k] for k in ("title", "description", "author", "footer", "provider")) or fields
    media = embed["video"] or embed["image"] or embed["thumbnail"]

    # Image and GIF link previews are shown as the media itself, without an embed box.
    # discord.http drops "type" when saving, so an embed with only media counts too.
    embed["media_only"] = media if (embed["type"] in ("image", "gifv") or not has_text) else None

    if not has_text and not media:
        return None
    return embed


def normalize_embeds(raw) -> list[dict]:
    """ Every embed of a message, broken ones are left out """
    if not isinstance(raw, list):
        return []
    return [e for e in (normalize_embed(g) for g in raw[:10]) if e]


# ── Components ──────────────────────────────────────────────────────────────

def _button(raw: dict) -> dict | None:
    style = BUTTON_STYLES.get(_int(raw.get("style")) or 0)
    if not style:
        return None

    button = {
        "type": BUTTON,
        "style": style,
        "label": _text(raw.get("label"), 80),
        "emoji": _emoji(raw.get("emoji")),
        "url": safe_url(raw.get("url")) if style == "link" else None,
        "disabled": raw.get("disabled") is True,
    }

    if style == "premium" and not button["label"]:
        button["label"] = "Premium"
    if not button["label"] and not button["emoji"]:
        return None
    return button


def _select(raw: dict, comp_type: int) -> dict:
    selected = []
    if comp_type == STRING_SELECT:
        for option in raw.get("options") or []:
            if isinstance(option, dict) and option.get("default") is True and (label := _text(option.get("label"), 100)):
                selected.append({"label": label, "emoji": _emoji(option.get("emoji"))})

    return {
        "type": comp_type,
        "placeholder": _text(raw.get("placeholder"), 150) or SELECT_PLACEHOLDERS.get(comp_type, "Make a selection"),
        "selected": selected,
        "disabled": raw.get("disabled") is True,
    }


def _text_display(raw: dict) -> dict | None:
    content = _text(raw.get("content"), 4000)
    return {"type": TEXT_DISPLAY, "content": content} if content else None


def _thumbnail(raw: dict) -> dict | None:
    media = _media(raw.get("media"))
    if not media:
        return None
    return {
        "type": THUMBNAIL,
        "url": media["url"],
        "description": _text(raw.get("description"), 1024),
        "spoiler": raw.get("spoiler") is True,
    }


def _component(raw, allowed: tuple[int, ...]) -> dict | None:
    if not isinstance(raw, dict):
        return None

    comp_type = _int(raw.get("type"))
    if comp_type not in allowed:
        return None

    match comp_type:
        case 1:  # Action row, up to 5 buttons or a single select
            children = raw.get("components") if isinstance(raw.get("components"), list) else []
            items = [c for c in (_component(g, (BUTTON, *SELECTS)) for g in children[:5]) if c]
            return {"type": ACTION_ROW, "components": items} if items else None

        case 2:
            return _button(raw)

        case 3 | 5 | 6 | 7 | 8:
            return _select(raw, comp_type)

        case 9:  # Section, 1-3 text displays with a button or thumbnail next to them
            children = raw.get("components") if isinstance(raw.get("components"), list) else []
            texts = [c for c in (_component(g, (TEXT_DISPLAY,)) for g in children[:3]) if c]
            accessory = _component(raw.get("accessory"), (BUTTON, THUMBNAIL))
            if not texts and not accessory:
                return None
            return {"type": SECTION, "components": texts, "accessory": accessory}

        case 10:
            return _text_display(raw)

        case 11:
            return _thumbnail(raw)

        case 12:  # Media gallery, 1-10 items
            items = []
            for item in (raw.get("items") or [])[:10]:
                if isinstance(item, dict) and (media := _media(item.get("media"))):
                    media["description"] = _text(item.get("description"), 1024)
                    media["spoiler"] = item.get("spoiler") is True
                    items.append(media)
            return {"type": MEDIA_GALLERY, "items": items} if items else None

        case 13:  # File, the url is usually attachment://<filename> so the name is all there is
            file = raw.get("file") if isinstance(raw.get("file"), dict) else {}
            raw_url = _text(file.get("url")) or ""
            name = _text(raw.get("name")) or (raw_url.removeprefix("attachment://") if raw_url.startswith("attachment://") else None)
            url = safe_url(raw_url) or safe_url(file.get("proxy_url"))
            if not name and url:
                name = url.split("?")[0].rstrip("/").split("/")[-1]
            return {
                "type": FILE,
                "name": name or "Unknown file",
                "url": url,
                "size": file_size(raw.get("size")),
                "spoiler": raw.get("spoiler") is True,
            }

        case 14:
            spacing = _int(raw.get("spacing"))
            return {
                "type": SEPARATOR,
                "divider": raw.get("divider") is not False,
                "spacing": 2 if spacing == 2 else 1,
            }

        case 17:  # Container, groups components behind an optional accent colour bar
            children = raw.get("components") if isinstance(raw.get("components"), list) else []
            items = [c for c in (_component(g, CONTAINER_CHILDREN) for g in children[:40]) if c]
            if not items:
                return None
            return {
                "type": CONTAINER,
                "components": items,
                "accent": colour_hex(raw.get("accent_color")),
                "spoiler": raw.get("spoiler") is True,
            }

    return None


def normalize_components(raw) -> list[dict]:
    """ Top level components of a message, legacy (action rows) or Components V2 """
    if not isinstance(raw, list):
        return []
    return [c for c in (_component(g, ROOT_CHILDREN) for g in raw[:40]) if c]
