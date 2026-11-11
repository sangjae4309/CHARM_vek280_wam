"""Device resources, separate from CHARM's uncalibrated performance model.

VE2802: AMD DS950 resource/array tables (v2.11), AM020 memory architecture.
Reservations and PLIO budgets are software policies, not device capacities.
"""

DEVICES = {
    "vck190": {
        "architecture": "aie", "aie_cols": 50, "aie_rows": 8,
        "aie_num": 400, "local_memory_bytes": 32 * 1024,
        "memory_tiles": 0, "memory_tile_bytes": 0,
        # Preserve the original CHARM model, including its resource counts.
        "bram_total": 967, "uram_total": 463,
        "bram_reserved": 100, "uram_reserved": 43,
        "plio_in": 100, "plio_out": 80,
    },
    "vek280": {
        "architecture": "aie_ml", "aie_cols": 38, "aie_rows": 8,
        "aie_num": 304, "local_memory_bytes": 64 * 1024,
        "memory_tiles": 76, "memory_tile_bytes": 512 * 1024,
        "bram_total": 600, "uram_total": 264,
        # Retain CHARM's reserve policy until platform utilization is measured.
        "bram_reserved": 100, "uram_reserved": 43,
        "pl_interface_tiles": 28,
        "plio_128bit_in_ceiling": 112, "plio_128bit_out_ceiling": 84,
        # Conservative inherited budgets below aggregate physical ceilings.
        # Channel frequency restrictions and routing still require the mapper.
        "plio_in": 100, "plio_out": 80,
    },
}


def device_resources(device, limits=None):
    resources = DEVICES[device.lower()].copy()
    resources["bram"] = resources["bram_total"] - resources["bram_reserved"]
    resources["uram"] = resources["uram_total"] - resources["uram_reserved"]
    for key, value in (limits or {}).items():
        if key not in ("aie_num", "aie_cols", "aie_rows", "bram", "uram", "plio_in", "plio_out"):
            raise ValueError(f"Unknown resource budget: {key}")
        if not isinstance(value, int) or value <= 0 or value > resources[key]:
            raise ValueError(f"{key} must be a positive integer <= {resources[key]}")
        resources[key] = value
    return resources


def validate_int8_memory(m, k, n, capacity):
    """Check retained packet-kernel addresses, including neighboring memory use.

    A ping/pong can share a module with its neighbor's B, C and stack.
    The union is a conservative placement check; it is not a bank-contention
    or compiler feasibility proof. Memory-tile capacity is not added here.
    """
    if k != 64 or m <= 0 or n <= 0 or m % 8 or n % 4:
        raise ValueError("Ported INT8 kernel requires K=64, M%8=0 and N%4=0")
    regions = [(0x0000, m*k, "A ping"), (0x2000, m*k, "A pong"),
               (0x3000, 1024, "stack"),
               (0x4000, k*n, "B ping"), (0x6000, k*n, "B pong"),
               (0x5000, m*n, "C ping"), (0x7000, m*n, "C pong")]
    regions.sort()
    for start, size, label in regions:
        if start + size > capacity:
            raise ValueError(f"{label} exceeds local data memory")
    for (start, size, label), (next_start, _, next_label) in zip(regions, regions[1:]):
        if start + size > next_start:
            raise ValueError(f"Retained addresses overlap: {label}, {next_label}")
    return {"capacity_bytes": capacity, "highest_address_exclusive": max(a+b for a,b,_ in regions),
            "reserved_bytes_in_union": sum(b for _,b,_ in regions),
            "stack_bytes_assumed": 1024, "target_compilation_verified": False}
