from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_cost_impact_band
        """)


        con.execute("""
        CREATE TABLE item_cost_impact_band AS


        WITH item_weights AS (

            SELECT

                item_code,

                AVG(pct_of_contract)
                    AS avg_contract_weight,


                COUNT(*) AS observations


            FROM contract_item_cost_weight


            GROUP BY item_code

        )


        SELECT

            w.item_code,

            m.item_description,

            m.unit,


            w.observations,


            ROUND(
                w.avg_contract_weight,
                4
            ) AS avg_contract_weight,


            CASE

                WHEN w.avg_contract_weight >= 5

                THEN 'HIGH'


                WHEN w.avg_contract_weight >= 1

                THEN 'MEDIUM'


                ELSE 'LOW'


            END AS cost_impact_class


        FROM item_weights w


        LEFT JOIN item_market_bands_v2 m

            ON w.item_code = m.item_code

        """)


    print("Item cost impact band created.")


if __name__ == "__main__":
    main()
