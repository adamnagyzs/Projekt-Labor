"""Eszköztípus-javaslat a megnevezésből.

A forrásban nincs eszköztípus, csak szabad szöveges megnevezés. Betöltéskor ebből javaslunk
kategóriát; a javaslat felülbírálható, és új típus a felületről is felvehető, tehát a típuslista
az adatbázisban él. Itt csak a kezdő besorolás kulcsszavai vannak.
"""

DEFAULT_TYPES: tuple[str, ...] = (
    "Bútor",
    "Számítógép",
    "Monitor",
    "Perifária",
    "Nyomtató",
    "Mérőműszer",
    "Hálózati eszköz",
    "Audiovizuális eszköz",
    "Oktatási eszköz",
    "Egyéb",
)

#: (szótő, típus); az első egyező nyer, ezért a szűkebb tő áll elöl: a `tablagep` a `tabla`
#: előtt, az `asztal` a `klaviatura` és a `muszer` előtt (`iroasztal (klaviatura)`,
#: `muszerasztal`). Az első két tő kizár: a szünetmentes táp és a hűtőszekrény ne kerüljön a
#: Mérőműszer, illetve a Bútor közé. A tövek ékezet nélküliek és kisbetűsek, mert a
#: `name_normalized` is ilyen.
KEYWORDS: tuple[tuple[str, str], ...] = (
    ("szunetmentes", "Egyéb"),
    ("huto", "Egyéb"),
    ("monitor", "Monitor"),
    ("nyomtato", "Nyomtató"),
    ("tablagep", "Számítógép"),
    ("szamitogep", "Számítógép"),
    ("laptop", "Számítógép"),
    ("notebook", "Számítógép"),
    ("hdd", "Számítógép"),
    ("ssd", "Számítógép"),
    ("sata", "Számítógép"),
    ("asztal", "Bútor"),
    ("keyboard", "Perifária"),
    ("billentyuzet", "Perifária"),
    ("klaviatura", "Perifária"),
    ("mouse", "Perifária"),
    ("mause", "Perifária"),
    ("eger", "Perifária"),
    ("dokkolo", "Perifária"),
    ("oszcilloszkop", "Mérőműszer"),
    ("multimeter", "Mérőműszer"),
    ("tapegyseg", "Mérőműszer"),
    ("generator", "Mérőműszer"),
    ("homero", "Mérőműszer"),
    ("pulzusmero", "Mérőműszer"),
    ("muszer", "Mérőműszer"),
    ("switch", "Hálózati eszköz"),
    ("router", "Hálózati eszköz"),
    ("antenna", "Hálózati eszköz"),
    ("telefon", "Hálózati eszköz"),
    ("projektor", "Audiovizuális eszköz"),
    ("vetitovaszon", "Audiovizuális eszköz"),
    ("kamera", "Audiovizuális eszköz"),
    ("szenzor", "Oktatási eszköz"),
    ("mindstorms", "Oktatási eszköz"),
    ("robot", "Oktatási eszköz"),
    ("adatgyujto", "Oktatási eszköz"),
    ("oktatasi", "Oktatási eszköz"),
    ("szek", "Bútor"),
    ("szekreny", "Bútor"),
    ("polc", "Bútor"),
    ("fotel", "Bútor"),
    ("kontener", "Bútor"),
    ("fogas", "Bútor"),
    ("tabla", "Bútor"),
    ("karfa", "Bútor"),
    ("allvany", "Bútor"),
)


def suggest_type(name_normalized: str) -> str:
    """A `DEFAULT_TYPES` egyike; ha egyik kulcsszó sem illik, „Egyéb"."""
    for stem, asset_type in KEYWORDS:
        if stem in name_normalized:
            return asset_type
    return "Egyéb"
