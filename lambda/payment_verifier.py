import random

def lambda_handler(event, context):
    print(event)
    # Random int between 0–3 inclusive. 
    # Payment verification fails 25% of the time. 
    payment_ind = random.randint(0, 3)
    return {
        'paymentVerified': False if payment_ind is 0 else True
    }    
