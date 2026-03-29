python
>>> import duckdb
>>> con = duckdb.connect("kth_metadata.duckdb")   # or whatever path you use in conf
>>> con.sql("SHOW TABLES;")                # or: con.sql("SHOW ALL TABLES;")
>>> con.sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main';")
