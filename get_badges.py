"""
Garmin Badge & Challenge Fetcher
Scarica badge guadagnati e sfide mensili da Garmin Connect.
"""

import json
import os
import base64
import tempfile
import shutil
from datetime import datetime

import garth
from garminconnect import Garmin

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_B64 = os.getenv("GARMIN_TOKEN")


def restore_token():
    """Decodifica il token base64 dal GitHub Secret."""
    if not TOKEN_B64:
        return None

    token_dir = os.path.join(tempfile.gettempdir(), "garth_session")
    if os.path.exists(token_dir):
        shutil.rmtree(token_dir)
    os.makedirs(token_dir)

    try:
        token_json = base64.b64decode(TOKEN_B64).decode()
        token_data = json.loads(token_json)

        for filename, content in token_data.items():
            filepath = os.path.join(token_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"Token ripristinato: {list(token_data.keys())}")
        return token_dir

    except Exception as e:
        print(f"Errore nel ripristino token: {e}")
        return None


def get_client():
    """Crea un client Garmin autenticato."""
    # Strategia 1: token pre-generato
    token_dir = restore_token()
    if token_dir:
        try:
            garth.resume(token_dir)
            client = Garmin()
            client.login(token_dir)
            print("Autenticazione con token riuscita.")
            return client
        except Exception as e:
            print(f"Token non valido: {e}")

    # Strategia 2: login diretto (fallback)
    if EMAIL and PASSWORD:
        try:
            client = Garmin(EMAIL, PASSWORD)
            client.login()
            print("Login diretto riuscito.")
            return client
        except Exception as e:
            print(f"Login diretto fallito: {e}")

    raise RuntimeError("Impossibile autenticarsi.")


def fetch_badges(client):
    """Recupera i badge guadagnati con get_earned_badges()."""
    try:
        earned = client.get_earned_badges()
        print(f"Badge guadagnati: {len(earned)}")
        return earned
    except Exception as e:
        print(f"Errore badge: {e}")
        return []


def fetch_challenges(client):
    """
    Recupera le sfide mensili.
    Le sfide sono badge "available" con date di inizio/fine
    e valori di progresso (badgeProgressValue / badgeTargetValue).
    """
    challenges = []

    # 1. Badge challenges in corso
    try:
        available = client.get_available_badge_challenges()
        print(f"Badge challenges disponibili: {len(available)}")
        for c in available:
            challenges.append({
                "challengeName": c.get("badgeChallengeName", c.get("badgeName", "Sfida")),
                "challengeDescription": c.get("description", ""),
                "imageUrl": c.get("badgeSmallImageUrl", c.get("badgeImageUrl", "")),
                "startDate": c.get("startDate", ""),
                "endDate": c.get("endDate", ""),
                "challengeTarget": c.get("badgeTargetValue", 0),
                "currentValue": c.get("badgeProgressValue", 0),
                "statusType": "ACTIVE",
            })
    except Exception as e:
        print(f"Errore badge challenges: {e}")

    # 2. Sfide virtuali in corso
    try:
        virtual = client.get_inprogress_virtual_challenges()
        print(f"Sfide virtuali in corso: {len(virtual)}")
        for c in virtual:
            challenges.append({
                "challengeName": c.get("challengeName", c.get("badgeName", "Sfida")),
                "challengeDescription": c.get("description", ""),
                "imageUrl": c.get("badgeSmallImageUrl", c.get("badgeImageUrl", "")),
                "startDate": c.get("startDate", ""),
                "endDate": c.get("endDate", ""),
                "challengeTarget": c.get("badgeTargetValue", c.get("challengeTarget", 0)),
                "currentValue": c.get("badgeProgressValue", c.get("currentValue", 0)),
                "statusType": "ACTIVE",
            })
    except Exception as e:
        print(f"Errore sfide virtuali: {e}")

    # 3. Available badges che sono sfide mensili (hanno date e target)
    try:
        available_badges = client.get_available_badges()
        monthly = [
            b for b in available_badges
            if b.get("badgeStartDate") and b.get("badgeTargetValue")
        ]
        print(f"Sfide mensili (da available badges): {len(monthly)}")
        for c in monthly:
            # Evita duplicati (stesso nome)
            name = c.get("badgeName", "Sfida")
            if not any(ch["challengeName"] == name for ch in challenges):
                challenges.append({
                    "challengeName": name,
                    "challengeDescription": "",
                    "imageUrl": c.get("badgeSmallImageUrl", c.get("badgeImageUrl", "")),
                    "startDate": c.get("badgeStartDate", ""),
                    "endDate": c.get("badgeEndDate", ""),
                    "challengeTarget": c.get("badgeTargetValue", 0),
                    "currentValue": c.get("badgeProgressValue", 0),
                    "statusType": "ACTIVE",
                })
    except Exception as e:
        print(f"Errore available badges: {e}")

    # 4. Non-completed badge challenges
    try:
        non_completed = client.get_non_completed_badge_challenges()
        print(f"Badge challenges non completate: {len(non_completed)}")
        for c in non_completed:
            name = c.get("badgeChallengeName", c.get("badgeName", "Sfida"))
            if not any(ch["challengeName"] == name for ch in challenges):
                challenges.append({
                    "challengeName": name,
                    "challengeDescription": c.get("description", ""),
                    "imageUrl": c.get("badgeSmallImageUrl", c.get("badgeImageUrl", "")),
                    "startDate": c.get("startDate", ""),
                    "endDate": c.get("endDate", ""),
                    "challengeTarget": c.get("badgeTargetValue", 0),
                    "currentValue": c.get("badgeProgressValue", 0),
                    "statusType": "ACTIVE",
                })
    except Exception as e:
        print(f"Errore non-completed challenges: {e}")

    # Segna come completate quelle al 100%
    for ch in challenges:
        target = ch.get("challengeTarget", 0)
        current = ch.get("currentValue", 0)
        if target and current and current >= target:
            ch["statusType"] = "COMPLETED"

    completate = sum(1 for c in challenges if c["statusType"] == "COMPLETED")
    print(f"Sfide totali: {len(challenges)} ({completate} completate)")
    return challenges


def main():
    if not TOKEN_B64 and not (EMAIL and PASSWORD):
        print("ERRORE: Nessuna credenziale configurata!")
        raise SystemExit(1)

    client = get_client()
    badges = fetch_badges(client)
    challenges = fetch_challenges(client)

    output = {
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "badges": badges,
        "challenges": challenges,
    }

    with open("badges.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nbadges.json aggiornato: {len(badges)} badge, {len(challenges)} sfide.")


if __name__ == "__main__":
    main()
