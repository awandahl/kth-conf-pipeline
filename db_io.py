import duckdb
import pandas as pd
from config import DB_PATH

def connect():
    return duckdb.connect(DB_PATH)

def fetch_conferences(con, limit):
    return con.execute(f"""
        SELECT pid, name_seq, conference
        FROM names_conference 
        WHERE conference IS NOT NULL
        USING SAMPLE {limit} ROWS
    """).df()  # ✅ .df() not .fetch_df()

def write_parsed_table(con, df, table_name="names_conference_parsed"):
    con.register("df", df)  # ✅ Register first
    con.execute(f"DROP TABLE IF EXISTS {table_name}")
    con.sql(f"CREATE TABLE {table_name} AS SELECT * FROM df")
    con.unregister("df")
