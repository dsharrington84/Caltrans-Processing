from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_intelligence_dashboard_v2
        """)

        con.execute("""
        CREATE TABLE contractor_intelligence_dashboard_v2 AS

        SELECT
            p.contractor_id,
            p.contractor_name,

            p.total_bids,
            p.apparent_wins,
            p.win_rate_pct,
            p.avg_bid_rank,
            p.avg_bid_amount,
            p.best_bid_rank,

            COUNT(DISTINCT
                CASE
                    WHEN c.contractor_a = p.contractor_id
                    THEN c.contractor_b
                    ELSE c.contractor_a
                END
            ) AS competitor_count,

            ROUND(
                AVG(c.competitive_intensity),
                2
            ) AS avg_competitive_intensity

        FROM contractor_performance_summary_v2 p

        LEFT JOIN contractor_competitor_summary_v2 c
            ON p.contractor_id = c.contractor_a
            OR p.contractor_id = c.contractor_b

        GROUP BY
            p.contractor_id,
            p.contractor_name,
            p.total_bids,
            p.apparent_wins,
            p.win_rate_pct,
            p.avg_bid_rank,
            p.avg_bid_amount,
            p.best_bid_rank

        """)

    print("Contractor intelligence dashboard v2 created.")


if __name__ == "__main__":
    main()
