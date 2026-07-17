from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS district_item_market_bands
        """)


        con.execute("""
        CREATE TABLE district_item_market_bands AS


        WITH district_prices AS (

            SELECT

                r.district,

                h.item_code,

                h.item_description,

                h.unit,


                COUNT(*) AS observations,


                COUNT(DISTINCT h.contractor_id)
                    AS contractor_count,


                MEDIAN(h.unit_price)
                    AS district_median_price


            FROM historical_bid_prices h


            JOIN historical_contract_reference_v2 r

                ON h.contract_number =
                   r.contract_number


            WHERE h.unit_price IS NOT NULL


            GROUP BY

                r.district,

                h.item_code,

                h.item_description,

                h.unit

        )


        SELECT

            d.district,

            d.item_code,

            d.item_description,

            d.unit,


            d.observations,

            d.contractor_count,


            ROUND(
                d.district_median_price,
                2
            ) AS district_median_price,


            ROUND(
                m.all_bid_median,
                2
            ) AS statewide_median_price,


            ROUND(

                (
                    d.district_median_price
                    -
                    m.all_bid_median
                )

                /

                NULLIF(
                    m.all_bid_median,
                    0
                )

                * 100,

                2

            ) AS adjustment_pct


        FROM district_prices d


        JOIN item_market_bands_v2 m

            ON d.item_code = m.item_code

            AND d.item_description =
                m.item_description

            AND d.unit = m.unit

        """)


    print("District item market bands created.")


if __name__ == "__main__":
    main()
