from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_competitor_summary
        """)

        con.execute("""
        CREATE TABLE contractor_competitor_summary AS

        SELECT
            LEAST(contractor_id, competitor_id) AS contractor_a,
            GREATEST(contractor_id, competitor_id) AS contractor_b,

            COUNT(*) AS times_competed,

            ROUND(
                COALESCE(AVG(avg_rank_difference), 0),
                2
            ) AS avg_rank_difference,

            ROUND(
                COUNT(*) * COALESCE(AVG(avg_rank_difference), 0),
                2
            ) AS competitive_intensity

        FROM contractor_competitor_matrix

        GROUP BY
            LEAST(contractor_id, competitor_id),
            GREATEST(contractor_id, competitor_id)

        """)

    print("Competitor summary created.")


if __name__ == "__main__":
    main()
