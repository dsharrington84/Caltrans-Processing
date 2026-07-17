from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_mapping_conflicts
        """)

        con.execute("""
        CREATE TABLE contractor_mapping_conflicts AS

        SELECT

            bidder_id,

            STRING_AGG(
                DISTINCT bidder_name,
                ' | '
            ) AS bidder_names,

            STRING_AGG(
                DISTINCT contractor_id,
                ' | '
            ) AS contractor_ids,

            COUNT(*) AS records

        FROM contractor_bidder_mapping

        GROUP BY bidder_id

        HAVING COUNT(DISTINCT contractor_id) > 1

        """)

    print("Contractor mapping conflicts created.")


if __name__ == "__main__":
    main()
