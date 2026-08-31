# check_redis.py

import redis

try:
    r = redis.Redis.from_url('redis://localhost:6379/0')
    if r.ping():
        print("✅ Redis is running!")
    else:
        print("❌ Redis is not responding")
except Exception as e:
    print(f"❌ Redis error: {e}")
