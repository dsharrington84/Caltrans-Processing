from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_trends_v2
        """)


        con.execute("""
        CREATE TABLE item_market_trends_v2 AS


        WITH normalized_dates AS (

            SELECT

                contract_number,


                CASE

                    WHEN LENGTH(TRIM(bid_opening_date)) = 8

                    THEN

                        SUBSTR(
                            TRIM(bid_opening_date),
                            1,
                            6
                        )
                        ||
                        '20'
                        ||
                        SUBSTR(
                            TRIM(bid_opening_date),
                            7,
                            2
                        )


                    ELSE

                        TRIM(bid_opening_date)


                END AS normalized_date


            FROM historical_contract_reference

        ),


        contract_dates AS (

            SELECT

                contract_number,


                TRY_STRPTIME(
                    normalized_date,
                    '%m/%d/%Y'
                ) AS bid_date


            FROM normalized_dates

        )


        SELECT

            h.item_code,

            h.item_description,

            h.unit,


            YEAR(c.bid_date)
                AS bid_year,


            COUNT(*) AS observations,


            COUNT(DISTINCT h.contractor_id)
                AS contractor_count,


            COUNT(DISTINCT h.contract_number)
                AS contract_count,


            ROUND(
                MEDIAN(h.unit_price),
                2
            ) AS median_price,


            ROUND(
                AVG(h.unit_price),
                2
            ) AS average_price,


            MIN(h.unit_price)
                AS min_price,


            MAX(h.unit_price)
                AS max_price


        FROM historical_bid_prices h


        JOIN contract_dates c

            ON h.contract_number =
               c.contract_number


        WHERE h.unit_price IS NOT NULL

        AND c.bid_date IS NOT NULL


        GROUP BY

            h.item_code,

            h.item_description,

            h.unit,

            YEAR(c.bid_date)

        """)


    print("Item market trends v2 created.")


if __name__ == "__main__":
    main()
