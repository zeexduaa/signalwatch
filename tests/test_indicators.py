import pytest

from signalwatch.indicators import ema, moving_average, pct_change, rsi, sma


def test_sma():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert sma([7], 1) == [7.0]
    assert sma([1, 2], 3) == [None, None]


def test_ema_is_seeded_with_sma_and_weights_recent_prices():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)  # SMA of 1, 2, 3
    assert out[3] == pytest.approx(3.0)  # 4*0.5 + 2*0.5
    assert out[4] == pytest.approx(4.0)
    assert ema([1, 2], 5) == [None, None]


def test_rsi_matches_the_textbook_example():
    # Wilder's classic 14-period example (as used in StockCharts' RSI explainer).
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    ]
    out = rsi(closes, 14)
    assert out[:14] == [None] * 14
    assert out[14] == pytest.approx(70.46, abs=0.05)
    assert out[15] == pytest.approx(66.25, abs=0.05)
    assert out[19] == pytest.approx(57.92, abs=0.1)


def test_rsi_edges():
    assert rsi([1, 2, 3, 4], 3)[-1] == 100.0  # only gains
    assert rsi([4, 3, 2, 1], 3)[-1] == pytest.approx(0.0)  # only losses
    assert rsi([5, 5, 5, 5], 3)[-1] == 50.0  # flat
    assert rsi([1, 2, 3], 3) == [None, None, None]


def test_pct_change():
    assert pct_change([100, 110, 99], 1) == [None, pytest.approx(10.0), pytest.approx(-10.0)]
    assert pct_change([100, 110, 99], 2)[2] == pytest.approx(-1.0)
    assert pct_change([0, 5], 1) == [None, None]  # no divide by zero


@pytest.mark.parametrize("bad", ["sma", "sma:0", "wma:5", "ema:x", "", "sma:-3"])
def test_moving_average_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        moving_average(bad, [1.0, 2.0])


def test_moving_average_parses_specs():
    assert moving_average("SMA:2", [1, 3, 5]) == [None, 2.0, 4.0]
    assert moving_average(" ema:1 ", [1, 3]) == [1.0, 3.0]


@pytest.mark.parametrize("fn", [sma, ema, rsi, pct_change])
def test_bad_periods(fn):
    with pytest.raises(ValueError):
        fn([1, 2, 3], 0)
