"""Sample module (synthetic) used to smoke-test code ingestion and line-level citations."""

PERMIT_FEES = {
    "residential_parking": 0,
    "street_occupancy": 75,
    "sidewalk_cafe": 250,
}

MAX_STREET_OCCUPANCY_DAYS = 30


def permit_fee(kind: str, days: int = 1) -> int:
    """Street occupancy permits are charged per day; other permits are flat."""
    if kind not in PERMIT_FEES:
        raise ValueError(f"unknown permit type: {kind}")
    if kind == "street_occupancy":
        if days > MAX_STREET_OCCUPANCY_DAYS:
            raise ValueError("street occupancy permits are limited to 30 days")
        return PERMIT_FEES[kind] * days
    return PERMIT_FEES[kind]
