import json
import time
import re
import markdown
import asyncio
import markupsafe

from datetime import datetime, UTC
from quart import Quart, render_template, request, jsonify, redirect
from utils import sqlite, tickets, jinja_filters
from utils.md_extensions import URLifyExtension, DiscordEmojiExtension, SmallLineExtension

# RegEx patterns
re_mentions = re.compile(r"(<(@|#|@&)(\d+)>)")

# Quart itself
app = Quart(__name__)
app.config["JSON_SORT_KEYS"] = False

# Create a loop (Python 3.10)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# General configs
db = sqlite.Database()
db.create_tables()  # Attempt to create table(s) if not exists already.

with open("config.json", "r") as f:
    config = json.load(f)

md = markdown.Markdown(
    extensions=[
        DiscordEmojiExtension(),
        "meta", "extra", "toc", "sane_lists",
        URLifyExtension(),
        SmallLineExtension()
    ]
)

# Jinja2 template filters
app.jinja_env.filters["markdown"] = lambda text: markupsafe.Markup(md.convert(text))
app.jinja_env.filters["detect_file"] = lambda file: jinja_filters.detect_file(file)


# Database cleaning task
async def background_task():
    """ Delete old ticket entries for privacy reasons """
    while True:
        db.execute("DELETE FROM tickets WHERE ? > expire", (int(time.time()),))
        await asyncio.sleep(5)


@app.before_serving
async def startup():
    app.background_task = asyncio.ensure_future(background_task())


@app.after_serving
async def shutdown():
    app.background_task.cancel()


def jsonify_standard(name: str, description: str, code: int = 200):
    """ The standard JSON output to my API """
    return jsonify({
        "code": code, "name": name, "description": description
    }), code


@app.route("/")
async def index():
    return await render_template("index.html", config=config)


@app.route("/<ticket_id>")
async def show_ticket(ticket_id):
    ticket_db = tickets.Ticket(db=db)
    data = ticket_db.fetch_ticket(ticket_id)

    if not data:
        return {"status": 404, "code": ticket_id}

    if str(data["submitted_by"]) == str(config["bot_id"]):
        valid_source = tickets.TicketSource.valid
    else:
        valid_source = tickets.TicketSource.unknown

    get_logs = json.loads(data["logs"])

    # To prevent XSS, fucking hell it's shit, but I'll find a better solution later...
    converted_logs = []
    for msg in get_logs["messages"]:
        temp_holder = []
        for content in msg["content"]:
            converted_msg = None
            if content["msg"]:
                converted_msg = content["msg"]

            _mentions = {
                "users": content.get("mentions", {}).get("users", {}),
                "roles": content.get("mentions", {}).get("roles", {}),
                "channels": content.get("mentions", {}).get("channels", {})
            }

            if converted_msg:
                for g in re_mentions.findall(converted_msg):
                    try:
                        if g[1] == "@":
                            converted_msg = converted_msg.replace(g[0], f"@{_mentions['users'][g[2]]}")
                        elif g[1] == "#":
                            converted_msg = converted_msg.replace(g[0], f"#{_mentions['channels'][g[2]]}")
                        elif g[1] == "@&":
                            converted_msg = converted_msg.replace(g[0], f"@{_mentions['roles'][g[2]]}")
                    except Exception:
                        # Old ticket, no mentions saved
                        pass

            temp_holder.append({
                "id": content["id"],
                "msg": converted_msg,
                "attachments": content.get("attachments", []),
                "reply": content.get("reply", None),
                "stickers": content.get("stickers", []),
                "edited": content.get("edited", False),
                "deleted": content.get("deleted", False)
            })

        converted_logs.append({
            "author": msg["author"],
            "timestamp": datetime.fromtimestamp(msg["timestamp"], UTC).strftime("%Y-%m-%d %H:%M:%S (UTC)"),
            "content": temp_holder
        })

    get_logs["messages"] = converted_logs

    messages_map = {}
    for i, entry in enumerate(get_logs["messages"], start=1):
        for ii, msg_entry in enumerate(entry["content"], start=1):
            messages_map[msg_entry["id"]] = msg_entry
            messages_map[msg_entry["id"]]["href_id"] = f"message-{i}-{ii}"
            messages_map[msg_entry["id"]]["author"] = entry["author"]

            if msg_entry["msg"] is not None:
                msg_entry["msg"] = msg_entry["msg"].replace("\n", " ")

            messages_map[msg_entry["id"]]["msg_shoten"] = (
                msg_entry["msg"]
                if len(msg_entry["msg"] or "...") < 32
                else msg_entry["msg"][:32].strip() + "..."
            )

    def reference_message(msg_id):
        return messages_map.get(msg_id, None)

    def get_author(user_id: int):
        if str(user_id) not in get_logs["users"]:
            return {
                "avatar": "/static/images/default.png",
                "username": "Unknown#0000",
            }
        return get_logs["users"][str(user_id)]

    return await render_template(
        "ticket.html",
        status=200, title=f"#{get_logs['channel_name']} | xelA Tickets", submitted_by=data["submitted_by"],
        ticket_id=data["ticket_id"], guild_id=data["guild_id"], author_id=str(data["author_id"]),
        created_at=data["created_at"], confirmed_by=str(data["confirmed_by"]),
        expires=data["expire"], context=data["context"], official_bot=config["bot_id"],
        channel_name=get_logs["channel_name"], valid_source=valid_source, logs=get_logs,
        reference_message=reference_message, str=str, get_author=get_author
    )


@app.route("/<ticket_id>/download")
async def download_ticket(ticket_id):
    ticket_db = tickets.Ticket(db=db)
    data = ticket_db.fetch_ticket(ticket_id)

    if not data:
        return jsonify_standard("Not found", f"Ticket {ticket_id} not found", 404)

    return jsonify(json.loads(data["logs"]))


@app.route("/submit/example")
async def submit_example():
    with open("examples/submit.json", "r") as f:
        data = json.load(f)

    return jsonify(data)


@app.route("/submit", methods=["POST"])
async def submit():
    token = request.headers.get("Authorization") or None
    uploaded_file = False

    files = await request.files
    if files:
        uploaded_file = True
        file = files.get("ticket_file") or None
        if not file:
            return jsonify_standard("Missing file", "Missing uploaded file...", 400)
        if file.content_type != "application/json":
            return jsonify_standard("Invalid file", "Invalid file type, only JSON is allowed...", 400)

        file_body = file.stream.read().decode("utf-8")
        try:
            post_data = json.loads(file_body)
        except Exception as e:
            return jsonify_standard("Broken", str(e), 400)
    else:
        post_data = await request.json
        if not post_data:
            return jsonify_standard("Missing data", "Missing JSON/data...", 400)

    if "submitted_by" not in post_data:
        return jsonify_standard("Missing data", "Missing 'submitted_by' in JSON", 400)

    if post_data["submitted_by"] == config["bot_id"]:
        if not token:
            post_data["submitted_by"] = "86477779717066752"  # If a user is uploading the JSON file without changing submitted_by
        if token and token != config["token"]:
            return jsonify_standard("Invalid token", "Invalid Authorization token...", 403)

    make_ticket = tickets.Ticket(payload=post_data, db=db)
    code, data = make_ticket.attempt_post()

    if code != 200:
        return jsonify_standard(f"Error: {data.message}", data.validator, code)

    if uploaded_file:
        return redirect(f"/{data}")
    else:
        return jsonify_standard("Success", data, code)


if __name__ == "__main__":
    app.run(
        port=config.get("port", 8080),
        debug=config.get("debug", False)
    )
