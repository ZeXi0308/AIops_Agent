from pymongo import MongoClient


class Mongo_DB_config:
    # MongoDB configuration
    user = "root"
    passwd = "123456"
    ipaddress = "10.86.71.100"
    port = "27017"
    # MongoDB server connection URL
    server = f"mongodb://{user}:{passwd}@{ipaddress}:{port}"

def explore_mongodb():
    client = MongoClient(Mongo_DB_config.server)
    db_list = client.list_database_names()
    print("Databases in MongoDB:")

    for db_name in db_list:
        print(f" - {db_name}")
        db = client[db_name]
        try:
            collection_list = db.list_collection_names()
        except Exception as e:
            print(f"   [Cannot access collections: {e}]")
            continue

        print("   Collections:")
        for coll_name in collection_list:
            print(f"     - {coll_name}")
            collection = db[coll_name]
            sample_docs = collection.find().limit(5)
            print("       Sample documents:")
            for doc in sample_docs:
                print(f"         {doc}")

if __name__ == "__main__":
    explore_mongodb()
