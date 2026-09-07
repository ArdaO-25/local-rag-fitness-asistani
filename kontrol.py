import sqlite3

DB_PATH = "knowledge.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, source, content FROM chunks ORDER BY id")

for chunk_id, source, content in cursor.fetchall():
    print(f"--- id: {chunk_id} | kaynak: {source} ---")
    print(content)
    print()

conn.close()
