import bcrypt

hash_val = b"$2b$12$fqwG.zYGVoZ/Ab24UIU9ZeoIBop5jsyZKwd3PuZlulXOKtgz52Scq"

pwds_to_test = ["realestate123", "password123", "admin123"]

for p in pwds_to_test:
    if bcrypt.checkpw(p.encode('utf-8'), hash_val):
        print(f"Match found: {p}")
        break
else:
    print("No match found")
