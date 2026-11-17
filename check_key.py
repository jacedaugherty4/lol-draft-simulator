from config import get_riot_api_key

key = get_riot_api_key()
print(f"Got key, length {len(key)}, ends in ...{key[-4:]}")