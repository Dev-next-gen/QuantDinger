from datetime import datetime, timedelta

from app.data_sources import us_stock
from app.data_sources.us_stock import USStockDataSource


class _EmptyChartResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"chart": {"result": []}}


def test_yahoo_chart_intraday_request_does_not_extend_end_date(monkeypatch):
    captured = {}

    def fake_get(_url, **kwargs):
        captured.update(kwargs["params"])
        return _EmptyChartResponse()

    monkeypatch.setattr(us_stock.requests, "get", fake_get)
    source = USStockDataSource.__new__(USStockDataSource)
    start = datetime(2026, 9, 8, 13, 30)
    end = datetime(2026, 9, 14, 15, 30)

    source._fetch_yahoo_chart("NVDA", "1m", start, end, 500)

    assert captured["period1"] == int(start.timestamp())
    assert captured["period2"] == int(end.timestamp())


def test_yahoo_chart_daily_request_keeps_inclusive_end_date(monkeypatch):
    captured = {}

    def fake_get(_url, **kwargs):
        captured.update(kwargs["params"])
        return _EmptyChartResponse()

    monkeypatch.setattr(us_stock.requests, "get", fake_get)
    source = USStockDataSource.__new__(USStockDataSource)
    start = datetime(2026, 9, 8)
    end = datetime(2026, 9, 14)

    source._fetch_yahoo_chart("NVDA", "1d", start, end, 500)

    assert captured["period2"] == int((end + timedelta(days=1)).timestamp())


def test_yahoo_chart_splits_long_one_minute_windows(monkeypatch):
    requests = []

    def fake_get(_url, **kwargs):
        requests.append(dict(kwargs["params"]))
        return _EmptyChartResponse()

    monkeypatch.setattr(us_stock.requests, "get", fake_get)
    source = USStockDataSource.__new__(USStockDataSource)
    start = datetime(2026, 9, 1, 13, 30)
    end = datetime(2026, 9, 14, 15, 30)

    source._fetch_yahoo_chart("NVDA", "1m", start, end, 5000)

    assert len(requests) == 2
    assert requests[0]["period1"] == int(start.timestamp())
    assert requests[0]["period2"] == int((start + timedelta(days=7)).timestamp())
    assert requests[1]["period1"] == int((start + timedelta(days=7)).timestamp())
    assert requests[1]["period2"] == int(end.timestamp())


def test_yfinance_intraday_request_preserves_datetime_bounds(monkeypatch):
    captured = {}

    class _Ticker:
        def history(self, **kwargs):
            captured.update(kwargs)
            return None

    monkeypatch.setattr(us_stock.yf, "Ticker", lambda _symbol: _Ticker())
    source = USStockDataSource.__new__(USStockDataSource)
    start = datetime(2026, 9, 8, 13, 30)
    end = datetime(2026, 9, 14, 15, 30)

    source._fetch_yfinance("NVDA", "1m", start, end)

    assert captured["start"] == start
    assert captured["end"] == end


class _MinuteChartResponse:
    def __init__(self, start_ts, count):
        self._timestamps = [start_ts + 60 * i for i in range(count)]

    def raise_for_status(self):
        return None

    def json(self):
        n = len(self._timestamps)
        return {"chart": {"result": [{
            "timestamp": self._timestamps,
            "indicators": {"quote": [{
                "open": [100.0 + i for i in range(n)],
                "high": [101.0 + i for i in range(n)],
                "low": [99.0 + i for i in range(n)],
                "close": [100.5 + i for i in range(n)],
                "volume": [10] * n,
            }]},
        }]}}


def test_three_minute_klines_from_yahoo_chart_are_merged(monkeypatch):
    session_open = int(datetime(2026, 9, 14, 13, 30).timestamp())
    captured = {}

    def fake_get(_url, **kwargs):
        captured.update(kwargs["params"])
        return _MinuteChartResponse(session_open, 6)

    monkeypatch.setattr(us_stock.requests, "get", fake_get)
    source = USStockDataSource.__new__(USStockDataSource)

    bars = source.get_kline("NVDA", "3m", 2, before_time=session_open + 3600)

    assert captured["interval"] == "1m"
    assert [bar["time"] for bar in bars] == [session_open, session_open + 180]
    assert bars[0]["open"] == 100.0
    assert bars[0]["high"] == 103.0
    assert bars[0]["low"] == 99.0
    assert bars[0]["close"] == 102.5
    assert bars[0]["volume"] == 30
    assert bars[1]["close"] == 105.5
