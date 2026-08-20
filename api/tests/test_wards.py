from hikage_navi.wards import TOKYO_23_WARD_CODES, OUTSIDE_MESSAGE


def test_twenty_three_ward_codes():
    assert len(TOKYO_23_WARD_CODES) == 23
    assert TOKYO_23_WARD_CODES[0] == "13101"
    assert TOKYO_23_WARD_CODES[-1] == "13123"
    assert "13113" in TOKYO_23_WARD_CODES  # 渋谷


def test_outside_message_mentions_23ku():
    assert "東京23区" in OUTSIDE_MESSAGE
