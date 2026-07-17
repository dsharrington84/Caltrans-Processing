from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_competitor_matrix_v2
        """)

        con.execute("""
        CREATE TABLE contractor_competitor_matrix_v2 AS

        SELECT
            a.contractor_id AS contractor_id,
            b.contractor_id AS competitor_id,

            COUNT(*) AS times_competed,

            ROUND(
                AVG(
                    ABS(a.bid_rank - b.bid_rank)
                ),
                2
            ) AS avg_rank_difference

        FROM contractor_bid_history_v2 a

        JOIN contractor_bid_history_v2 b
            ON a.contract_number = b.contract_number
            AND a.contractor_id <> b.contractor_id

        GROUP BY
            a.contractor_id,
            b.contractor_id

        """)

    print("Competitor matrix v2 created.")


if __name__ == "__main__":
    main()
