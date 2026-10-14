"""``list_providers``."""

from __future__ import annotations

from capybucks_mcp.catalog import CATALOG, key_configured
from capybucks_mcp.envelope import YAHOO_WARNING, success


async def list_providers() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for spec in CATALOG:
        row = spec.as_dict()
        row["key_configured"] = key_configured(spec.name)
        rows.append(row)
    return success(
        tool="list_providers",
        data={"providers": rows},
        warnings=[YAHOO_WARNING],
    )
