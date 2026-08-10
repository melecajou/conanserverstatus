import sqlite3
con = sqlite3.connect(":memory:")
cur = con.cursor()
cur.execute("CREATE TABLE t (id INTEGER)")
try:
    placeholders = ",".join("?" * 5000)
    cur.execute(f"SELECT * FROM t WHERE id IN ({placeholders})", list(range(5000)))
    print("Success! Limit is >= 5000")
except Exception as e:
    print("Error:", e)
