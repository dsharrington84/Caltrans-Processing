from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_bidder_mapping
        """)

        con.execute("""
        CREATE TABLE contractor_bidder_mapping AS

        SELECT DISTINCT

            b.bidder_id,
            b.bidder_name,
            a.contractor_id,

            1.0 AS confidence,

            'contractor_aliases_v2' AS source

        FROM bidder_staging b

        JOIN contractor_aliases_v2 a

            ON b.bidder_name = a.alias_name

        """)

    print("Contractor bidder mapping created.")


if __name__ == "__main__":
    main()
