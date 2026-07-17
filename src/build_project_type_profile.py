from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS project_type_profile
        """)


        con.execute("""
        CREATE TABLE project_type_profile AS


        WITH item_weights AS (

            SELECT

                contract_number,

                item_description,

                SUM(pct_of_contract)
                    AS item_weight


            FROM contract_item_cost_weight


            GROUP BY

                contract_number,

                item_description

        ),


        categorized AS (

            SELECT

                contract_number,

                item_weight,


                CASE

                    WHEN LOWER(item_description)
                    LIKE '%asphalt%'
                    OR LOWER(item_description)
                    LIKE '%pavement%'
                    OR LOWER(item_description)
                    LIKE '%hot mix%'

                    THEN 'PAVING'


                    WHEN LOWER(item_description)
                    LIKE '%bridge%'
                    OR LOWER(item_description)
                    LIKE '%structural concrete%'
                    OR LOWER(item_description)
                    LIKE '%structural steel%'

                    THEN 'STRUCTURES'


                    WHEN LOWER(item_description)
                    LIKE '%signal%'
                    OR LOWER(item_description)
                    LIKE '%lighting%'
                    OR LOWER(item_description)
                    LIKE '%fiber%'

                    THEN 'ELECTRICAL'


                    WHEN LOWER(item_description)
                    LIKE '%pipe%'
                    OR LOWER(item_description)
                    LIKE '%drain%'
                    OR LOWER(item_description)
                    LIKE '%culvert%'

                    THEN 'DRAINAGE'


                    WHEN LOWER(item_description)
                    LIKE '%excav%'
                    OR LOWER(item_description)
                    LIKE '%grading%'
                    OR LOWER(item_description)
                    LIKE '%embank%'

                    THEN 'EARTHWORK'


                    ELSE 'OTHER'


                END AS project_type


            FROM item_weights

        ),


        ranked AS (

            SELECT

                contract_number,

                project_type,

                SUM(item_weight) AS type_weight,


                ROW_NUMBER() OVER (

                    PARTITION BY contract_number

                    ORDER BY SUM(item_weight) DESC

                ) AS rn


            FROM categorized


            GROUP BY

                contract_number,

                project_type

        )


        SELECT

            contract_number,

            project_type,

            type_weight


        FROM ranked


        WHERE rn = 1

        """)


    print("Project type profile created.")


if __name__ == "__main__":
    main()
