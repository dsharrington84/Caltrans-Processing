from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


MERGES = [

    # old_id, canonical_id, reason

    ("C00170", "C00169", "SEMA naming variation"),
    ("C00126", "C00125", "Mercer Fraser formatting"),
    ("C00102", "C00103", "JABRE formatting"),
    ("C00145", "C00146", "Powell formatting"),
    ("C00016", "C00017", "Autobahn formatting"),
    ("C00052", "C00051", "DOJA formatting"),
    ("C00040", "C00039", "Chumo formatting"),
    ("C00194", "C00193", "Truesdell phone artifact"),
    ("C00205", "C00203", "Westcoast formatting"),
]


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_id_merge_map
        """)

        con.execute("""
        CREATE TABLE contractor_id_merge_map (
            old_contractor_id VARCHAR,
            canonical_contractor_id VARCHAR,
            merge_reason VARCHAR,
            confidence VARCHAR,
            status VARCHAR
        )
        """)

        for old_id, canonical_id, reason in MERGES:

            con.execute("""
            INSERT INTO contractor_id_merge_map
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                old_id,
                canonical_id,
                reason,
                "HIGH",
                "APPROVED"
            ])

    print("Contractor merge map created.")


if __name__ == "__main__":
    main()
