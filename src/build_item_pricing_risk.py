from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_pricing_risk
        """)

        con.execute("""
        CREATE TABLE item_pricing_risk AS

        SELECT

            item_code,
            item_description,
            unit,

            observations,

            all_bid_median,

            p25,
            p75,

            ROUND(
                (
                    p75 - p25
                )
                /
                NULLIF(all_bid_median,0)
                * 100,
                2
            ) AS spread_pct,


            CASE

                WHEN
                    (
                    (p75 - p25)
                    /
                    NULLIF(all_bid_median,0)
                    * 100
                    ) > 100
                THEN 'HIGH'

                WHEN
                    (
                    (p75 - p25)
                    /
                    NULLIF(all_bid_median,0)
                    * 100
                    ) > 50
                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS volatility_class,


            confidence_level


        FROM item_market_bands_v2

        """)

    print("Item pricing risk created.")


if __name__ == "__main__":
    main()
