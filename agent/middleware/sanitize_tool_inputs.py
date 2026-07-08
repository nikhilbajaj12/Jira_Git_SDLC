"""Sanitize tool input middleware.

Coerces malformed integer fields in read_file calls before they reach Pydantic
validation.  The LLM occasionally generates strings like ``'1, 80'`` or
``'170, "limit": 60'`` for integer parameters; we extract the leading digit
sequence so the call succeeds instead of burning an LLM turn on a retry.

Also normalizes Windows absolute paths in file tool arguments to virtual
sandbox paths so the LLM can use paths returned by Windows shell commands
(e.g. ``pwd`` → ``C:\\Users\\...\\sandbox_workspace\\repo\\file.txt``).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

_READ_FILE_INT_FIELDS = ("offset", "limit")

# Tools that accept file/directory path arguments
_PATH_TOOL_ARGS: dict[str, tuple[str, ...]] = {
    "read_file": ("file_path",),
    "write_file": ("file_path",),
    "edit_file": ("file_path",),
    "ls": ("path",),
    "glob": ("pattern", "path"),
    "grep": ("pattern", "path"),
}


def _coerce_int(value: object) -> int | None:
    """Extract the first integer from *value* if it is a non-integer string.

    Returns the parsed integer, or ``None`` if no leading digits are found.
    If *value* is already an ``int`` (or ``None``), returns it unchanged.
    """
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.match(r"\s*(\d+)", value)
        if match:
            return int(match.group(1))
        return None
    return None


def _sanitize_read_file_args(args: dict) -> dict:
    """Return a copy of *args* with integer fields coerced where needed."""
    sanitized = dict(args)
    for field in _READ_FILE_INT_FIELDS:
        if field in sanitized:
            original = sanitized[field]
            coerced = _coerce_int(original)
            if coerced is not None and coerced != original:
                logger.warning("Coercing read_file.%s from %r to %d", field, original, coerced)
                sanitized[field] = coerced
    return sanitized


def _get_sandbox_root() -> str:
    """Return the local sandbox root dir as a forward-slash path, or ``""``."""
    root = os.environ.get("LOCAL_SANDBOX_ROOT_DIR", "")
    if root:
        return os.path.normpath(root).replace("\\", "/")
    return ""


def _normalize_path(value: object) -> object:
    """Convert a Windows absolute path to a virtual sandbox path.

    Leaves non-string values and already-virtual paths unchanged.
    """
    if not isinstance(value, str):
        return value

    # Normalise backslashes first
    path = value.replace("\\", "/")

    # Already a virtual path (starts with /) — pass through
    if path.startswith("/"):
        return path

    # Not a Windows absolute path — leave for validate_path to handle
    if not (len(path) >= 3 and path[1] == ":" and path[0].isalpha()):
        return path

    # Windows absolute path — try to strip the sandbox root prefix
    root_dir = _get_sandbox_root()
    if root_dir:
        # Ensure root dir has trailing /
        root_prefix = root_dir.rstrip("/") + "/"
        if path.startswith(root_prefix):
            relative = path[len(root_prefix):]
            virtual = "/" + relative
            logger.info("Normalised path %s -> %s", value, virtual)
            return virtual

    # Also try well-known markers as fallback
    for marker in ("/sandbox_workspace/", "/workspace/"):
        idx = path.find(marker)
        if idx != -1:
            relative = path[idx + len(marker):]
            virtual = "/" + relative
            logger.info("Normalised path %s -> %s (via %s)", value, virtual, marker.rstrip("/"))
            return virtual

    logger.warning("Could not normalise Windows absolute path to virtual path: %s", value)
    return value


def _normalise_tool_path_args(name: str, args: dict) -> dict:
    """Return a copy of *args* with path arguments normalised to virtual paths."""
    path_fields = _PATH_TOOL_ARGS.get(name)
    if not path_fields:
        return args

    sanitized = dict(args)
    changed = False
    for field in path_fields:
        if field in sanitized:
            original = sanitized[field]
            normalised = _normalize_path(original)
            if normalised is not original:
                sanitized[field] = normalised
                changed = True
    return sanitized if changed else args


class SanitizeToolInputsMiddleware(AgentMiddleware):
    """Intercept tool calls to sanitise their inputs before execution.

    Currently handles:
    - Malformed ``offset`` / ``limit`` integers in ``read_file``.
    - Windows absolute paths in file-tool arguments → virtual sandbox paths.
    """

    state_schema = AgentState

    def _sanitize_request(self, request: ToolCallRequest) -> ToolCallRequest:
        tool_call = request.tool_call
        if not isinstance(tool_call, dict):
            return request

        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        if not isinstance(args, dict):
            return request

        # 1. Coerce malformed integers (read_file only)
        if name == "read_file":
            args = _sanitize_read_file_args(args)

        # 2. Normalise Windows paths for any file tool
        args = _normalise_tool_path_args(name, args)

        if args is tool_call.get("args"):
            return request
        new_tool_call = {**tool_call, "args": args}
        return request.override(tool_call=new_tool_call)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        return handler(self._sanitize_request(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        return await handler(self._sanitize_request(request))
