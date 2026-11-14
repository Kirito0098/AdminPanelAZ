"""OpenVPN route limit compaction and DPI-aware budgeting."""
import ipaddress
import logging

from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.parsers import _normalize_cidrs

logger = logging.getLogger(__name__)


def _compress_cidrs_to_limit(cidrs, limit):
    normalized = _normalize_cidrs(cidrs)
    if not normalized:
        return [], None

    if limit is None or int(limit) <= 0:
        return [], {
            "strategy": "supernet_compaction",
            "original_cidr_count": len(normalized),
            "compressed_cidr_count": 0,
            "target_limit": 0,
            "aggregation_method": "netaddr",
        }

    target_limit = int(limit)

    try:
        import netaddr
    except ImportError:
        raise RuntimeError("netaddr package is required for CIDR aggregation. Install it with: pip install netaddr")

    # Parse all networks using netaddr for proper handling
    try:
        networks = [netaddr.IPNetwork(value) for value in normalized]
    except (netaddr.AddrFormatError, ValueError) as e:
        logger.warning(f"Failed to parse CIDR blocks with netaddr: {e}. Falling back to ipaddress module.")
        networks = [ipaddress.ip_network(value, strict=False) for value in normalized]

    # Remove redundant CIDRs where one is completely contained within another
    # This is a conservative approach that doesn't merge adjacent blocks
    non_redundant = []
    sorted_networks = sorted(networks, key=lambda n: (int(n.ip), -n.prefixlen))

    for net in sorted_networks:
        is_redundant = False
        for other in non_redundant:
            if net in other:
                # This network is contained in another, skip it
                is_redundant = True
                break
        if not is_redundant:
            # Remove any previously added networks that are now contained in this one
            non_redundant = [n for n in non_redundant if n not in net]
            non_redundant.append(net)

    # If deduplication resulted in redundant entries being removed
    if len(non_redundant) < len(normalized):
        # We had overlaps, return deduplicated
        if len(non_redundant) <= target_limit:
            compressed = [str(net) for net in sorted(non_redundant, key=lambda n: (int(n.ip), n.prefixlen))]
            return compressed, {
                "strategy": "netaddr_deduplicate_overlaps",
                "original_cidr_count": len(normalized),
                "compressed_cidr_count": len(compressed),
                "target_limit": target_limit,
                "aggregation_method": "netaddr",
            }
    else:
        # No overlaps found, return original if within limit
        if len(normalized) <= target_limit:
            return normalized, None

    # At this point we're over limit, need to trim
    # Sort by prefix length (ascending = keep larger blocks first), then by address
    trimmed = sorted(
        non_redundant,
        key=lambda n: (n.prefixlen, int(n.ip)),
    )[:target_limit]

    compressed = [str(net) for net in trimmed]
    return compressed, {
        "strategy": "netaddr_trim_to_limit",
        "original_cidr_count": len(normalized),
        "compressed_cidr_count": len(compressed),
        "target_limit": target_limit,
        "aggregation_method": "netaddr",
        "trimmed_to_limit": True,
    }

def _normalize_dpi_priority_files(values):
    if values is None:
        return []

    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]

    normalized = []
    seen = set()
    for item in values:
        file_name = str(item or "").strip()
        if not file_name or file_name in seen:
            continue
        if file_name not in IP_FILES:
            continue
        normalized.append(file_name)
        seen.add(file_name)
    return normalized

def _normalize_priority_min_budget(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return 0

    if parsed <= 0:
        return 0
    return parsed

def _allocate_route_budget(
    counts,
    total_limit,
    *,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
):
    """Single source of truth for the global route budget.

    ``counts`` is either ``{file_name: route_count}`` or an iterable of
    ``(file_name, route_count)`` pairs. Returns ``(budgets, meta)`` where
    ``budgets[file_name]`` is how many routes that file may keep, and ``meta``
    describes the applied strategy (``None`` when no limit applies).

    Both the CIDR-list path (:func:`_apply_total_route_limit`) and the
    counts-only estimate path (``db_pipeline._apply_total_route_limit_counts``)
    go through this function, so the preview and the real build can never
    disagree on the per-file budget.
    """
    pairs = list(counts.items()) if isinstance(counts, dict) else list(counts or [])

    counts_by_name = {}
    for name, value in pairs:
        counts_by_name[str(name)] = int(value or 0)

    if total_limit is None or int(total_limit) <= 0:
        return dict(counts_by_name), None

    route_limit = int(total_limit)
    original_total = sum(counts_by_name.values())

    if original_total <= route_limit:
        # Keep the meta even when nothing was cut: UI needs the budget itself.
        return dict(counts_by_name), {
            "strategy": "none",
            "limit": route_limit,
            "original_total": original_total,
            "warning": None,
        }

    non_empty = {name: count for name, count in counts_by_name.items() if count > 0}
    if not non_empty:
        return dict(counts_by_name), None

    priority_files = set(_normalize_dpi_priority_files(dpi_priority_files))
    mandatory_files = set(_normalize_dpi_priority_files(dpi_mandatory_files))
    priority_files.update(mandatory_files)
    priority_min_budget = _normalize_priority_min_budget(dpi_priority_min_budget)

    # Deterministic order — bigger files first, ties by file name — so the
    # iteration order of `counts` never changes who gets a route.
    by_size = sorted(non_empty, key=lambda name: (-non_empty[name], name))
    budgets = {name: 0 for name in non_empty}

    if route_limit < len(non_empty):
        # Fewer routes than files: keep the most important ones alive.
        if mandatory_files:
            first = [name for name in by_size if name in mandatory_files]
        elif priority_files and priority_min_budget > 0:
            first = [name for name in by_size if name in priority_files]
        else:
            first = []
        ordered = first + [name for name in by_size if name not in first]
        for name in ordered[:route_limit]:
            budgets[name] = 1
        return budgets, _route_budget_meta(
            route_limit,
            original_total,
            budgets,
            priority_files,
            mandatory_files,
            priority_min_budget,
        )

    reserved_total = 0

    if mandatory_files:
        for name in sorted(non_empty):
            if name in mandatory_files:
                budgets[name] = max(budgets[name], 1)
                reserved_total += 1

    if reserved_total > route_limit:
        # Not even one route per mandatory file fits: keep the biggest ones.
        budgets = {name: 0 for name in non_empty}
        reserved_total = 0
        for name in [name for name in by_size if name in mandatory_files]:
            if reserved_total >= route_limit:
                break
            budgets[name] = 1
            reserved_total += 1

    if priority_files and priority_min_budget > 0:
        for name in sorted(non_empty):
            if name not in priority_files:
                continue
            reserved = min(non_empty[name], priority_min_budget)
            new_budget = max(budgets[name], reserved)
            reserved_total += max(0, new_budget - budgets[name])
            budgets[name] = new_budget

    if reserved_total > route_limit:
        budgets = {name: 0 for name in non_empty}
        reserved_total = 0
        for name in [name for name in by_size if name in priority_files]:
            if reserved_total >= route_limit:
                break
            budgets[name] = 1
            reserved_total += 1

    remaining_limit = max(route_limit - reserved_total, 0)
    remaining_capacity = {
        name: max(0, non_empty[name] - budgets[name]) for name in non_empty
    }
    total_capacity = sum(remaining_capacity.values())

    if remaining_limit > 0 and total_capacity > 0:
        raw_shares = {}
        for name in non_empty:
            capacity = remaining_capacity[name]
            if capacity <= 0:
                raw_shares[name] = 0.0
                continue
            share = (capacity * remaining_limit) / total_capacity
            raw_shares[name] = share
            budgets[name] += min(capacity, int(share))

        allocated = sum(budgets.values())
        if allocated > route_limit:
            for name in sorted(budgets, key=lambda key: (-budgets[key], key)):
                while budgets[name] > 0 and allocated > route_limit:
                    budgets[name] -= 1
                    allocated -= 1
                if allocated <= route_limit:
                    break

        if allocated < route_limit:
            # Hand the rounding remainder to the largest fractional share first.
            for name in sorted(raw_shares, key=lambda key: (-(raw_shares[key] - int(raw_shares[key])), key)):
                while budgets[name] < non_empty[name] and allocated < route_limit:
                    budgets[name] += 1
                    allocated += 1
                if allocated >= route_limit:
                    break

    return budgets, _route_budget_meta(
        route_limit,
        original_total,
        budgets,
        priority_files,
        mandatory_files,
        priority_min_budget,
    )


def _route_budget_meta(
    route_limit,
    original_total,
    budgets,
    priority_files,
    mandatory_files,
    priority_min_budget,
):
    dropped_mandatory_files = sorted(
        mandatory_files - {name for name, budget in budgets.items() if budget > 0}
    )
    meta = {
        "strategy": "global_total_route_limit",
        "limit": route_limit,
        "original_total": original_total,
        "warning": (
            "Не все обязательные detected-провайдеры поместились в лимит"
            if dropped_mandatory_files
            else None
        ),
        "priority_files": sorted(priority_files),
        "mandatory_files": sorted(mandatory_files),
        "priority_min_budget": priority_min_budget,
        "dropped_mandatory_files": dropped_mandatory_files,
    }
    return meta


def _apply_total_route_limit(
    entries,
    total_limit,
    *,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
):
    if not entries:
        return entries, None

    if total_limit is None or int(total_limit) <= 0:
        return entries, None

    route_limit = int(total_limit)
    original_total = sum(len(item.get("cidrs") or []) for item in entries)

    counts = {str(item.get("file") or ""): len(item.get("cidrs") or []) for item in entries}
    budgets, budget_meta = _allocate_route_budget(
        counts,
        route_limit,
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )
    if budget_meta is None:
        return entries, None

    if budget_meta["strategy"] == "none":
        return entries, {
            "strategy": "none",
            "limit": route_limit,
            "original_total_cidr_count": original_total,
            "compressed_total_cidr_count": original_total,
            "warning": None,
        }

    priority_files = set(budget_meta["priority_files"])
    mandatory_files = set(budget_meta["mandatory_files"])
    priority_min_budget = int(budget_meta["priority_min_budget"])

    adjusted_entries = []
    per_file = []
    for entry in entries:
        item = dict(entry)
        file_name = str(item.get("file") or "")
        cidrs = list(item.get("cidrs") or [])
        budget = budgets.get(file_name, len(cidrs))
        compressed_cidrs, compression_meta = _compress_cidrs_to_limit(cidrs, budget)
        item["cidrs"] = compressed_cidrs
        if compression_meta and compression_meta.get("compressed_cidr_count", len(compressed_cidrs)) < compression_meta.get("original_cidr_count", len(cidrs)):
            item["global_route_optimization"] = compression_meta
        adjusted_entries.append(item)
        per_file.append(
            {
                "file": item.get("file"),
                "original_cidr_count": len(cidrs),
                "compressed_cidr_count": len(compressed_cidrs),
                "target_budget": budget,
                "dpi_priority": bool(file_name in priority_files),
                "dpi_mandatory": bool(file_name in mandatory_files),
            }
        )

    compressed_total = sum(len(item.get("cidrs") or []) for item in adjusted_entries)
    dropped_mandatory_files = list(budget_meta["dropped_mandatory_files"])
    meta = {
        "strategy": "global_total_route_limit",
        "limit": route_limit,
        "original_total_cidr_count": original_total,
        "compressed_total_cidr_count": compressed_total,
        "files": per_file,
    }
    if mandatory_files:
        meta["dpi_mandatory"] = {
            "enabled": True,
            "mandatory_files": sorted(mandatory_files),
            "dropped_mandatory_files": dropped_mandatory_files,
        }
        if dropped_mandatory_files:
            meta["warning"] = budget_meta["warning"]
    if priority_files and priority_min_budget > 0:
        meta["dpi_priority"] = {
            "enabled": True,
            "priority_files": sorted(priority_files),
            "priority_min_budget": priority_min_budget,
        }
    return adjusted_entries, meta
