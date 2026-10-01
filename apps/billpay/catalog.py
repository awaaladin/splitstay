"""The billers SplitStay can pay. Adding airtime, cable TV or water = adding rows + a category here;
the group, contribution and payout code never mentions a specific biller."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Biller:
    service_id: str  # provider's code for the biller
    name: str
    category: str  # electricity | airtime | cable_tv | water
    variations: tuple[str, ...] = ()
    customer_label: str = "Customer number"


ELECTRICITY = "electricity"

_DISCO_VARIATIONS = ("prepaid", "postpaid")

BILLERS: dict[str, Biller] = {
    b.service_id: b
    for b in [
        Biller("ikeja-electric", "Ikeja Electric (IKEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("eko-electric", "Eko Electric (EKEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("abuja-electric", "Abuja Electric (AEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("ibadan-electric", "Ibadan Electric (IBEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("enugu-electric", "Enugu Electric (EEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("portharcourt-electric", "Port Harcourt Electric (PHED)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("kano-electric", "Kano Electric (KEDCO)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("kaduna-electric", "Kaduna Electric (KAEDCO)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("jos-electric", "Jos Electric (JED)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("benin-electric", "Benin Electric (BEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("yola-electric", "Yola Electric (YEDC)", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
        Biller("aba-electric", "Aba Power", ELECTRICITY, _DISCO_VARIATIONS, "Meter number"),
    ]
}


def get_biller(service_id: str) -> Biller | None:
    return BILLERS.get(service_id)


def choices(category: str | None = None):
    return [(b.service_id, b.name) for b in BILLERS.values() if category in (None, b.category)]
