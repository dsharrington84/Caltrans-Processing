from pathlib import Path
import duckdb
import re


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def normalize_name(name):

    if not name:
        return ""

    name = str(name).upper()

    # punctuation cleanup
    name = re.sub(r"[,.]", "", name)

    # spacing cleanup
    name = re.sub(r"\s+", " ", name).strip()

    return name


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractors_v2
        """)

        con.execute("""
        DROP TABLE IF EXISTS contractor_aliases_v2
        """)

        con.execute("""
        CREATE TABLE contractors_v2 (
            contractor_id VARCHAR PRIMARY KEY,
            canonical_name VARCHAR,
            normalized_name VARCHAR,
            is_sema BOOLEAN,
            notes VARCHAR
        )
        """)

        con.execute("""
        CREATE TABLE contractor_aliases_v2 (
            alias_name VARCHAR,
            contractor_id VARCHAR,
            confidence DOUBLE,
            source VARCHAR
        )
        """)

        names = con.execute("""
        SELECT DISTINCT bidder_name
        FROM bidder_staging
        ORDER BY bidder_name
        """).fetchall()


        contractor_map = {}

        contractor_counter = 1


        for (name,) in names:

            normalized = normalize_name(name)

            if normalized not in contractor_map:

                contractor_map[normalized] = (
                    f"C{contractor_counter:05d}",
                    name
                )

                contractor_counter += 1


        for normalized, data in contractor_map.items():

            contractor_id, canonical = data

            con.execute("""
            INSERT INTO contractors_v2
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                contractor_id,
                canonical,
                normalized,
                "SEMA" in normalized,
                None
            ])


        for normalized, data in contractor_map.items():

            contractor_id, canonical = data

            aliases = con.execute("""
            SELECT DISTINCT bidder_name
            FROM bidder_staging
            WHERE UPPER(REPLACE(REPLACE(bidder_name,'.',''),',','')) = ?
            """,
            [normalized]).fetchall()


            for (alias,) in aliases:

                con.execute("""
                INSERT INTO contractor_aliases_v2
                VALUES (?, ?, ?, ?)
                """,
                [
                    alias,
                    contractor_id,
                    1.0,
                    "bidder_staging"
                ])


    print("Contractor Master v2 created.")


if __name__ == "__main__":
    main()
