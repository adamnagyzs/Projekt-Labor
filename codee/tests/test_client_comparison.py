import sys
from uuid import uuid4
import pytest
from PySide6.QtWidgets import QApplication

from leltariv_client.api import FakeApiClient
from leltariv_client.pages.comparison import ComparisonPage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_comparison_page_fake_api(qapp):
    api = FakeApiClient("http://localhost:8000")
    token = "fake_token_123"

    page = ComparisonPage(api, token)
    
    #Adatok betöltődése
    periods = api.get_periods(token)
    zones = api.get_zones(token)

    assert len(periods) > 0
    assert len(zones) > 0

    #get_comparison hívás tesztelése
    comp = api.get_comparison(token, periods[0].id, "262")
    assert comp is not None
    assert comp.summary.expected_assets >= 0
    assert len(comp.rows) > 0

    #asset history lekérdezés tesztelése
    asset_id = comp.rows[0].asset.id
    history = api.get_asset_history(token, asset_id)
    assert isinstance(history, list)
    assert len(history) > 0