from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS project_type_profile_v2
        """)


        con.execute("""
        CREATE TABLE project_type_profile_v2 AS


        WITH item_family_scores AS (

            SELECT

                contract_number,

                item_description,

                pct_of_contract,


                CASE


                    WHEN LOWER(item_description) LIKE '%asphalt%'
                    OR LOWER(item_description) LIKE '%pavement%'
                    OR LOWER(item_description) LIKE '%hot mix%'
                    OR LOWER(item_description) LIKE '%grind%'

                    THEN 'PAVING_REHAB'


                    WHEN LOWER(item_description) LIKE '%bridge%'
                    OR LOWER(item_description) LIKE '%structural%'
                    OR LOWER(item_description) LIKE '%concrete%'

                    THEN 'STRUCTURES_BRIDGE'


                    WHEN LOWER(item_description) LIKE '%signal%'
                    OR LOWER(item_description) LIKE '%lighting%'
                    OR LOWER(item_description) LIKE '%fiber%'
                    OR LOWER(item_description) LIKE '%electrical%'

                    THEN 'ELECTRICAL_ITS'


                    WHEN LOWER(item_description) LIKE '%pipe%'
                    OR LOWER(item_description) LIKE '%drain%'
                    OR LOWER(item_description) LIKE '%culvert%'

                    THEN 'DRAINAGE_STORMWATER'


                    WHEN LOWER(item_description) LIKE '%excavat%'
                    OR LOWER(item_description) LIKE '%grading%'
                    OR LOWER(item_description) LIKE '%embank%'

                    THEN 'EARTHWORK_GRADING'


                    WHEN LOWER(item_description) LIKE '%sign%'
                    OR LOWER(item_description) LIKE '%barrier%'
                    OR LOWER(item_description) LIKE '%stripe%'
                    OR LOWER(item_description) LIKE '%traffic%'

                    THEN 'TRAFFIC_SAFETY'


                    WHEN LOWER(item_description) LIKE '%landscape%'
                    OR LOWER(item_description) LIKE '%erosion%'
                    OR LOWER(item_description) LIKE '%vegetation%'

                    THEN 'ENVIRONMENTAL_LANDSCAPE'


                    ELSE 'OTHER'


                END AS project_family


            FROM contract_item_cost_weight

        ),


        project_scores AS (

            SELECT

                contract_number,

                project_family,

                SUM(pct_of_contract)
                    AS family_weight


            FROM item_family_scores


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


            FROM project_scores

        )


        SELECT

            contract_number,

            CASE

                WHEN family_weight < 40

                THEN 'MULTI_DISCIPLINE'

                ELSE project_family

            END AS project_type,


            ROUND(
                family_weight,
                2
            ) AS dominant_family_weight


        FROM ranked


        WHERE rn = 1

        """)


    print("Project type profile v2 created.")


if __name__ == "__main__":
    main()
