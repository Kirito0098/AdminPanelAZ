"""HTTP attachment responses that keep the intended filename across browsers.

Safari, iOS WebView and some Chromium builds map ``text/plain`` (+ ``nosniff``)
to a ``.txt`` extension and ignore ``Content-Disposition`` / ``<a download>``.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import Response

DOWNLOAD_MEDIA_TYPE = "application/octet-stream"


def content_disposition_attachment(filename: str) -> str:
    name = (filename or "download").replace("\\", "_").replace('"', "").replace("\r", "").replace("\n", "")
    if not name.strip():
        name = "download"
    ascii_name = name.encode("ascii", "replace").decode("ascii")
    encoded = quote(name, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


def attachment_response(content: str | bytes, filename: str) -> Response:
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(
        content=body,
        media_type=DOWNLOAD_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition_attachment(filename)},
    )
