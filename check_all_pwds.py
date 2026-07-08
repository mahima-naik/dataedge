import bcrypt

hashes = {
    "dataedge@pitchxai.com": b"$2b$12$iIkqGdA65scP5wCkVZzMgOdS2EeBLCBgbwa83vWmo5aadVg8NoKSq",
    "data-edge@gmail.com": b"$2b$12$o2iwP0QtQViVOPIMkPmE5.RtB4cJke7tH3XtM8xb8cewIKnPjMZ.q",
    "buyers@procucev.com": b"$2b$12$PFPpx4Ce9t6emE9cdQK/4.hJmv5ZVM98RfypJ5X5/2ya3hYdLExLO",
    "rfqs@procucev.com": b"$2b$12$yXSPFYsWoqPO3Y9.MoXW9Ox/lXApdAnPPZJzhYNx.TKoG6Mwwb67y",
    "admin@procucev.com": b"$2b$12$oWaM3kYTRT1ufyAFdEzJueCADOkg8zJKgqyKqXXqXsIasOEA9LH5u",
    "factory@procucev.com": b"$2b$12$N6kT7BiCxvuYr12XxcMM0OoL2EZQse/g5.DzMlE3U0IiyJd5ZH7XC",
    "realestate@procucev.com": b"$2b$12$fqwG.zYGVoZ/Ab24UIU9ZeoIBop5jsyZKwd3PuZlulXOKtgz52Scq",
    "vernikaai@procucev.com": b"$2b$12$1hG62JWGVTuH5lw/hr02zObT6SL5yiBZMA0Td0wP.dE4nsn/yAsiq",
}

for email, h in hashes.items():
    found = False
    for p in ["dataedge123", "sellers123", "buyers123", "rfqs123", "admin123", "factory123", "realestate123", "vernikaai123", "password123"]:
        if bcrypt.checkpw(p.encode('utf-8'), h):
            print(f"{email}: {p}")
            found = True
            break
    if not found:
        print(f"{email}: UNKNOWN")
