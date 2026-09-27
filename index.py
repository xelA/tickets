import json
import time
import asyncio

from datetime import datetime, UTC
from quart import Quart, render_template, request, jsonify, redirect
from postgreslite import PostgresLite
from utils import tickets, jinja_filters, discord_objects
from utils.config import load_config
from utils.md_extensions import DiscordMarkdown, plain_text

# Quart itself
app = Quart(__name__)
app.config["JSON_SORT_KEYS"] = False

# Create a loop (Python 3.10)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# General configs
config = load_config()

# dotenvplus reads numbers as int, the API compares them with strings from JSON
bot_id = str(config["BOT_ID"])
api_token = str(config["API_TOKEN"])

# Create or update the tables from schema.sql
database = PostgresLite(config.get("DB_PATH", "storage.db"))
database.sync_schema("schema.sql")
db = database.connect_async()

discord_md = DiscordMarkdown()

# Jinja2 template filters
app.jinja_env.filters["markdown"] = lambda text, mentions=None: discord_md.render(text, mentions)
app.jinja_env.filters["detect_file"] = jinja_filters.detect_file


@app.context_processor
def inject_globals():
    """ Variables every template can use """
    return {"year": datetime.now(UTC).year}


# Database cleaning task, started and stopped with the server
cleanup_tasks: set[asyncio.Task] = set()


async def background_task():
    """ Delete old ticket entries for privacy reasons """
    while True:
        await db.execute("DELETE FROM tickets WHERE $1 > expire", int(time.time()))
        await asyncio.sleep(5)


@app.before_serving
async def startup():
    """ Start deleting expired tickets """
    cleanup_tasks.add(asyncio.create_task(background_task()))


@app.after_serving
async def shutdown():
    """ Stop the cleanup task and close the database """
    for task in cleanup_tasks:
        task.cancel()
    await db.close()


def jsonify_standard(name: str, description: str, code: int = 200):
    """ The standard JSON output to my API """
    return jsonify({
        "code": code, "name": name, "description": description
    }), code


@app.route("/")
async def index():
    """ API docs and the JSON upload form """
    return await render_template("index.html")


@app.route("/<ticket_id>")
async def show_ticket(ticket_id: str):
    """ Render a ticket the way it looked in Discord """
    ticket_db = tickets.Ticket(db=db)
    data = await ticket_db.fetch_ticket(ticket_id)

    if not data:
        return await render_template(
            "ticket.html",
            status=404, code=ticket_id, title="404 | xelA Tickets"
        ), 404

    valid_source = tickets.TicketSource.valid if str(data["submitted_by"]) == bot_id else tickets.TicketSource.unknown

    get_logs = data["logs"]

    converted_logs = []
    for msg in get_logs["messages"]:
        temp_holder = []
        for content in msg["content"]:
            temp_holder.append({
                "id": content.get("id"),
                "msg": content.get("msg") or None,
                "mentions": content.get("mentions") if isinstance(content.get("mentions"), dict) else {},
                "attachments": content.get("attachments", []),
                "reply": content.get("reply", None),
                "stickers": content.get("stickers", []),
                "edited": content.get("edited", False),
                "deleted": content.get("deleted", False),
                # Both are optional, older tickets and other bots don't send them
                "embeds": discord_objects.normalize_embeds(content.get("embeds")),
                "components": discord_objects.normalize_components(content.get("components")),
            })

        # A reply always starts a new message group, like Discord
        groups: list[list[dict]] = []
        for entry in temp_holder:
            if not groups or entry["reply"]:
                groups.append([])
            groups[-1].append(entry)

        for group in groups:
            converted_logs.append({
                "author": msg["author"],
                "timestamp": datetime.fromtimestamp(msg["timestamp"], UTC).strftime("%Y-%m-%d %H:%M:%S (UTC)"),
                "content": group
            })

    get_logs["messages"] = converted_logs

    messages_map = {}
    for i, entry in enumerate(get_logs["messages"], start=1):
        for ii, msg_entry in enumerate(entry["content"], start=1):
            msg_entry["href_id"] = f"message-{i}-{ii}"
            msg_entry["author"] = entry["author"]

            # One line preview for replies, the message itself keeps its newlines
            preview = plain_text(msg_entry["edited"] or msg_entry["msg"], msg_entry["mentions"])
            if not preview and (msg_entry["embeds"] or msg_entry["components"] or msg_entry["attachments"]):
                preview = "Click to see attachment"
            msg_entry["msg_shoten"] = preview if len(preview) < 32 else preview[:32].strip() + "..."

            if msg_entry["id"] is not None:
                messages_map[str(msg_entry["id"])] = msg_entry

    def reference_message(msg_id: int | str) -> dict | None:
        """ The message a reply points to, if it's in this ticket """
        return messages_map.get(str(msg_id))

    def get_author(user_id: int | str) -> dict:
        """ User info from the ticket, or a placeholder for unknown users """
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
        expires=data["expire"], context=data["context"], official_bot=bot_id,
        channel_name=get_logs["channel_name"], valid_source=valid_source, logs=get_logs,
        reference_message=reference_message, str=str, get_author=get_author
    )


@app.route("/<ticket_id>/download")
async def download_ticket(ticket_id: str):
    """ The raw ticket JSON, same format as it was submitted """
    ticket_db = tickets.Ticket(db=db)
    data = await ticket_db.fetch_ticket(ticket_id)

    if not data:
        return jsonify_standard("Not found", f"Ticket {ticket_id} not found", 404)

    return jsonify(data["logs"])


@app.route("/submit/example")
async def submit_example():
    """ Example payload for /submit """
    with open("examples/submit.json", encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data)


@app.route("/submit", methods=["POST"])
async def submit():
    """ Save a ticket, either as a JSON body or an uploaded .json file """
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

    if str(post_data["submitted_by"]) == bot_id:
        if not token:
            post_data["submitted_by"] = "86477779717066752"  # If a user is uploading the JSON file without changing submitted_by
        if token and token != api_token:
            return jsonify_standard("Invalid token", "Invalid Authorization token...", 403)

    make_ticket = tickets.Ticket(payload=post_data, db=db)
    result = await make_ticket.attempt_post()

    if not result.ticket_id:
        return jsonify_standard(result.error, result.description, result.code)

    if uploaded_file:
        return redirect(f"/{result.ticket_id}")
    return jsonify_standard("Success", result.ticket_id, result.code)


if __name__ == "__main__":
    app.run(
        host=config.get("HOST", "127.0.0.1"),
        port=config.get("PORT", 8080),
        debug=config.get("DEBUG", False)
    )
