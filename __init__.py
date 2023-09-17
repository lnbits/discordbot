from fastapi import APIRouter

from lnbits.db import Database
from lnbits.helpers import template_renderer

db = Database("ext_discordbot")

discordbot_static_files = [
    {
        "path": "/discordbot/static",
        "name": "discordbot_static",
    }
]

discordbot_ext: APIRouter = APIRouter(prefix="/discordbot", tags=["discordbot"])


def discordbot_renderer():
    return template_renderer(["discordbot/templates"])


from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403
