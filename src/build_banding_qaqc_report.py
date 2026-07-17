from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS banding_qaqc_report
        """)


        con.execute("""
        CREATE TABLE banding_qaqc_report AS


        SELECT

            p.item_code,

            p.item_description,

            p.unit,


            p.weighted_market_price,


            d.market_depth_score,


            t.trend_signal,

            t.trend_reliability,


            c.cost_impact_class,


            CASE

                WHEN
                    d.market_depth_score >= 75

                    AND

                    t.trend_reliability = 'HIGH'

                    AND

                    c.cost_impact_class IN
                    ('HIGH','MEDIUM')

                THEN 'GREEN'


                WHEN
                    d.market_depth_score >= 50

                THEN 'YELLOW'


                ELSE 'RED'


            END AS qaqc_status,


            CASE

                WHEN
                    d.market_depth_score >= 75

                    AND
                    t.trend_reliability = 'HIGH'

                THEN 'AUTO_APPROVE'


                WHEN
                    d.market_depth_score >= 50

                THEN 'ESTIMATOR_REVIEW'


                ELSE 'MANUAL_REVIEW'


            END AS recommendation


        FROM item_pricing_bands_final p


        LEFT JOIN item_market_depth_score d

            ON p.item_code = d.item_code

            AND p.item_description =
                d.item_description

            AND p.unit = d.unit


        LEFT JOIN item_market_trend_reliability t

            ON p.item_code = t.item_code

            AND p.item_description =
                t.item_description

            AND p.unit = t.unit


        LEFT JOIN item_cost_impact_band c

            ON p.item_code = c.item_code

            AND p.item_description =
                c.item_description

            AND p.unit = c.unit

        """)


    print("Banding QAQC report created.")


if __name__ == "__main__":
    main()
