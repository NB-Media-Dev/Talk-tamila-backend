"""Turn an uploaded file into a base64 data URL (images and videos)."""

import base64
import os
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


async def file_to_base64_data_url(file: UploadFile) -> Tuple[str, str]:
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = file.content_type

    if not content_type or content_type == "application/octet-stream":
        if ext in VIDEO_EXTENSIONS:
            content_type = "video/mp4"
        elif ext == ".png":
            content_type = "image/png"
        elif ext == ".gif":
            content_type = "image/gif"
        elif ext == ".webp":
            content_type = "image/webp"
        else:
            content_type = "image/jpeg"

    media_type = "video" if ("video" in content_type or ext in VIDEO_EXTENSIONS) else "image"
    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"
    return data_url, media_type
