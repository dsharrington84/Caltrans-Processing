from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS project_type_profile_v3
        """)


        con.execute("""
        CREATE TABLE project_type_profile_v3 AS


        WITH winning_items AS (

            SELECT DISTINCT

                contract_number,

                item_code,

                item_description,

                unit,

                extended_amount,

                total_bid_amount


            FROM contract_item_cost_weight


            WHERE bid_rank = 1

        ),


        normalized_items AS (

            SELECT

                contract_number,

                item_description,


                (
                    extended_amount
                    /
                    NULLIF(
                        total_bid_amount,
                        0
                    )
                )
                * 100 AS pct_weight


            FROM winning_items

        ),


        classified AS (

            SELECT

                contract_number,

                pct_weight,


                CASE


                    WHEN LOWER(item_description) LIKE '%asphalt%'
                    OR LOWER(item_description) LIKE '%pavement%'
                    OR LOWER(item_description) LIKE '%hot mix%'
                    OR LOWER(item_description) LIKE '%grind%'
                    OR LOWER(item_description) LIKE '%seal%'

                    THEN 'PAVING_REHAB'


                    WHEN LOWER(item_description) LIKE '%bridge%'
                    OR LOWER(item_description) LIKE '%structural%'
                    OR LOWER(item_description) LIKE '%concrete%'
                    OR LOWER(item_description) LIKE '%approach slab%'

                    THEN 'STRUCTURES_BRIDGE'


                    WHEN LOWER(item_description) LIKE '%signal%'
                    OR LOWER(item_description) LIKE '%lighting%'
                    OR LOWER(item_description) LIKE '%fiber%'
                    OR LOWER(item_description) LIKE '%electrical%'

                    THEN 'ELECTRICAL_ITS'


                    WHEN LOWER(item_description) LIKE '%pipe%'
                    OR LOWER(item_description) LIKE '%drain%'
                    OR LOWER(item_description) LIKE '%culvert%'
                    OR LOWER(item_description) LIKE '%storm%'

                    THEN 'DRAINAGE_STORMWATER'


                    WHEN LOWER(item_description) LIKE '%excavat%'
                    OR LOWER(item_description) LIKE '%grading%'
                    OR LOWER(item_description) LIKE '%embank%'
                    OR LOWER(item_description) LIKE '%borrow%'

                    THEN 'EARTHWORK_GRADING'


                    WHEN LOWER(item_description) LIKE '%sign%'
                    OR LOWER(item_description) LIKE '%barrier%'
                    OR LOWER(item_description) LIKE '%stripe%'
                    OR LOWER(item_description) LIKE '%traffic%'

                    THEN 'TRAFFIC_SAFETY'


                    WHEN LOWER(item_description) LIKE '%landscape%'
                    OR LOWER(item_description) LIKE '%erosion%'
                    OR LOWER(item_description) LIKE '%vegetation%'
                    OR LOWER(item_description) LIKE '%seeding%'

                    THEN 'ENVIRONMENTAL_LANDSCAPE'


                    ELSE 'OTHER'


                END AS project_family


            FROM normalized_items

        ),


        family_totals AS (

            SELECT

                contract_number,

                project_family,


                SUM(pct_weight) AS family_weight


            FROM classified


            GROUP BY

                contract_number,

                project_family

        ),


        ranked AS (

            SELECT

                contract_number,

                project_family,

                family_weight,


                ROW_NUMBER() OVER (

                    PARTITION BY contract_number

                    ORDER BY family_weight DESC

                ) AS rn


            FROM family_totals

        )


        SELECT

            contract_number,


            CASE

                WHEN family_weight < 40

                THEN 'MULTI_DISCIPLINE'


                ELSE project_family


            END AS project_type,


            ROUND(
                LEAST(
                    family_weight,
                    100
                ),
                2
            ) AS dominant_family_weight


        FROM ranked


        WHERE rn = 1

        """)


    print("Project type profile v3 created.")


if __name__ == "__main__":
    main()
