import common
import ldap3

config = common.load_config()
conn = common.get_service_account_connection()
conn.auto_referrals = False

username = "testecaixa"
print(f"1. Fetching current attributes for {username}...")
conn.search(
    config.get('AD_SEARCH_BASE'),
    f'(&(objectClass=user)(sAMAccountName={username}))',
    attributes=['distinguishedName', 'mail', 'targetAddress', 'proxyAddresses', 'userPrincipalName']
)

if not conn.entries:
    print(f"Error: User {username} not found.")
    exit(1)

user = conn.entries[0]
dn = user.entry_dn
original_mail = user.mail.value if 'mail' in user else None
original_target = user.targetAddress.value if 'targetAddress' in user else None
original_upn = user.userPrincipalName.value if 'userPrincipalName' in user else None
original_proxies = user.proxyAddresses.values if 'proxyAddresses' in user else []

print("Original mail:", original_mail)
print("Original targetAddress:", original_target)
print("Original UPN:", original_upn)
print("Original proxyAddresses:", original_proxies)

# Step 2: Add a temporary alias
temp_alias = "testecaixa-temp@comolatti.com.br"
print(f"\n2. Adding temporary alias {temp_alias} to proxyAddresses...")
new_proxies = [str(p) for p in original_proxies]
new_proxies.append(f"smtp:{temp_alias}")

conn.modify(dn, {'proxyAddresses': [(ldap3.MODIFY_REPLACE, new_proxies)]})
if conn.result['description'] != 'success':
    print("Error adding temporary alias:", conn.result)
    exit(1)

# Step 3: Promote the temporary alias to primary (simulating api_set_primary_alias)
print(f"\n3. Promoting {temp_alias} to primary...")
# Calculate new proxies (SMTP: for primary, smtp: for aliases)
updated_proxies = []
for p in new_proxies:
    if p.startswith('SMTP:'):
        updated_proxies.append(f"smtp:{p[5:]}")
    elif p.lower() == f"smtp:{temp_alias.lower()}":
        updated_proxies.append(f"SMTP:{temp_alias}")
    else:
        updated_proxies.append(p)

# Modify using the new logic (without modifying userPrincipalName)
changes = {
    'proxyAddresses': [(ldap3.MODIFY_REPLACE, updated_proxies)],
    'mail': [(ldap3.MODIFY_REPLACE, [temp_alias])],
    'targetAddress': [(ldap3.MODIFY_REPLACE, [temp_alias])]
}

conn.modify(dn, changes)
if conn.result['description'] != 'success':
    print("Error promoting alias:", conn.result)
    exit(1)

# Step 4: Verify the result
print("\n4. Verifying modifications in AD...")
conn.search(dn, '(objectClass=*)', attributes=['mail', 'targetAddress', 'proxyAddresses', 'userPrincipalName'])
updated_user = conn.entries[0]

print("Updated mail:", updated_user.mail.value if 'mail' in updated_user else 'N/A')
print("Updated targetAddress:", updated_user.targetAddress.value if 'targetAddress' in updated_user else 'N/A')
print("Updated UPN (should be same as original):", updated_user.userPrincipalName.value if 'userPrincipalName' in updated_user else 'N/A')
print("Updated proxyAddresses:", updated_user.proxyAddresses.values if 'proxyAddresses' in updated_user else 'N/A')

# Revert back to original state
print("\n5. Reverting changes back to original state...")
revert_changes = {
    'proxyAddresses': [(ldap3.MODIFY_REPLACE, original_proxies)],
    'mail': [(ldap3.MODIFY_REPLACE, [original_mail] if original_mail else [])],
    'targetAddress': [(ldap3.MODIFY_REPLACE, [original_target] if original_target else [])]
}
conn.modify(dn, revert_changes)
print("Revert result:", conn.result['description'])
