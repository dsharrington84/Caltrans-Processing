from pathlib import Path
import duckdb
import re


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def normalize_name(name):

    if not name:
        return ""

    name = str(name).upper()

    name = re.sub(r"[,.]", "", name)

    name = name.replace(" INCORPORATED", " INC")
    name = name.replace(" INC.", " INC")
    name = name.replace(" LLC.", " LLC")

    name = re.sub(r"\s+", " ", name).strip()

    return name


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractors
        """)

        con.execute("""
        DROP TABLE IF EXISTS contractor_aliases
        """)

        con.execute("""
        CREATE TABLE contractors (
            contractor_id VARCHAR PRIMARY KEY,
            canonical_name VARCHAR,
            normalized_name VARCHAR,
            is_sema BOOLEAN,
            notes VARCHAR
        )
        """)

        con.execute("""
        CREATE TABLE contractor_aliases (
            alias_name VARCHAR,
            contractor_id VARCHAR,
            source VARCHAR,
            confidence DOUBLE
        )
        """)

        bidders = con.execute("""
        SELECT DISTINCT bidder_name
        FROM bidder_staging
        """).fetchall()


        contractor_id = 1

        for (name,) in bidders:

            normalized = normalize_name(name)

            cid = f"C{contractor_id:05d}"

            con.execute("""
            INSERT INTO contractors
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                cid,
                name,
                normalized,
                "SEMA" in normalized,
                None
            ])

            con.execute("""
            INSERT INTO contractor_aliases
            VALUES (?, ?, ?, ?)
            """,
            [
                name,
                cid,
                "bidder_staging",
                1.0
            ])

            contractor_id += 1


    print("Contractor Master v1 created.")


if __name__ == "__main__":
    main()
