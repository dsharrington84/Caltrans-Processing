from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        # ----------------------------------
        # Contract Bid Totals
        # ----------------------------------

        con.execute("""
        DROP TABLE IF EXISTS contract_bid_totals
        """)

        con.execute("""
        CREATE TABLE contract_bid_totals AS

        SELECT

            contract_number,
            contractor_id,
            bid_rank,

            SUM(extended_amount) AS total_bid_amount

        FROM historical_bid_prices

        GROUP BY

            contract_number,
            contractor_id,
            bid_rank

        """)


        # ----------------------------------
        # Item Cost Weight
        # ----------------------------------

        con.execute("""
        DROP TABLE IF EXISTS contract_item_cost_weight
        """)

        con.execute("""
        CREATE TABLE contract_item_cost_weight AS

        SELECT

            h.contract_number,
            h.contractor_id,
            h.bid_rank,

            h.item_number,
            h.item_code,
            h.item_description,
            h.unit,

            h.extended_amount,

            t.total_bid_amount,

            ROUND(
                (
                    h.extended_amount
                    /
                    NULLIF(t.total_bid_amount,0)
                )
                * 100,
                4
            ) AS pct_of_contract


        FROM historical_bid_prices h

        JOIN contract_bid_totals t

            ON h.contract_number = t.contract_number

            AND h.contractor_id = t.contractor_id

            AND h.bid_rank = t.bid_rank

        """)


    print("Contract cost weighting tables created.")


if __name__ == "__main__":
    main()
