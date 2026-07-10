import os
import sys

from fastapi import status
from fastapi.routing import APIRoute

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers import chat


def test_conversation_attachment_upload_uses_accepted_status():
    route = next(
        route
        for route in chat.router.routes
        if isinstance(route, APIRoute) and route.path == "/conversation-attachment"
    )

    assert route.status_code == status.HTTP_202_ACCEPTED
