import random

def lambda_handler(event, context):
    print(event)
    items = event["items"]
    # Out of stock 10% of the time. 
    for item in items:
        item["quantityInStock"] = random.randint(0, 9)
        
    return items