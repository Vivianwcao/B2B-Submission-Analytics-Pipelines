import requests
from datetime import datetime, timedelta

# get dates for api
def get_date():
    # convert string to datetime
    today = datetime.today().date()

    # compute range 7 days to be safe
    start_date = today - timedelta(days=7)
    return start_date.isoformat() # YYYY-MM-DD

def get_ssl_credentials(ssm):
    # Fetch cert + key strings from SSM
    response = ssm.get_parameters(
        Names=["/emi-v3/oildex/certificate", "/emi-v3/oildex/ssl_key"],
        WithDecryption=True
    )
    params = {p['Name'].split('/')[-1]: p['Value'] for p in response['Parameters']}
    
    # Write them to /tmp as actual files
    cert_path = '/tmp/client.cert'
    key_path = '/tmp/client.key'
    
    with open(cert_path, 'w') as f:
        f.write(params['certificate'])
    with open(key_path, 'w') as f:
        f.write(params['ssl_key'])
    
    return (cert_path, key_path)

# def get_tickets(duns, cert):
def get_tickets(duns, cert, start_date, end_date):
    # This is the correct url, do not use the one provided in swagger under 'Request URL'
    url = 'https://api.openinvoice.com/docp/supply-chain/v1/receipts/'

    params = {
        # "$filter": f"partyDUNS eq {duns} and dateCriteria eq lastActionDatetime and searchDateFrom eq {get_date()}",
        "$filter": f"partyDUNS eq {duns} and dateCriteria eq lastActionDatetime and searchDateFrom eq {start_date} and searchDateTo eq {end_date}",
        "$select": (
            "itemID, "
            "receiptNumber, "
            "supplierParty, "
            "buyerParty, "
            "submissionSource,"
            "lastActionDatetime, "
            "status, "
            "actions, " 
            "serviceDateFrom, "
            "serviceDateTo, "
            "totalAmount, "
            "currencyCode, "
            "submittedDatetime, " # 99.9% submitted == last submitted
            "lastSubmittedDatetime, " # use this instead of submittedDatetime, slightly more accurate
            "approvedDatetime, "
            "invoicedStatus, "
            "invoiceNumber, "
            "afeNumber, "
            "costCenterNumber, "
            "glCoding,"
            "links, "
            "receiptType"
        )   
    }
    headers = {
        "accept": "application/json",      
    }
    response = requests.get(
        url,
        cert=cert,
        headers=headers,
        params=params,
        timeout=(20, 300)  # (connect_timeout, read_timeout)
    )    
    response.raise_for_status()  # raises HTTP Error automatically
    return response.json()