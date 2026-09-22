import pytest

from gdis_loader import __version__
from gdis_loader.gui.app import main


def test_version() -> None:
    assert __version__ == "0.1"


def test_gui_smoke_test_does_not_start_event_loop() -> None:
    assert main(["--smoke-test"]) == 0


def test_gui_smoke_test_checks_expected_version() -> None:
    assert main(["--smoke-test", "--expected-version", "0.1"]) == 0
    with pytest.raises(RuntimeError):
        main(["--smoke-test", "--expected-version", "9.9"])
