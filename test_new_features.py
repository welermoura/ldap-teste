import common
import ldap3

config = common.load_config()
conn = common.get_service_account_connection()
conn.auto_referrals = False

username = "testecaixa"
search_base = config.get('AD_SEARCH_BASE')

print(f"1. Fetching current status of {username}...")
conn.search(
    search_base,
    f'(&(objectClass=user)(sAMAccountName={username}))',
    attributes=['distinguishedName', 'userAccountControl', 'msExchRecipientTypeDetails', 'msExchRemoteRecipientType', 'msExchDelegateListLink']
)

if not conn.entries:
    print(f"Error: User {username} not found.")
    exit(1)

user = conn.entries[0]
dn = user.entry_dn
original_uac = user.userAccountControl.value
original_type = user.msExchRecipientTypeDetails.value if 'msExchRecipientTypeDetails' in user else None
original_remote = user.msExchRemoteRecipientType.value if 'msExchRemoteRecipientType' in user else None

print("Original UAC:", original_uac)
print("Original msExchRecipientTypeDetails:", original_type)
print("Original msExchRemoteRecipientType:", original_remote)

# Step 2: Convert to Normal Mailbox
print("\n2. Simulating conversion to Normal Mailbox (User Mailbox)...")
new_uac = original_uac & ~2  # Enable account (remove bit 2)
modifications = {
    'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])],
    'msExchRecipientTypeDetails': [(ldap3.MODIFY_REPLACE, [1])],
    'msExchRemoteRecipientType': [(ldap3.MODIFY_REPLACE, [4])]
}
conn.modify(dn, modifications)
print("Modify result:", conn.result['description'])

# Verify normal attributes
conn.search(dn, '(objectClass=*)', attributes=['userAccountControl', 'msExchRecipientTypeDetails', 'msExchRemoteRecipientType'])
normal_user = conn.entries[0]
print("New UAC (should be 512):", normal_user.userAccountControl.value)
print("New msExchRecipientTypeDetails (should be 1):", normal_user.msExchRecipientTypeDetails.value if 'msExchRecipientTypeDetails' in normal_user else 'N/A')
print("New msExchRemoteRecipientType (should be 4):", normal_user.msExchRemoteRecipientType.value if 'msExchRemoteRecipientType' in normal_user else 'N/A')

# Step 3: Revert back to Shared Mailbox (using 97)
print("\n3. Converting back to Shared Mailbox...")
shared_uac = normal_user.userAccountControl.value | 2 # Disable account
revert_shared = {
    'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(shared_uac)])],
    'msExchRecipientTypeDetails': [(ldap3.MODIFY_REPLACE, [34359738368])],
    'msExchRemoteRecipientType': [(ldap3.MODIFY_REPLACE, [97])]
}
conn.modify(dn, revert_shared)
print("Revert result:", conn.result['description'])

# Verify shared attributes
conn.search(dn, '(objectClass=*)', attributes=['userAccountControl', 'msExchRecipientTypeDetails', 'msExchRemoteRecipientType'])
shared_user = conn.entries[0]
print("Reverted UAC (should be 514):", shared_user.userAccountControl.value)
print("Reverted msExchRecipientTypeDetails (should be 34359738368):", shared_user.msExchRecipientTypeDetails.value)
print("Reverted msExchRemoteRecipientType (should be 97):", shared_user.msExchRemoteRecipientType.value)

# Step 4: Delegate Management Test
print("\n4. Finding a test user to act as delegate...")
conn.search(
    search_base,
    '(&(objectClass=user)(objectCategory=person)(!(sAMAccountName=testecaixa)))',
    attributes=['distinguishedName', 'sAMAccountName'],
    size_limit=1
)
if not conn.entries:
    print("Error: Could not find any other user for delegate test.")
    exit(1)

delegate_user = conn.entries[0]
delegate_dn = delegate_user.entry_dn
delegate_sam = delegate_user.sAMAccountName.value
print(f"Selected Delegate: {delegate_sam} ({delegate_dn})")

# Add delegate
print(f"\n5. Adding {delegate_sam} as delegate of {username}...")
conn.search(dn, '(objectClass=*)', attributes=['msExchDelegateListLink'])
current_delegates = conn.entries[0].msExchDelegateListLink.values if 'msExchDelegateListLink' in conn.entries[0] else []
new_delegates = [str(d) for d in current_delegates]
new_delegates.append(delegate_dn)

conn.modify(dn, {'msExchDelegateListLink': [(ldap3.MODIFY_REPLACE, new_delegates)]})
print("Add delegate modify result:", conn.result['description'])

# Verify delegate added
conn.search(dn, '(objectClass=*)', attributes=['msExchDelegateListLink'])
print("Updated delegates link list:", conn.entries[0].msExchDelegateListLink.values if 'msExchDelegateListLink' in conn.entries[0] else [])

# Remove delegate
print(f"\n6. Removing {delegate_sam} from delegates...")
revert_delegates = [str(d) for d in new_delegates if str(d).lower() != delegate_dn.lower()]
conn.modify(dn, {'msExchDelegateListLink': [(ldap3.MODIFY_REPLACE, revert_delegates)]})
print("Remove delegate modify result:", conn.result['description'])

# Verify delegate removed
conn.search(dn, '(objectClass=*)', attributes=['msExchDelegateListLink'])
print("Final delegates link list (should be same as original):", conn.entries[0].msExchDelegateListLink.values if 'msExchDelegateListLink' in conn.entries[0] else [])
