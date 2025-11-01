from pymongo import MongoClient

def get_MS_access_token():
    user = "root"
    passwd = "123456"
    ipaddress = "10.86.71.100"
    port = "27017"
    db_name = "token_store"      
    collection_name = "oauth_tokens"

    mongo_uri = f"mongodb://{user}:{passwd}@{ipaddress}:{port}/"
    client = MongoClient(mongo_uri)
    try:
        db = client[db_name]
        collection = db[collection_name]

        doc = collection.find_one({"_id": "microsoft_oauth_token"})
        if doc and "access_token" in doc:
            return doc["access_token"]
        else:
            return None
    finally:
        client.close()

if __name__ == "__main__":
    # ---------------------------
    # 仅当脚本被直接运行时执行
    # ---------------------------
    print("🟢 正在连接 MongoDB...")
    token = get_MS_access_token()

    if token:
        print("✅ 成功获取 access_token：")
        print(token)
    else:
        print("❌ 未获取到 access_token，请检查数据库或 _id 是否存在。")
