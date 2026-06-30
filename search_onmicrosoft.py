import common

config = common.load_config()
search_base = config.get('AD_SEARCH_BASE')

conn = common.get_service_account_connection()
conn.auto_referrals = False

# Search for users with proxyAddresses set
conn.search(
    search_base,
    '(&(objectClass=user)(objectCategory=person)(proxyAddresses=*))',
    attributes=['sAMAccountName', 'cn', 'proxyAddresses'],
    size_limit=1000
)

print(f"Total entries with proxyAddresses: {len(conn.entries)}")
found_count = 0
for entry in conn.entries:
    proxies = entry.proxyAddresses.values if 'proxyAddresses' in entry else []
    on_ms = [p for p in proxies if 'onmicrosoft.com' in p.lower()]
    if on_ms:
        found_count += 1
        print("-" * 50)
        print("sAMAccountName:", entry.sAMAccountName.value)
        print("CN:", entry.cn.value)
        print("proxyAddresses:", proxies)
        if found_count >= 10:
            print("Stopping after 10 examples...")
            break
