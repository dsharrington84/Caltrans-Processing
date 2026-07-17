from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_bands_v2
        """)

        con.execute("""
        CREATE TABLE item_market_bands_v2 AS

        SELECT

            h.item_code,
            h.item_description,
            h.unit,

            COUNT(*) AS observations,

            COUNT(DISTINCT h.contractor_id)
                AS contractor_count,

            COUNT(DISTINCT h.contract_number)
                AS contract_count,


            ROUND(
                AVG(h.unit_price),
                2
            ) AS all_bid_average,


            ROUND(
                MEDIAN(h.unit_price),
                2
            ) AS all_bid_median,


            ROUND(
                MEDIAN(
                    CASE
                        WHEN h.bid_rank = 1
                        THEN h.unit_price
                    END
                ),
                2
            ) AS low_bid_median,


            ROUND(
                MEDIAN(
                    CASE
                        WHEN h.bid_rank <= 3
                        THEN h.unit_price
                    END
                ),
                2
            ) AS top3_median,


            ROUND(
                QUANTILE_CONT(
                    h.unit_price,
                    0.25
                ),
                2
            ) AS p25,


            ROUND(
                QUANTILE_CONT(
                    h.unit_price,
                    0.75
                ),
                2
            ) AS p75,


            ROUND(
                AVG(w.pct_of_contract),
                4
            ) AS avg_contract_weight,


            CASE

                WHEN COUNT(*) >= 100
                THEN 'HIGH'

                WHEN COUNT(*) >= 25
                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS confidence_level


        FROM historical_bid_prices h


        LEFT JOIN contract_item_cost_weight w

            ON h.contract_number = w.contract_number

            AND h.contractor_id = w.contractor_id

            AND h.item_code = w.item_code


        WHERE h.unit_price IS NOT NULL


        GROUP BY

            h.item_code,
            h.item_description,
            h.unit

        """)

    print("Item market bands v2 created.")


if __name__ == "__main__":
    main()
