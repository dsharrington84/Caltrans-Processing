from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_performance_summary_v2
        """)

        con.execute("""
        CREATE TABLE contractor_performance_summary_v2 AS

        SELECT
            c.contractor_id,
            c.canonical_name AS contractor_name,

            COUNT(h.contract_number) AS total_bids,

            SUM(
                CASE
                    WHEN h.won_flag = TRUE
                    THEN 1
                    ELSE 0
                END
            ) AS apparent_wins,

            ROUND(
                SUM(
                    CASE
                        WHEN h.won_flag = TRUE
                        THEN 1
                        ELSE 0
                    END
                ) * 100.0
                / COUNT(h.contract_number),
                2
            ) AS win_rate_pct,

            ROUND(
                AVG(h.bid_rank),
                2
            ) AS avg_bid_rank,

            ROUND(
                AVG(h.bid_amount),
                2
            ) AS avg_bid_amount,

            MIN(h.bid_rank) AS best_bid_rank

        FROM contractors_v2 c

        JOIN contractor_bid_history_v2 h
            ON c.contractor_id = h.contractor_id

        GROUP BY
            c.contractor_id,
            c.canonical_name

        """)

    print("Contractor performance summary v2 created.")


if __name__ == "__main__":
    main()
