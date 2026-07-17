from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contract_total_reconciliation
        """)

        con.execute("""
        CREATE TABLE contract_total_reconciliation AS

        SELECT

            t.contract_number,

            t.contractor_id,

            t.bid_rank,

            t.total_bid_amount AS reference_total,


            SUM(h.extended_amount)
                AS calculated_total,


            ROUND(
                (
                    SUM(h.extended_amount)
                    -
                    t.total_bid_amount
                )
                /
                NULLIF(
                    t.total_bid_amount,
                    0
                )
                * 100,
                4
            ) AS variance_pct,


            CASE

                WHEN ABS(
                    (
                    SUM(h.extended_amount)
                    -
                    t.total_bid_amount
                    )
                    /
                    NULLIF(
                        t.total_bid_amount,
                        0
                    )
                    * 100
                ) <= 0.01

                THEN 'PASS'

                ELSE 'REVIEW'

            END AS reconciliation_status


        FROM contract_bid_totals t

        JOIN historical_bid_prices h

            ON t.contract_number = h.contract_number

            AND t.contractor_id = h.contractor_id

            AND t.bid_rank = h.bid_rank


        GROUP BY

            t.contract_number,

            t.contractor_id,

            t.bid_rank,

            t.total_bid_amount

        """)

    print("Contract total reconciliation created.")


if __name__ == "__main__":
    main()
