import common

config = common.load_config()
search_base = config.get('AD_SEARCH_BASE')

conn = common.get_service_account_connection()
conn.auto_referrals = False

# Search for objects with msExchRecipientTypeDetails = 34359738368 (Shared Mailbox)
conn.search(
    search_base,
    '(&(objectClass=user)(objectCategory=person)(msExchRecipientTypeDetails=34359738368))',
    attributes=['sAMAccountName', 'cn', 'mail', 'targetAddress', 'proxyAddresses', 'msExchRemoteRecipientType', 'userPrincipalName', 'userAccountControl', 'mailNickname'],
    size_limit=10
)

print(f"Encontradas {len(conn.entries)} caixas compartilhadas no AD:")
for entry in conn.entries:
    print("-" * 50)
    print("sAMAccountName:", entry.sAMAccountName.value)
    print("CN:", entry.cn.value)
    print("mail:", entry.mail.value if 'mail' in entry else 'N/A')
    print("targetAddress:", entry.targetAddress.value if 'targetAddress' in entry else 'N/A')
    print("mailNickname:", entry.mailNickname.value if 'mailNickname' in entry else 'N/A')
    print("userPrincipalName:", entry.userPrincipalName.value if 'userPrincipalName' in entry else 'N/A')
    print("userAccountControl:", entry.userAccountControl.value if 'userAccountControl' in entry else 'N/A')
    print("msExchRemoteRecipientType:", entry.msExchRemoteRecipientType.value if 'msExchRemoteRecipientType' in entry else 'N/A')
    print("proxyAddresses:", entry.proxyAddresses.values if 'proxyAddresses' in entry else 'N/A')
