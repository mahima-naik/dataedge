import bcrypt

passwords = {
    "buyers@procucev.com": "buyers123",
    "rfqs@procucev.com": "rfqs123",
    "admin@procucev.com": "admin123",
    "factory@procucev.com": "factory123",
    "realestate@procucev.com": "realestate123",
    "vernikaai@procucev.com": "vernikaai123",
    "sellers@procucev.com": "sellers123",
}

for email, pwd in passwords.items():
    h = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    print(f'    "{email}": {{')
    print(f'        "password_hash": b"{h}",')
    print(f'        "role": "{email.split("@")[0].replace("realestate", "real_estate")}",')
    print(f'    }},')
