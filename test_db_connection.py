
import os
import psycopg

from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from .env")

# Add SSL if required and not already configured
if "sslmode" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{separator}sslmode=require"

# TEST 1: Check database host
parsed_url = urlparse(DATABASE_URL)

print("\n========== TEST 1 ==========")
print("Database Host:", parsed_url.hostname)
print("Database Name:", parsed_url.path)

sslmode = parse_qs(parsed_url.query).get("sslmode", ["not specified"])[0]
print("SSL Mode:", sslmode)

# TEST 2: Check actual database connectivity
print("\n========== TEST 2 ==========")

try:
    with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:

        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()

            print("Database Connection: SUCCESS")
            print("Query Result:", result)

except Exception as e:
    print("Database Connection: FAILED")
    print("Error:", repr(e))
