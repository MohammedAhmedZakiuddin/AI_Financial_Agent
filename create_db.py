import sqlite3
import random
import faker
from datetime import datetime, timedelta

# Initialize Faker
fake = faker.Faker()

# Connect to SQLite database
conn = sqlite3.connect('customers.db')
cursor = conn.cursor()

# Drop tables if they exist
cursor.execute('DROP TABLE IF EXISTS customers')
cursor.execute('DROP TABLE IF EXISTS transactions')

# Create customers table
cursor.execute('''
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    email TEXT,
    zip_code TEXT,
    account_number TEXT,
    balance REAL
)
''')

# Create transactions table
cursor.execute('''
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    date TEXT,
    description TEXT,
    amount REAL,
    running_balance REAL,
    FOREIGN KEY (customer_id) REFERENCES customers (id)
)
''')

# Transaction Categories
types = [
    ("Rent Payment", -1200),
    ("WiFi Bill", -60),
    ("Car Insurance", -150),
    ("Health Insurance", -200),
    ("Water Bill", -30),
    ("Gas Station", -50),
    ("Groceries", -100),
    ("Dining Out", -80),
    ("Movie Night", -40),
    ("Gym Membership", -45)
]

# Generate 50 dummy customers
for _ in range(50):
    first_name = fake.first_name()
    last_name = fake.last_name()
    phone = fake.msisdn()[:10]  # Ensure 10 digits
    email = fake.email()
    zip_code = fake.zipcode()
    account_number = fake.unique.bban()
    balance = round(random.uniform(5000, 20000), 2)

    # Insert into customers table
    cursor.execute('''
    INSERT INTO customers (first_name, last_name, phone, email, zip_code, account_number, balance)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (first_name, last_name, phone, email, zip_code, account_number, balance))
    
    customer_id = cursor.lastrowid

    # Insert 10 transactions for each customer
    transaction_date = datetime.now()
    running_balance = balance

    for description, amount_base in types:
        amount = amount_base + random.uniform(-5, 5)  # Slight random adjustment
        running_balance += amount
        cursor.execute('''
        INSERT INTO transactions (customer_id, date, description, amount, running_balance)
        VALUES (?, ?, ?, ?, ?)
        ''', (customer_id, transaction_date.strftime('%Y-%m-%d'), description, amount, running_balance))

        # Move the date backward for each transaction
        transaction_date -= timedelta(days=random.randint(1, 5))

# Commit and close
conn.commit()
conn.close()

print("✅ Customer database with 50 customers and 10 transactions each created successfully!")
