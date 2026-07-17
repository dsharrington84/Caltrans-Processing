from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS bid_spread_analysis
        """)


        con.execute("""
        CREATE TABLE bid_spread_analysis AS


        WITH ranked_bids AS (

            SELECT

                contract_number,

                bid_rank,

                roster_bid_amount,


                ROW_NUMBER() OVER (

                    PARTITION BY contract_number

                    ORDER BY bid_rank

                ) AS rn


            FROM bidder_staging


            WHERE bid_rank IS NOT NULL

        ),


        summary AS (

            SELECT

                contract_number,


                COUNT(*) AS bidder_count,


                MAX(
                    CASE
                        WHEN rn = 1
                        THEN roster_bid_amount
                    END
                ) AS low_bid,


                MAX(
                    CASE
                        WHEN rn = 2
                        THEN roster_bid_amount
                    END
                ) AS second_bid,


                AVG(roster_bid_amount)
                    AS average_bid


            FROM ranked_bids


            GROUP BY contract_number

        )


        SELECT


            contract_number,

            bidder_count,

            low_bid,

            second_bid,

            average_bid,


            ROUND(

                (
                    second_bid
                    -
                    low_bid
                )

                /

                NULLIF(
                    low_bid,
                    0
                )

                * 100,

                2

            ) AS low_to_second_pct,


            ROUND(

                (
                    average_bid
                    -
                    low_bid
                )

                /

                NULLIF(
                    low_bid,
                    0
                )

                * 100,

                2

            ) AS low_to_average_pct,


            CASE

                WHEN

                (
                    second_bid
                    -
                    low_bid
                )
                /
                NULLIF(
                    low_bid,
                    0
                )
                * 100 < 5

                THEN 'VERY_TIGHT'


                WHEN

                (
                    second_bid
                    -
                    low_bid
                )
                /
                NULLIF(
                    low_bid,
                    0
                )
                * 100 < 15

                THEN 'TIGHT'


                WHEN

                (
                    second_bid
                    -
                    low_bid
                )
                /
                NULLIF(
                    low_bid,
                    0
                )
                * 100 < 30

                THEN 'NORMAL'


                ELSE 'WIDE'


            END AS spread_class


        FROM summary

        """)


    print("Bid spread analysis created.")


if __name__ == "__main__":
    main()
