from gdis_loader import __version__
from gdis_loader.gui.app import main


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_gui_smoke_test_does_not_start_event_loop() -> None:
    assert main(["--smoke-test"]) == 0
