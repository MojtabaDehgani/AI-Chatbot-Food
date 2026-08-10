import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "food_orders.db")

connection = sqlite3.connect(DB_PATH)
cursor = connection.cursor()

cursor.executescript("""
DROP TABLE IF EXISTS food_orders;

CREATE TABLE food_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    food_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    comment TEXT,
    FOREIGN KEY(user_id) REFERENCES allowed_users(id),
    FOREIGN KEY(food_id) REFERENCES foods(id)
);
""")

connection.commit()
connection.close()

print("✅ The database was successfully updated and the new table was created!")