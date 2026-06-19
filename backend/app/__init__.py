"""Package initializer for app.

Contains runtime initialization, including global monkey-patching of the google-genai
SDK to support OpenRouter fallback seamlessly across all application phases.
"""

from __future__ import annotations

import sys

try:
    from google.genai.models import Models
    from google.genai.types import GenerateContentResponse, Candidate, Content, Part
    
    # Save the original SDK method
    original_generate_content = Models.generate_content

    def patched_generate_content(self, *, model: str, contents, config=None, **kwargs) -> GenerateContentResponse:
        """Globally intercepts text generation to route to OpenRouter with automatic Gemini fallback."""
        from app.core.config import settings
        from app.core.logging import get_logger
        import httpx

        log = get_logger("google.genai.patched")

        # 1. Parse prompt text from SDK contents structure
        prompt_str = ""
        if isinstance(contents, str):
            prompt_str = contents
        elif isinstance(contents, list):
            prompt_parts = []
            for c in contents:
                if isinstance(c, str):
                    prompt_parts.append(c)
                elif hasattr(c, "parts"):
                    for p in c.parts:
                        if hasattr(p, "text") and p.text:
                            prompt_parts.append(p.text)
                elif hasattr(c, "text") and c.text:
                    prompt_parts.append(c.text)
            prompt_str = "\n".join(prompt_parts)
        elif hasattr(contents, "parts"):
            prompt_parts = []
            for p in contents.parts:
                if hasattr(p, "text") and p.text:
                    prompt_parts.append(p.text)
            prompt_str = "\n".join(prompt_parts)
        elif hasattr(contents, "text") and contents.text:
            prompt_str = contents.text
        else:
            prompt_str = str(contents)

        # 2. Extract configuration
        temp = 0.0
        response_json = False
        if config:
            if hasattr(config, "temperature") and config.temperature is not None:
                temp = float(config.temperature)
            if hasattr(config, "response_mime_type") and config.response_mime_type == "application/json":
                response_json = True

        # 3. Call OpenRouter primarily if configured
        if settings.openrouter_api_key:
            try:
                log.info("openrouter.call_start", model=model, response_json=response_json)
                
                # Format model identifier for OpenRouter
                model_id = model
                if not model_id.startswith("google/") and "gemini" in model_id:
                    model_id = f"google/{model_id}"
                elif not model_id.startswith("google/") and not model_id.startswith("openai/") and "/" not in model_id:
                    model_id = f"google/{model_id}"

                headers = {
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/google-deepmind/ai-financial-document-analyst",
                    "X-Title": "AI Financial Document Analyst"
                }

                payload = {
                    "model": model_id,
                    "messages": [
                        {"role": "user", "content": prompt_str}
                    ],
                    "temperature": temp,
                }
                if response_json:
                    payload["response_format"] = {"type": "json_object"}

                timeout = settings.metric_llm_request_timeout or 60.0
                with httpx.Client(timeout=timeout) as http_client:
                    r = http_client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    r.raise_for_status()
                    res_data = r.json()
                    text_content = res_data["choices"][0]["message"]["content"]
                    log.info("openrouter.call_success", model=model_id)
                    return GenerateContentResponse(
                        candidates=[
                            Candidate(
                                content=Content(
                                    parts=[
                                        Part(text=text_content)
                                    ]
                                )
                            )
                        ]
                    )
            except Exception as or_exc:
                log.error("openrouter.call_failed", error=str(or_exc), msg="falling back to Gemini")

        # 4. Fallback to Gemini SDK call
        try:
            log.info("gemini.call_start", model=model)
            resp = original_generate_content(self, model=model, contents=contents, config=config, **kwargs)
            log.info("gemini.call_success", model=model)
            return resp
        except Exception as gem_exc:
            log.error("gemini.call_failed", error=str(gem_exc))
            # 5. Try OpenRouter as a secondary fallback if not tried or failed before
            if settings.openrouter_api_key:
                log.info("gemini.call_failed_trying_openrouter_secondary", model=model)
                try:
                    model_id = model
                    if not model_id.startswith("google/") and "gemini" in model_id:
                        model_id = f"google/{model_id}"
                    elif not model_id.startswith("google/") and not model_id.startswith("openai/") and "/" not in model_id:
                        model_id = f"google/{model_id}"

                    headers = {
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/google-deepmind/ai-financial-document-analyst",
                        "X-Title": "AI Financial Document Analyst"
                    }

                    payload = {
                        "model": model_id,
                        "messages": [
                            {"role": "user", "content": prompt_str}
                        ],
                        "temperature": temp,
                    }
                    if response_json:
                        payload["response_format"] = {"type": "json_object"}

                    timeout = settings.metric_llm_request_timeout or 60.0
                    with httpx.Client(timeout=timeout) as http_client:
                        r = http_client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json=payload
                        )
                        r.raise_for_status()
                        res_data = r.json()
                        text_content = res_data["choices"][0]["message"]["content"]
                        log.info("openrouter.secondary_call_success", model=model_id)
                        return GenerateContentResponse(
                            candidates=[
                                Candidate(
                                    content=Content(
                                        parts=[
                                            Part(text=text_content)
                                        ]
                                    )
                                )
                            ]
                        )
                except Exception as or_sec_exc:
                    log.error("openrouter.secondary_call_failed", error=str(or_sec_exc))
            raise gem_exc

    # Globally reassign class method
    Models.generate_content = patched_generate_content

except ImportError:
    pass
