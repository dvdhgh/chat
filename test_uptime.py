import database
import time
import asyncio

async def test():
    print("Testing database.init_db()...")
    start = time.time()
    database.init_db()
    print(f"init_db took {time.time() - start:.2f}s")
    
    print("Testing database.get_uptime()...")
    start = time.time()
    result = database.get_uptime()
    print(f"get_uptime took {time.time() - start:.2f}s")
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test())
