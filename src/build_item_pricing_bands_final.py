from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_pricing_bands_final
        """)


        con.execute("""
        CREATE TABLE item_pricing_bands_final AS


        SELECT

            w.item_code,

            w.item_description,

            w.unit,


            w.observations,


            w.contractor_count,

            w.contract_count,


            w.weighted_market_price,


            b.winning_market_price,

            b.competitive_market_price,

            b.full_market_price,


            t.trend_signal,

            t.change_pct,

            t.trend_factor,


            d.market_depth_score,


            c.cost_impact_class,


            CASE

                WHEN d.market_depth_score >= 75

                THEN 'HIGH'

                WHEN d.market_depth_score >= 50

                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS market_confidence,


            CASE

                WHEN d.market_depth_score >= 75

                THEN 'USE_MARKET'

                WHEN d.market_depth_score >= 50

                THEN 'BLEND_MARKET_CONTRACTOR'

                ELSE 'REVIEW_REQUIRED'

            END AS pricing_strategy


        FROM item_weighted_market_price w


        LEFT JOIN winning_vs_market_bands b

            ON w.item_code = b.item_code

            AND w.item_description =
                b.item_description

            AND w.unit = b.unit


        LEFT JOIN item_market_trend_reliability t

            ON w.item_code = t.item_code

            AND w.item_description =
                t.item_description

            AND w.unit = t.unit


        LEFT JOIN item_market_depth_score d

            ON w.item_code = d.item_code

            AND w.item_description =
                d.item_description

            AND w.unit = d.unit


        LEFT JOIN item_cost_impact_band c

            ON w.item_code = c.item_code

            AND w.item_description =
                c.item_description

            AND w.unit = c.unit

        """)


    print("Final item pricing bands created.")


if __name__ == "__main__":
    main()
