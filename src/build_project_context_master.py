from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS project_context_master
        """)


        con.execute("""
        CREATE TABLE project_context_master AS


        SELECT

            s.contract_number,

            s.project_value,

            s.project_size_band,


            r.district,


            p.project_type,

            p.dominant_family_weight,


            c.bidder_count,

            c.contractor_count,

            c.competition_class,


            m.competition_pressure,

            m.competition_factor


        FROM project_size_bands s


        LEFT JOIN historical_contract_reference_v2 r

            ON s.contract_number =
               r.contract_number


        LEFT JOIN project_type_profile_v3 p

            ON s.contract_number =
               p.contract_number


        LEFT JOIN contract_competition_index c

            ON s.contract_number =
               c.contract_number


        LEFT JOIN market_competition_factor m

            ON s.contract_number =
               m.contract_number

        """)


    print("Project context master created.")


if __name__ == "__main__":
    main()
