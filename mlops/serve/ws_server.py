"""
Brain_Scape — WebSocket Annotation Server

Real-time collaborative annotation sync via WebSocket.
Supports multiple concurrent users viewing/annotating the same scan.
Uses versioned annotations with optimistic locking.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class AnnotationSession:
    """A collaborative annotation session for a single scan."""
    scan_id: str
    connections: Dict[str, WebSocket] = field(default_factory=dict)  # user_id -> ws
    annotations: Dict[str, dict] = field(default_factory=dict)       # annotation_id -> annotation
    versions: Dict[str, int] = field(default_factory=dict)           # annotation_id -> latest version
    lock = None

    def __post_init__(self):
        self.lock = asyncio.Lock()


class AnnotationWebSocketManager:
    """Manages WebSocket connections and annotation sessions.

    Features:
    - Multiple concurrent users per scan
    - Real-time broadcast of annotation changes
    - Optimistic locking for concurrent edits
    - Version history for each annotation
    """

    def __init__(self):
        self.sessions: Dict[str, AnnotationSession] = {}  # scan_id -> session
        self._cleanup_task: Optional[asyncio.Task] = None

    def get_or_create_session(self, scan_id: str) -> AnnotationSession:
        """Get or create an annotation session for a scan."""
        if scan_id not in self.sessions:
            self.sessions[scan_id] = AnnotationSession(scan_id=scan_id)
            logger.info(f"Created annotation session for scan {scan_id}")
        return self.sessions[scan_id]

    async def connect(self, websocket: WebSocket, scan_id: str, user_id: str):
        """Accept a WebSocket connection and add to the session."""
        await websocket.accept()
        session = self.get_or_create_session(scan_id)

        async with session.lock:
            session.connections[user_id] = websocket
            logger.info(f"User {user_id} connected to scan {scan_id} "
                         f"({len(session.connections)} users)")

        # Send existing annotations to the new user
        for ann_id, ann in session.annotations.items():
            await self._send_to_user(websocket, {
                "type": "annotation_created",
                "annotation": ann,
            })

        # Notify others that a user joined
        await self._broadcast(session, {
            "type": "user_joined",
            "user_id": user_id,
            "scan_id": scan_id,
            "active_users": len(session.connections),
        }, exclude_user=user_id)

    async def disconnect(self, scan_id: str, user_id: str):
        """Remove a WebSocket connection from the session."""
        session = self.sessions.get(scan_id)
        if not session:
            return

        async with session.lock:
            session.connections.pop(user_id, None)
            logger.info(f"User {user_id} disconnected from scan {scan_id} "
                         f"({len(session.connections)} users remaining)")

        # Notify others
        await self._broadcast(session, {
            "type": "user_left",
            "user_id": user_id,
            "scan_id": scan_id,
            "active_users": len(session.connections),
        })

        # Clean up empty sessions
        if not session.connections:
            self.sessions.pop(scan_id, None)
            logger.info(f"Cleaned up empty session for scan {scan_id}")

    async def handle_message(self, scan_id: str, user_id: str, message: dict):
        """Process an incoming WebSocket message."""
        session = self.sessions.get(scan_id)
        if not session:
            return

        msg_type = message.get("type")

        if msg_type == "annotation_created":
            await self._handle_create(session, user_id, message)
        elif msg_type == "annotation_updated":
            await self._handle_update(session, user_id, message)
        elif msg_type == "annotation_deleted":
            await self._handle_delete(session, user_id, message)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_create(self, session: AnnotationSession, user_id: str, message: dict):
        """Handle annotation creation."""
        annotation = message.get("annotation", {})
        annotation_id = annotation.get("id")
        if not annotation_id:
            return

        async with session.lock:
            annotation["user_id"] = user_id
            annotation["created_at"] = datetime.utcnow().isoformat()
            annotation["version"] = 1
            session.annotations[annotation_id] = annotation
            session.versions[annotation_id] = 1

        await self._broadcast(session, {
            "type": "annotation_created",
            "annotation": annotation,
        })

    async def _handle_update(self, session: AnnotationSession, user_id: str, message: dict):
        """Handle annotation update with optimistic locking."""
        annotation = message.get("annotation", {})
        annotation_id = annotation.get("id")
        if not annotation_id:
            return

        async with session.lock:
            current_version = session.versions.get(annotation_id, 0)
            client_version = annotation.get("version", current_version)

            # Optimistic locking: reject if client version is stale
            if client_version != current_version:
                # Send conflict notification
                ws = session.connections.get(user_id)
                if ws:
                    await self._send_to_user(ws, {
                        "type": "annotation_conflict",
                        "annotation_id": annotation_id,
                        "server_version": current_version,
                        "client_version": client_version,
                        "server_annotation": session.annotations.get(annotation_id),
                    })
                return

            # Apply update
            new_version = current_version + 1
            annotation["version"] = new_version
            annotation["updated_at"] = datetime.utcnow().isoformat()
            annotation["updated_by"] = user_id
            session.annotations[annotation_id] = annotation
            session.versions[annotation_id] = new_version

        await self._broadcast(session, {
            "type": "annotation_updated",
            "annotation": annotation,
        })

    async def _handle_delete(self, session: AnnotationSession, user_id: str, message: dict):
        """Handle annotation deletion."""
        annotation_id = message.get("annotation_id")
        if not annotation_id:
            return

        async with session.lock:
            if annotation_id in session.annotations:
                del session.annotations[annotation_id]
                del session.versions[annotation_id]

        await self._broadcast(session, {
            "type": "annotation_deleted",
            "annotation_id": annotation_id,
            "deleted_by": user_id,
        })

    async def _broadcast(self, session: AnnotationSession, message: dict, exclude_user: str = None):
        """Broadcast a message to all connected users in a session."""
        disconnected = []
        for user_id, ws in session.connections.items():
            if user_id == exclude_user:
                continue
            try:
                await self._send_to_user(ws, message)
            except Exception:
                disconnected.append(user_id)

        # Clean up disconnected users
        for user_id in disconnected:
            session.connections.pop(user_id, None)

    async def _send_to_user(self, websocket: WebSocket, message: dict):
        """Send a JSON message to a single WebSocket."""
        await websocket.send_json(message)

    def get_session_info(self, scan_id: str) -> Optional[dict]:
        """Get information about an annotation session."""
        session = self.sessions.get(scan_id)
        if not session:
            return None
        return {
            "scan_id": scan_id,
            "active_users": len(session.connections),
            "annotation_count": len(session.annotations),
            "user_ids": list(session.connections.keys()),
        }


# Global instance
ws_manager = AnnotationWebSocketManager()


async def annotation_websocket_endpoint(websocket: WebSocket, scan_id: str, user_id: str):
    """FastAPI WebSocket endpoint for annotation collaboration."""
    await ws_manager.connect(websocket, scan_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await ws_manager.handle_message(scan_id, user_id, message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from user {user_id}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(scan_id, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        await ws_manager.disconnect(scan_id, user_id)