import logging


logging.basicConfig(level=logging.INFO)

# Removed top-level create_all to prevent crash on import in Cloud Run.


def _ensure_dependencies() -> list[str]:
    """Check optional crawler dependencies and return import errors."""
    missing: list[str] = []
    try:
        import yfinance  # noqa: F401
    except Exception:
        missing.append("yfinance")
    return missing

def fetch_us_etf_holdings(symbol: str):
    """Fetch top holdings for US ETFs via yfinance."""
    missing = _ensure_dependencies()
    if missing:
        logging.warning(f"Crawler optional dependency missing for yfinance flow: {', '.join(missing)}")
        return []

    import yfinance as yf

    ticker = yf.Ticker(symbol)
    try:
        holdings = ticker.funds_data.top_holdings
        if holdings is None or holdings.empty:
            logging.warning(f"No holdings found for {symbol} via yfinance.")
            return []

        results = []
        for index, row in holdings.iterrows():
            # row: name, weight (float)
            weight = float(row.get('Weight', 0))
            # Sometimes index is the symbol
            h_symbol = str(index) if index else row.get('Name')
            name = str(row.get('Name', h_symbol))

            if weight > 0:
                results.append({
                    "holding_symbol": h_symbol,
                    "holding_name": name,
                    "weight": weight,
                    "currency": "USD",
                    "country": "US",
                    "sector": "Other" # could be fetched individually
                })

        # Normalize weights if they don't add to 1
        total_weight = sum(r['weight'] for r in results)
        if total_weight > 0 and total_weight < 0.98:
            for r in results:
                r['weight'] /= total_weight

        return results
    except Exception as e:
        logging.error(f"Error fetching {symbol}: {e}")
        return []

def save_to_db(etf_symbol: str, etf_name: str, holdings: list):
    try:
        from sqlalchemy.orm import Session
        from ..database import SessionLocal, get_neo4j
        from ..db_models import HoldingDB
    except Exception:
        logging.error("Database dependency is missing; skipping DB/Neo4j persistence.")
        return

    db: Session = SessionLocal()
    
    # 1. Update RDB
    # Delete old holdings
    db.query(HoldingDB).filter(HoldingDB.product_symbol == etf_symbol).delete()
    
    for h in holdings:
        holding_record = HoldingDB(
            product_symbol=etf_symbol,
            holding_symbol=h["holding_symbol"],
            holding_name=h["holding_name"],
            weight=h["weight"],
            currency=h["currency"],
            country=h["country"],
            sector=h["sector"]
        )
        db.add(holding_record)
    
    db.commit()
    db.close()
    
    # 2. Update Neo4j
    session = get_neo4j()
    if session:
        try:
            # Merge ETF node
            session.run("""
                MERGE (e:ETF {symbol: $symbol})
                SET e.name = $name
            """, symbol=etf_symbol, name=etf_name)
            
            # Merge Holdings and relationships
            for h in holdings:
                session.run("""
                    MERGE (e:ETF {symbol: $etf_symbol})
                    MERGE (s:Stock {symbol: $holding_symbol})
                    SET s.name = $holding_name
                    MERGE (e)-[r:HOLDS]->(s)
                    SET r.weight = $weight
                """, etf_symbol=etf_symbol, holding_symbol=h["holding_symbol"],
                     holding_name=h["holding_name"], weight=h["weight"])
            logging.info(f"Successfully saved {etf_symbol} to RDB and Neo4j.")
        finally:
            session.close()

def run_crawler():
    # Crawl some major ETFs as an example for the live usable system
    targets = [
        ("SPY", "SPDR S&P 500 ETF Trust"),
        ("QQQ", "Invesco QQQ Trust"),
        ("SCHD", "Schwab US Dividend Equity")
    ]
    
    for symbol, name in targets:
        logging.info(f"Fetching {symbol}...")
        holdings = fetch_us_etf_holdings(symbol)
        if holdings:
            save_to_db(symbol, name, holdings)

if __name__ == "__main__":
    run_crawler()
