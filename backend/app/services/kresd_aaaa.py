"""AAAA answer switch for AntiZapret Knot Resolver: a managed NODATA block in custom.lua / custom2.lua.

AntiZapret's kresd.conf answers every AAAA query with ``::``; setup.sh rewrites kresd.conf but keeps
/etc/knot-resolver/*.lua, so the switch lives in the custom files.
"""

from __future__ import annotations

from typing import Literal

AaaaMode = Literal["zero", "nodata", "custom"]

AAAA_TARGETS: dict[str, str] = {"antizapret": "kresd_custom", "vpn": "kresd_custom2"}

BLOCK_START = "-- [ADMINPANEL-AAAA-NODATA-START]"
BLOCK_END = "-- [ADMINPANEL-AAAA-NODATA-END]"

NODATA_BLOCK = f"""{BLOCK_START} Managed by AdminPanelAZ: answer AAAA with NODATA instead of ::
do
\tlocal nodata = policy.ANSWER({{[kres.type.SOA] = {{rdata = kres.parse_rdata({{'SOA . . 1 1 1 1 86400'}}), ttl = 86400}}}}, true)
\tlocal rule = policy.add(function(_, query)
\t\tif query.stype == kres.type.AAAA then
\t\t\treturn nodata
\t\tend
\tend)
\t-- kresd.conf adds its AAAA -> :: rule before loading this file and the first matching rule wins;
\t-- policy.special_names (localhost, private zones) stay ahead of this rule.
\tif policy.rules[#policy.rules] == rule then
\t\ttable.remove(policy.rules)
\t\tlocal special = {{}}
\t\tfor _, item in ipairs(policy.special_names) do
\t\t\tspecial[item.cb] = true
\t\tend
\t\tlocal pos = 1
\t\tfor i, r in ipairs(policy.rules) do
\t\t\tif special[r.cb] then
\t\t\t\tpos = i + 1
\t\t\tend
\t\tend
\t\ttable.insert(policy.rules, pos, rule)
\tend
end
{BLOCK_END}
"""


def aaaa_mode(content: str) -> AaaaMode:
    starts, ends = content.count(BLOCK_START), content.count(BLOCK_END)
    if starts == 0 and ends == 0:
        return "zero"
    if starts == 1 and ends == 1 and NODATA_BLOCK in content:
        return "nodata"
    return "custom"


def with_aaaa_nodata(content: str, enabled: bool) -> str:
    """Add or remove the managed block, leaving the rest of the file as it was."""
    mode = aaaa_mode(content)
    if mode == "custom":
        raise ValueError("AAAA block was edited by hand")
    if enabled:
        if mode == "nodata":
            return content
        base = content.rstrip("\n")
        return f"{base}\n\n{NODATA_BLOCK}" if base else NODATA_BLOCK
    if mode == "zero":
        return content
    before, after = content.split(NODATA_BLOCK, 1)
    if before.endswith("\n\n"):
        before = before[:-1]
    return before + after
