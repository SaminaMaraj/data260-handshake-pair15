from sqlalchemy import text

from app.database import engine


with engine.connect() as connection:
    result = connection.execute(text("SELECT DATABASE(), 1"))
    database_name, test_value = result.one()

    print(f"Connected to database: {database_name}")
    print(f"Test result: {test_value}")
