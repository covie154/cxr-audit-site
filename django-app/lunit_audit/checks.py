"""Project-level deployment and transport checks."""

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_llm_transport(app_configs, **kwargs):
    """Warn when production uses plaintext LLM transport without an explicit allow flag."""

    if settings.DEBUG:
        return []

    parsed = urlparse(settings.LLM_BASE_URL)
    if parsed.scheme != "http":
        return []

    if settings.LLM_ALLOW_INSECURE_TRANSPORT:
        return [
            Warning(
                "LLM_BASE_URL uses HTTP in production with LLM_ALLOW_INSECURE_TRANSPORT enabled.",
                hint=(
                    "Use this only for isolated private transport. Prefer HTTPS or a "
                    "controlled private inference network for production ePHI workflows."
                ),
                id="lunit_audit.W001",
            )
        ]

    return [
        Warning(
            "LLM_BASE_URL uses HTTP while DEBUG=False.",
            hint=(
                "Use an HTTPS OpenAI-compatible endpoint, or set "
                "LLM_ALLOW_INSECURE_TRANSPORT=True only after documenting private "
                "network isolation and endpoint authentication."
            ),
            id="lunit_audit.W002",
        )
    ]
