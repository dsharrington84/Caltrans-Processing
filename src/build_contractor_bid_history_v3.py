from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_bid_history_v3
        """)

        con.execute("""
        CREATE TABLE contractor_bid_history_v3 AS

        SELECT

            COALESCE(
                m.canonical_contractor_id,
                a.contractor_id
            ) AS contractor_id,

            b.contract_number,

            b.bid_rank,

            b.roster_bid_amount AS bid_amount,

            b.award_status,


            CASE
                WHEN b.bid_rank = 1
                THEN TRUE
                ELSE FALSE
            END AS won_flag


        FROM bidder_staging b


        JOIN contractor_aliases_v2 a

            ON b.bidder_name = a.alias_name


        LEFT JOIN contractor_id_merge_map m

            ON a.contractor_id = m.old_contractor_id

        """)

    print("Contractor bid history v3 created.")


if __name__ == "__main__":
    main()
