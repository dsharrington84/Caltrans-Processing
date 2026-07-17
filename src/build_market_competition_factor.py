from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS market_competition_factor
        """)


        con.execute("""
        CREATE TABLE market_competition_factor AS


        SELECT

            c.contract_number,

            c.bidder_count,

            c.competition_class,


            s.low_bid,

            s.second_bid,

            s.low_to_second_pct,

            s.spread_class,


            CASE


                WHEN

                    c.competition_class = 'HIGH'

                    AND

                    s.spread_class IN
                    ('VERY_TIGHT','TIGHT')

                THEN 'HIGH_PRESSURE'


                WHEN

                    c.competition_class = 'LOW'

                THEN 'LOW_PRESSURE'


                ELSE 'NORMAL_PRESSURE'


            END AS competition_pressure,


            CASE


                WHEN

                    c.competition_class = 'HIGH'

                    AND

                    s.spread_class IN
                    ('VERY_TIGHT','TIGHT')

                THEN 0.95


                WHEN

                    c.competition_class = 'LOW'

                THEN 1.05


                ELSE 1.00


            END AS competition_factor


        FROM contract_competition_index c


        JOIN bid_spread_analysis s

            ON c.contract_number =
               s.contract_number

        """)


    print("Market competition factor created.")


if __name__ == "__main__":
    main()
