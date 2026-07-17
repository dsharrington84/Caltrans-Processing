from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_competitor_summary_v2
        """)

        con.execute("""
        CREATE TABLE contractor_competitor_summary_v2 AS

        SELECT
            LEAST(contractor_id, competitor_id) AS contractor_a,
            GREATEST(contractor_id, competitor_id) AS contractor_b,

            COUNT(*) AS times_competed,

            ROUND(
                AVG(avg_rank_difference),
                2
            ) AS avg_rank_difference,

            ROUND(
                COUNT(*) * AVG(avg_rank_difference),
                2
            ) AS competitive_intensity

        FROM contractor_competitor_matrix_v2

        GROUP BY
            LEAST(contractor_id, competitor_id),
            GREATEST(contractor_id, competitor_id)

        """)

    print("Competitor summary v2 created.")


if __name__ == "__main__":
    main()
