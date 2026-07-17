from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_pricing_confidence_v4
        """)

        con.execute("""
        CREATE TABLE contractor_pricing_confidence_v4 AS

        WITH contractor_activity AS (

            SELECT

                contractor_id,

                COUNT(DISTINCT contract_number)
                    AS total_contracts,

                COUNT(*)
                    AS total_bids

            FROM contractor_bid_history_v3

            GROUP BY contractor_id

        )


        SELECT

            p.contractor_id,

            p.item_code,

            p.item_description,

            p.unit,


            p.bid_count AS item_observations,


            a.total_contracts,

            a.total_bids,


            p.median_unit_price
                AS contractor_median_price,


            ROUND(
                (
                    p.max_unit_price
                    -
                    p.min_unit_price
                )
                /
                NULLIF(
                    p.median_unit_price,
                    0
                )
                * 100,
                2
            ) AS price_spread_pct,


            ROUND(

                (
                    CASE
                        WHEN p.bid_count >= 25
                        THEN 40

                        WHEN p.bid_count >= 10
                        THEN 25

                        ELSE 10
                    END

                    +

                    CASE
                        WHEN a.total_bids >= 30
                        THEN 30

                        WHEN a.total_bids >= 10
                        THEN 20

                        ELSE 10
                    END

                    +

                    CASE
                        WHEN
                        (
                            (
                            p.max_unit_price
                            -
                            p.min_unit_price
                            )
                            /
                            NULLIF(
                                p.median_unit_price,
                                0
                            )
                        ) < 1

                        THEN 30

                        ELSE 15

                    END

                ),

                2

            ) AS confidence_score,


            CASE

                WHEN

                (
                    CASE
                        WHEN p.bid_count >= 25 THEN 40
                        WHEN p.bid_count >= 10 THEN 25
                        ELSE 10
                    END

                    +

                    CASE
                        WHEN a.total_bids >= 30 THEN 30
                        WHEN a.total_bids >= 10 THEN 20
                        ELSE 10
                    END

                    +

                    CASE
                        WHEN
                        (
                            (
                            p.max_unit_price
                            -
                            p.min_unit_price
                            )
                            /
                            NULLIF(
                                p.median_unit_price,
                                0
                            )
                        ) < 1

                        THEN 30

                        ELSE 15

                    END

                ) >= 75

                THEN 'HIGH'


                WHEN

                (
                    CASE
                        WHEN p.bid_count >= 25 THEN 40
                        WHEN p.bid_count >= 10 THEN 25
                        ELSE 10
                    END

                    +

                    CASE
                        WHEN a.total_bids >= 30 THEN 30
                        WHEN a.total_bids >= 10 THEN 20
                        ELSE 10
                    END

                    +

                    CASE
                        WHEN
                        (
                            (
                            p.max_unit_price
                            -
                            p.min_unit_price
                            )
                            /
                            NULLIF(
                                p.median_unit_price,
                                0
                            )
                        ) < 1

                        THEN 30

                        ELSE 15

                    END

                ) >= 50

                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS confidence_level


        FROM contractor_item_price_history_v3 p


        JOIN contractor_activity a

            ON p.contractor_id = a.contractor_id

        """)

    print("Contractor pricing confidence v4 created.")


if __name__ == "__main__":
    main()
