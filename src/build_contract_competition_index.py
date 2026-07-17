from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contract_competition_index
        """)


        con.execute("""
        CREATE TABLE contract_competition_index AS


        SELECT

            b.contract_number,


            COUNT(DISTINCT b.bidder_id)
                AS bidder_count,


            COUNT(DISTINCT m.contractor_id)
                AS contractor_count,


            AVG(b.bid_rank)
                AS average_bid_rank,


            CASE

                WHEN COUNT(DISTINCT b.bidder_id) >= 8

                THEN 'HIGH'


                WHEN COUNT(DISTINCT b.bidder_id) >= 4

                THEN 'MEDIUM'


                ELSE 'LOW'


            END AS competition_class


        FROM bidder_staging b


        LEFT JOIN contractor_bidder_mapping m

            ON b.bidder_id = m.bidder_id


        GROUP BY

            b.contract_number

        """)


    print("Contract competition index created.")


if __name__ == "__main__":
    main()
