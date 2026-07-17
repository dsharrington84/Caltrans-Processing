from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS price_outlier_analysis
        """)

        con.execute("""
        CREATE TABLE price_outlier_analysis AS

        SELECT

            h.contract_number,

            h.contractor_id,

            h.bidder_name,

            h.item_code,

            h.item_description,

            h.unit,

            h.unit_price,

            h.bid_rank,


            m.p25,

            m.p75,

            ROUND(
                m.p75 - m.p25,
                2
            ) AS iqr,


            CASE

                WHEN h.unit_price <
                    m.p25 -
                    1.5 * (m.p75 - m.p25)

                THEN 'LOW_OUTLIER'


                WHEN h.unit_price >
                    m.p75 +
                    1.5 * (m.p75 - m.p25)

                THEN 'HIGH_OUTLIER'


                ELSE 'NORMAL'

            END AS outlier_flag


        FROM historical_bid_prices h

        JOIN item_market_bands_v2 m

            ON h.item_code = m.item_code

            AND h.item_description = m.item_description

       	AND h.unit = m.unit

        """)

    print("Price outlier analysis created.")


if __name__ == "__main__":
    main()
