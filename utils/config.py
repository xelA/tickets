from typing import TypedDict

from dotenvplus import DotEnv

__all__ = (
    "Config",
    "load_config",
)


class Config(TypedDict):
    HOST: str
    PORT: int
    DEBUG: bool
    BOT_ID: int
    API_TOKEN: str
    DB_PATH: str


def load_config(path: str = ".env") -> Config:
    """ Read the .env file, see .env.example for every key """
    return DotEnv[Config](path).as_typed()
