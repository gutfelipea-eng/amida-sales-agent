"""Email template fallbacks — used when AI is unavailable or for A/B testing."""

TEMPLATES = {
    "first_touch_generic": {
        "subject": "AI execution for {firm_name}'s portfolio",
        "body": """Hi {first_name},

Saw you recently joined {firm_name} as {title} — congrats on the move.

Building AI capabilities across a PE portfolio is one of those roles where the strategy is clear but finding the right execution partner is the hard part.

We've been helping Nordic PE-backed companies go from AI roadmap to production systems — data platforms, ML pipelines, the boring-but-critical infrastructure that makes AI actually work.

Would a 15-minute call make sense to see if there's a fit?

Best,
Felipe
CEO, Amida AI""",
    },
}


def render_template(template_key: str, **kwargs) -> tuple[str, str]:
    """Render a template with the given variables. Returns (subject, body)."""
    tmpl = TEMPLATES[template_key]
    return (
        tmpl["subject"].format(**kwargs),
        tmpl["body"].format(**kwargs),
    )
