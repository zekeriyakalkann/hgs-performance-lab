"""Tüm test oturumu için süreç içi yalıtım koruması (bkz. isolation_guard.py).

Test dosyalarındaki mevcut ağ korumaları (`install_network_guard`, `refuse` fixture'ları) olduğu gibi çalışır; bu
koruma onların altında, son katmandır: hiçbir test, bu sürecin kendi açmadığı bir porta (ör. gerçek HGS2) bağlanamaz.
"""

import isolation_guard
import pytest


def pytest_configure(config):
    isolation_guard.install()


def pytest_unconfigure(config):
    isolation_guard.uninstall()


@pytest.fixture(autouse=True)
def isolation_violations():
    """Testin sırasında engellenen bağlantı girişimleri. Bilerek girişim deneyen test listeyi denetleyip boşaltmalıdır."""
    isolation_guard.violations.clear()
    yield isolation_guard.violations
    found = list(isolation_guard.violations)
    isolation_guard.violations.clear()
    if found:
        pytest.fail(f"Test süreci dışındaki hedefe bağlantı denendi (engellendi): {found!r}", pytrace=False)
