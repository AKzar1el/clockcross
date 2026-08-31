from types import SimpleNamespace

import pytest

from clockcross.runtime import build_competition_runtime


def settings(*, role: str, allow_dev_order: bool):
    return SimpleNamespace(
        clockcross_account_role=role,
        clockcross_allow_dev_order=allow_dev_order,
    )


def test_competition_runtime_rejects_development_account_before_building_dependencies():
    with pytest.raises(RuntimeError, match="competition account role"):
        build_competition_runtime(settings(role="development", allow_dev_order=False))


def test_competition_runtime_rejects_development_order_flag_before_building_dependencies():
    with pytest.raises(RuntimeError, match="development-order flag"):
        build_competition_runtime(settings(role="competition", allow_dev_order=True))
