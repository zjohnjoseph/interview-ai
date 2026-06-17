from __future__ import annotations

import asyncio
import functools
from typing import Any

from pydantic import BaseModel

from app.services.llm_service import llm_service


async def call_llm_async(
    prompt: str,
    system_prompt: str = "You are a technical interviewer AI. Return structured JSON only.",
    response_model: type[BaseModel] | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(llm_service.call_llm, prompt, system_prompt, response_model),
    )
