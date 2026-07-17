from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS project_size_bands
        """)


        con.execute("""
        CREATE TABLE project_size_bands AS


        SELECT

            contract_number,

            total_bid_amount AS project_value,


            CASE


                WHEN total_bid_amount < 500000

                THEN 'VERY_SMALL'


                WHEN total_bid_amount < 5000000

                THEN 'SMALL'


                WHEN total_bid_amount < 25000000

                THEN 'MEDIUM'


                WHEN total_bid_amount < 100000000

                THEN 'LARGE'


                ELSE 'MEGA'


            END AS project_size_band


        FROM contract_bid_totals


        WHERE bid_rank = 1

        """)


    print("Project size bands created.")


if __name__ == "__main__":
    main()
