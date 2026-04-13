import logging

import requests
from langchain_core.tools import tool

log = logging.getLogger(__name__)


@tool
def get_stock_info(ticker: str) -> str:
    """Get current stock price and daily percentage change for a stock ticker symbol.
    ticker: stock symbol like AAPL, GOOGL, TSLA, MSFT, APL, etc.
    Returns current price, previous close, and % change for today."""
    try:
        ticker = ticker.upper().strip()
        log.debug("Fetching stock data for %s", ticker)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        result = data.get("chart", {}).get("result")
        if not result:
            error = data.get("chart", {}).get("error", {})
            return f"Could not find stock data for '{ticker}': {error.get('description', 'Unknown error')}"

        meta = result[0].get("meta", {})
        current_price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        currency = meta.get("currency", "USD")
        exchange = meta.get("exchangeName", "")
        name = meta.get("shortName", ticker)

        if current_price is None:
            return f"Could not retrieve price data for {ticker}."

        if prev_close:
            pct_change = (current_price - prev_close) / prev_close * 100
            direction = "up" if pct_change > 0 else "down"
            change_str = f"\nDaily Change: {direction} {abs(pct_change):.2f}%"
        else:
            pct_change = None
            change_str = ""

        return (
            f"{name} ({ticker}) on {exchange}\n"
            f"Current Price: {currency} {current_price:.2f}\n"
            f"Previous Close: {currency} {prev_close:.2f}"
            f"{change_str}"
        )
    except requests.exceptions.RequestException as e:
        log.warning("Network error fetching stock data for %s: %s", ticker, e)
        return f"Network error fetching stock data for {ticker}: {e}"
    except Exception as e:
        log.exception("Unexpected error fetching stock data for %s", ticker)
        return f"Error fetching stock data for {ticker}: {e}"
