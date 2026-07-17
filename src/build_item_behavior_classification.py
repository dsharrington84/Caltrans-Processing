from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_behavior_classification
        """)

        con.execute("""
        CREATE TABLE item_behavior_classification AS

        SELECT

            m.item_code,

            m.item_description,

            m.unit,

            m.observations,

            m.avg_contract_weight,

            m.confidence_level,


            CASE

                WHEN m.unit IN
                ('LF','SF','CY','TON','EA','HR','WDAY')
                THEN 'UNIT_PRICE'


                WHEN m.unit = 'LS'
                AND m.avg_contract_weight >= 25
                THEN 'DOMINANT_LS'


                WHEN m.unit = 'LS'
                THEN 'LUMP_SUM'


                ELSE 'SPECIALTY'


            END AS item_behavior_class


        FROM item_market_bands_v2 m

        """)

    print("Item behavior classification created.")


if __name__ == "__main__":
    main()
