from leltariv_domain.categories import DEFAULT_TYPES, suggest_type
from leltariv_domain.normalization import normalize_text


def type_of(name: str) -> str:
    return suggest_type(normalize_text(name))


def test_real_source_names() -> None:
    # valódi megnevezések a két forrásállományból, az elgépeléssel együtt
    assert type_of("TÁRGYALŐSZÉK") == "Bútor"
    assert type_of("Forgószék") == "Bútor"
    assert type_of("DIGITÁLIS OSZCILLOSZKÓP") == "Mérőműszer"
    assert type_of("Táblagép") == "Számítógép"
    assert type_of("Egér (optikai)") == "Perifária"


def test_narrow_stem_wins() -> None:
    assert type_of("ÍRÓASZTAL (KLAVIATÚRA)") == "Bútor"
    assert type_of("műszerasztal") == "Bútor"
    assert type_of("Szünetmentes tápegység") == "Egyéb"


def test_every_suggestion_is_a_default_type() -> None:
    names = ("Szék", "Monitor", "Valami egészen más", "", "xbox one", "PT100 hőmérő")
    assert all(type_of(name) in DEFAULT_TYPES for name in names)
    assert type_of("Valami egészen más") == "Egyéb"
