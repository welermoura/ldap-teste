import common

config = common.load_config()
conn = common.get_service_account_connection()
conn.auto_referrals = False

suffixes = common.get_ad_upn_suffixes(conn)
print("Detected UPN Suffixes:")
print(suffixes)
