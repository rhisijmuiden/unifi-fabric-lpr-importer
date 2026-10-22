import pytest

from app.services.plates import credential_value, format_plate, group_name, plate_key


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("12bdf3", "12-BDF-3"),  # sidecode 7
        ("vz482k", "VZ-482-K"),  # sidecode 9
        ("1-KBB-00", "1-KBB-00"),  # sidecode 8
        ("ab 12 cd", "AB-12-CD"),  # sidecode 4
        ("bnz 123", "BNZ-123"),  # no Dutch sidecode: kept, in capitals
        ("  gg-x-99 ", "GG-X-99"),
    ],
)
def test_format_plate(raw, expected):
    assert format_plate(raw) == expected


def test_plate_key_and_credentials():
    assert plate_key("12-bdf-3") == "12BDF3"
    assert credential_value("12bdf3", "official") == "12-BDF-3"
    assert credential_value("12-BDF-3", "compact") == "12BDF3"


def test_group_name():
    assert group_name("Netwerktransport", "Wognum") == "Netwerktransport Wognum"
    assert group_name("Netwerktransport", "") == "Netwerktransport"
