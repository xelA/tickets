import time
import secrets
import enum
import logging

from dataclasses import dataclass
from jsonschema import validate, ValidationError
from postgreslite import AsyncPoolConnection

_log = logging.getLogger(__name__)


class TicketSource(enum.IntEnum):
    unknown = 0
    valid = 1
    approved = 2


@dataclass
class PostResult:
    """ Outcome of Ticket.attempt_post, ticket_id is only set when it worked """

    code: int
    ticket_id: str | None = None
    error: str = ""
    description: str = ""


class Ticket:
    def __init__(self, db: AsyncPoolConnection, payload: dict | None = None, expire: int = 86400):
        self.payload = payload
        self.db = db
        self.expire = expire
        self.re_discord_id = "^[0-9]{14,19}$"

    @property
    def generate_id(self) -> str:
        """ Generate random ID with Python.secrets """
        return secrets.token_urlsafe(10)

    async def fetch_ticket(self, ticket_id: str) -> dict | None:
        """ Fetch ticket from the database, logs are decoded from JSON already """
        return await self.db.fetchrow(
            "SELECT * FROM tickets WHERE ticket_id = $1", ticket_id
        )

    async def attempt_post(self) -> PostResult:
        """ Attempt to post JSON payload to the database """
        error = self.validation()
        if error:
            return PostResult(400, error=f"Error: {error.message}", description=str(error.validator))

        output: dict = self.payload or {}

        right_now = int(time.time())
        ticket_id = self.generate_id

        try:
            await self.db.execute(
                """
                INSERT INTO tickets
                    (ticket_id, guild_id, author_id, context, submitted_by, created_at, logs, expire, confirmed_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                ticket_id, int(output["guild_id"]), int(output["author_id"]), output["context"],
                int(output["submitted_by"]), int(output["created_at"]), output, right_now + self.expire,
                int(output["confirmed_by"])
            )
        except Exception:
            _log.exception("Failed to save ticket")
            return PostResult(500, error="Internal server error", description="Internal server error... contact site owner.")

        return PostResult(200, ticket_id=ticket_id)

    def validation(self) -> ValidationError | None:
        """ Validate the payload sent to POST """
        json_validation = {
            "definitions": {
                "content_entry": {
                    "type": "object",
                    "properties": {
                        "msg": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "edited": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "deleted": {"type": "boolean"},
                        "content": {"type": "string"},
                        # Optional, older tickets and other bots don't send them
                        "embeds": {"anyOf": [
                            {"type": "array", "maxItems": 10, "items": {"type": "object"}},
                            {"type": "null"}
                        ]},
                        "components": {"anyOf": [
                            {"type": "array", "maxItems": 40, "items": {"$ref": "#/definitions/component"}},
                            {"type": "null"}
                        ]}
                    },
                    "required": ["msg"]
                },

                # https://discord.com/developers/docs/components/reference
                "component": {
                    "type": "object",
                    "properties": {"type": {"type": "integer", "minimum": 1}},
                    "required": ["type"]
                },

                "users_entry": {
                    "type": "object",
                    "propertyNames": {"pattern": self.re_discord_id},
                    "patternProperties": {
                        f"{self.re_discord_id}": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "avatar": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                "badge": {"anyOf": [{"type": "string"}, {"type": "null"}]}
                            },
                            "required": ["username", "avatar", "badge"]
                        }
                    }
                },

                "messages": {
                    "type": "object",
                    "properties": {
                        "author": {"type": "string"},
                        "timestamp": {
                            "type": "number",
                            "minimum": 0
                        },
                        "content": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/content_entry"}
                        }
                    },
                    "required": ["author", "timestamp", "content"]
                }
            },

            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "channel_name": {"type": "string"},
                "created_at": {"type": "number", "minimum": 0},
                "submitted_by": {"type": "string", "pattern": self.re_discord_id},
                "confirmed_by": {"type": "string", "pattern": self.re_discord_id},
                "author_id": {"type": "string", "pattern": self.re_discord_id},
                "guild_id": {"type": "string", "pattern": self.re_discord_id},
                "users": {"$ref": "#/definitions/users_entry"},
                "messages": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/messages"}
                }
            },
            "required": ["channel_name", "guild_id", "created_at", "author_id", "users", "messages", "submitted_by", "context", "confirmed_by"]
        }

        try:
            validate(self.payload, schema=json_validation)
        except ValidationError as e:
            return e

        return None
