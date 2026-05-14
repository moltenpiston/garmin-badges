"""
Garmin Badge & Challenge Fetcher
Scarica badge e sfide mensili da Garmin Connect.
Usa un token pre-generato (GARMIN_TOKEN) per evitare
il rate limit sugli IP di GitHub Actions.
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
    """Decodifica il token base64 e lo salva su disco."""
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
    """
    Crea un client Garmin autenticato.
    1. Prova con il token salvato (garth.resume)
    2. Fallback: login diretto con email/password
    """
    # Strategia 1: token
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
            print("Rigenera il token con genera_token.py sul tuo PC.")

    # Strategia 2: login diretto
    if EMAIL and PASSWORD:
        print("Tentativo login diretto...")
        try:
            client = Garmin(EMAIL, PASSWORD)
            client.login()
            print("Login diretto riuscito.")
            return client
        except Exception as e:
            print(f"Login diretto fallito: {e}")

    raise RuntimeError("Impossibile autenticarsi. Configura il secret GARMIN_TOKEN.")


def fetch_badges(client):
    """Recupera i badge guadagnati."""
    try:
        all_badges = client.get_badges()
        earned = [b for b in all_badges if b.get("badgeEarnedDate") is not None]
        print(f"Badge: {len(earned)} guadagnati su {len(all_badges)} totali.")
        return earned
    except Exception as e:
        print(f"Errore badge: {e}")
        return []


def fetch_challenges(client):
    """Recupera le sfide mensili (attive e completate)."""
    try:
        enrolled = client.connectapi(
            "/badgechallenge-service/badgeChallenge/enrolled"
        )

        challenges = []
        for c in enrolled:
            challenges.append({
                "challengeId": c.get("challengeId"),
                "challengeName": c.get("challengeName", "Sfida senza nome"),
                "challengeDescription": c.get("description", ""),
                "imageUrl": c.get("badgeImageUrl", ""),
                "startDate": c.get("startDate", ""),
                "endDate": c.get("endDate", ""),
                "challengeTarget": c.get("challengeTarget", 0),
                "currentValue": c.get("currentValue", 0),
                "statusType": c.get("challengeStatusType", "ACTIVE"),
            })

        completate = sum(1 for c in challenges if c["statusType"] == "COMPLETED")
        print(f"Sfide: {len(challenges)} trovate ({completate} completate).")
        return challenges

    except Exception as e:
        print(f"Errore sfide: {e}")
        return []


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
