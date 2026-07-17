from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_bid_history
        """)

        con.execute("""
        CREATE TABLE contractor_bid_history (
            contractor_id VARCHAR,
            contract_number VARCHAR,
            bid_rank INTEGER,
            bid_amount DECIMAL(18,2),
            award_status VARCHAR,
            won_flag BOOLEAN
        )
        """)

        con.execute("""
        INSERT INTO contractor_bid_history
        SELECT
            c.contractor_id,
            b.contract_number,
            b.bid_rank,
            b.roster_bid_amount,
            b.award_status,
            CASE
                WHEN b.bid_rank = 1
                THEN TRUE
                ELSE FALSE
            END
        FROM bidder_staging b
        JOIN contractors c
            ON b.bidder_name = c.canonical_name
        """)

    print("Contractor bid history created.")


if __name__ == "__main__":
    main()
