import Levenshtein
import sqlite3
import os
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "food_orders.db")

@contextmanager
def get_db():
    connection = sqlite3.connect(DB_PATH) 
    cursor = connection.cursor()
    try:
        yield connection, cursor
    finally:
        connection.close()


def _calculate_min_distance(str1, str2):
    if not str1 or not str2:
        return float('inf')
    
    str1, str2 = str1.lower(), str2.lower()
    d1 = Levenshtein.distance(str1, str2, weights=(0, 1, 1))
    d2 = Levenshtein.distance(str1, str2, weights=(1, 0, 1))
    d3 = Levenshtein.distance(str1, str2, weights=(1, 1, 1))
    return min(d1, d2, d3)


def food_search(food_name=None, restaurant_name=None, max_distance=1):
    with get_db() as (connection, cursor):
        cursor.execute("SELECT id, food_name, food_category, restaurant_name, price FROM foods")
        results = cursor.fetchall()

    matches = []
    for food_id, db_food_name, food_category, db_restaurant_name, db_price in results:
        
        f_dist = _calculate_min_distance(food_name, db_food_name) if food_name else None
        r_dist = _calculate_min_distance(restaurant_name, db_restaurant_name) if restaurant_name else None

        is_match = False
        final_dist = 0

        if food_name and restaurant_name:
            if f_dist <= max_distance and r_dist <= max_distance:
                is_match = True
                final_dist = min(f_dist, r_dist)
        elif food_name:
            if f_dist <= max_distance:
                is_match = True
                final_dist = f_dist
        elif restaurant_name:
            if r_dist <= max_distance:
                is_match = True
                final_dist = r_dist

        if is_match:
            matches.append({
                'id': food_id,
                'food_name': db_food_name,
                'food_category': food_category,
                'restaurant_name': db_restaurant_name,
                'price': db_price,
                'edit_distance': final_dist
            })

    matches.sort(key=lambda x: x['edit_distance'])
    return matches


def cancel_order(order_id, phone_number):
    with get_db() as (connection, cursor):
        cursor.execute("""
            SELECT fo.status 
            FROM food_orders fo
            JOIN allowed_users u ON fo.user_id = u.id
            WHERE fo.id = ? AND u.phone = ?
        """, (order_id, phone_number))
        
        result = cursor.fetchone()
        
        if result is None:
            return f"Order ID {order_id} from {phone_number} does not exist."
        
        current_status = result[0]
        
        if current_status == "preparation":
            cursor.execute("UPDATE food_orders SET status = 'canceled' WHERE id = ?", (order_id,))
            connection.commit()
            return f"Order ID {order_id} from {phone_number} has been successfully canceled."
        else:
            return f"Order ID {order_id} from {phone_number} cannot be canceled as it is in '{current_status}' status."
        
def comment_order(order_id, person_name, comment):
    with get_db() as (connection, cursor):
        cursor.execute("SELECT id FROM food_orders WHERE id = ?", (order_id,))
        if cursor.fetchone() is None:
            return f"Order ID {order_id} does not exist."
        
        cursor.execute("UPDATE food_orders SET comment = ? WHERE id = ?", (comment, order_id))
        connection.commit()
        return f"Comment for Order ID {order_id} from {person_name} has been updated."

def check_order_status(order_id):
    with get_db() as (connection, cursor):
        cursor.execute("SELECT status FROM food_orders WHERE id = ?", (order_id,))
        result = cursor.fetchone()
        
        if result is None:
            return f"Order ID {order_id} does not exist."
        
        return f"Order ID {order_id} is currently in '{result[0]}' status."
    
def create_order(person_name, phone_number, order_description):
    with get_db() as (connection, cursor):
        try:
            cursor.execute("SELECT id FROM allowed_users WHERE phone = ?", (phone_number,))
            user_row = cursor.fetchone()
            if not user_row:
                return f"User {person_name} not found in database."
            user_id = user_row[0]

            food_name_part = order_description
            restaurant_name_part = None
            
            if " from " in order_description.lower():
                parts = order_description.lower().split(" from ", 1)
                food_name_part = parts[0].strip()
                restaurant_name_part = parts[1].strip()

            matches = food_search(food_name=food_name_part, restaurant_name=restaurant_name_part, max_distance=2)
            
            if not matches:
                return "Sorry, I couldn't find this specific food in the database to link it to your order."
            
            food_id = matches[0]['id']

            cursor.execute("""
                INSERT INTO food_orders (user_id, food_id, status, comment) 
                VALUES (?, ?, 'preparation', 'No comment yet')
            """, (user_id, food_id))
            
            connection.commit()
            new_order_id = cursor.lastrowid
            return f"Order successfully created! The new Order ID is {new_order_id}."
        except Exception as e:
            return f"Failed to create order due to database error: {e}"
        
def setup_allowed_users():
    users_data = [
        ("Mojtaba", "09105835703"), ("John", "09105835702"), ("Michael", "09105835701"), 
        ("David", "09105835704"), ("James", "09105835705"), ("Robert", "09105835706"), 
        ("William", "09105835707"), ("Joseph", "09105835708"), ("Daniel", "09105835709"), 
        ("Matthew", "09105835710"), ("Andrew", "09105835711"), ("Christopher", "09105835712"), 
        ("Anthony", "09105835713"), ("Joshua", "09105835714"), ("Ryan", "09105835715"), 
        ("Nicholas", "09105835716"), ("Benjamin", "09105835717"), ("Samuel", "09105835718"), 
        ("Jonathan", "09105835719"), ("Alexander", "09105835720"), ("Thomas", "09105835721"), 
        ("Kevin", "09105835722"), ("Jason", "09105835723"), ("Justin", "09105835724"), 
        ("Brandon", "09105835725"), ("Brian", "09105835726"), ("Adam", "09105835727"), 
        ("Nathan", "09105835728"), ("Christian", "09105835729"), ("Aaron", "09105835730"), 
        ("Jack", "09105835731"), ("Henry", "09105835732"), ("Leo", "09105835733"), 
        ("Lucas", "09105835734"), ("Noah", "09105835735"), ("Liam", "09105835736"), 
        ("Ethan", "09105835737"), ("Mason", "09105835738"), ("Logan", "09105835739"), 
        ("Oliver", "09105835740"), ("Jacob", "09105835741"), ("Dylan", "09105835742"), 
        ("Isaac", "09105835743"), ("Caleb", "09105835744"), ("Owen", "09105835745"), 
        ("Hunter", "09105835746"), ("Charles", "09105835747"), ("Patrick", "09105835748"), 
        ("George", "09105835749"), ("Eric", "09105835750")
    ]
    
    with get_db() as (connection, cursor):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE
            )
        ''')
        
        cursor.execute("SELECT COUNT(*) FROM allowed_users")
        count = cursor.fetchone()[0]
        
        if count == 0:
            cursor.executemany('INSERT INTO allowed_users (name, phone) VALUES (?, ?)', users_data)
            connection.commit()
            print("50 authorized users successfully added to the database!")
        else:
            print("Users already exist in the database. No changes made.")


def verify_user(name: str, phone: str) -> bool:
    with get_db() as (connection, cursor):
        cursor.execute("SELECT 1 FROM allowed_users WHERE name = ? AND phone = ?", (name, phone))
        result = cursor.fetchone()
        return result is not None

def get_all_user_orders(phone_number):
    with get_db() as (connection, cursor):
        cursor.execute("""
            SELECT fo.id, f.food_name || ' from ' || f.restaurant_name, fo.status 
            FROM food_orders fo
            JOIN allowed_users u ON fo.user_id = u.id
            JOIN foods f ON fo.food_id = f.id
            WHERE u.phone = ?
        """, (phone_number,))
        
        results = cursor.fetchall()
        
        if not results:
            return "No orders found for this user."
        
        formatted_results = []
        for order_id, desc, status in results:
            formatted_results.append(f"Order ID: {order_id} | Description: {desc} | Status: {status}")
            
        return "\n".join(formatted_results)
