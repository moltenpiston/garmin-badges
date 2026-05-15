"""
Garmin Badge & Challenge Fetcher — Versione corretta
Scarica badge guadagnati e sfide mensili da Garmin Connect.

Logica sfide:
  - get_non_completed_badge_challenges(1, limit) → sfide ATTIVE con progresso reale
  - get_badge_challenges(1, limit) → tutte le sfide (per quelle completate)
  - get_available_badges() → sfide disponibili non iscritte
  I dati vengono uniti evitando duplicati.
"""

import json
import os
import base64
import tempfile
import shutil
from datetime import datetime, timedelta

import garth
from garminconnect import Garmin

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_B64 = os.getenv("GARMIN_TOKEN")

BADGE_IMG_URL = "https://connect.garmin.com/images/badges/xxhdpi/badge_{uuid}_lrg.png"


def restore_token():
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
            with open(os.path.join(token_dir, filename), "w", encoding="utf-8") as f:
                f.write(content)
        return token_dir
    except Exception as e:
        print(f"Errore token: {e}")
        return None


def get_client():
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

    if EMAIL and PASSWORD:
        try:
            client = Garmin(EMAIL, PASSWORD)
            client.login()
            print("Login diretto riuscito.")
            return client
        except Exception as e:
            print(f"Login diretto fallito: {e}")

    raise RuntimeError("Impossibile autenticarsi.")


def make_image_url(uuid):
    return BADGE_IMG_URL.format(uuid=uuid) if uuid else ""


def fetch_badges(client):
    """Recupera i badge guadagnati."""
    try:
        earned = client.get_earned_badges()
        print(f"Badge guadagnati: {len(earned)}")
        result = []
        for b in earned:
            uuid = b.get("badgeUuid", "")
            result.append({
                "badgeId": b.get("badgeId"),
                "badgeName": b.get("badgeName", "Badge"),
                "badgeUuid": uuid,
                "imageUrl": make_image_url(uuid),
                "badgeEarnedDate": b.get("badgeEarnedDate"),
                "badgePoints": b.get("badgePoints", 0),
                "badgeCategoryId": b.get("badgeCategoryId"),
            })
        return result
    except Exception as e:
        print(f"Errore badge: {e}")
        return []


def fetch_challenges(client):
    """
    Recupera le sfide mensili da 3 fonti:
    1. get_non_completed_badge_challenges → sfide attive CON progresso reale
    2. get_badge_challenges → sfide completate
    3. get_available_badges → sfide disponibili ma non iscritte
    """
    challenges = {}  # badgeId → challenge dict

    # 1. SFIDE ATTIVE con progresso reale (fonte principale!)
    try:
        active = client.get_non_completed_badge_challenges(1, 200)
        print(f"Sfide attive (non completate): {len(active)}")
        for c in active:
            bid = c.get("badgeId")
            if not bid:
                continue
            uuid = c.get("badgeUuid", "")
            challenges[bid] = {
                "badgeId": bid,
                "challengeName": c.get("badgeChallengeName", c.get("badgeName", "Sfida")),
                "badgeUuid": uuid,
                "imageUrl": make_image_url(uuid),
                "startDate": c.get("startDate", ""),
                "endDate": c.get("endDate", ""),
                "challengeTarget": c.get("badgeTargetValue") or 0,
                "currentValue": c.get("badgeProgressValue") or 0,
                "badgeUnitId": c.get("badgeUnitId"),
                "statusType": "ACTIVE",
            }
    except Exception as e:
        print(f"Errore sfide attive: {e}")

    # 2. SFIDE COMPLETATE (ultimi 12 mesi)
    try:
        all_bc = client.get_badge_challenges(1, 200)
        cutoff = (datetime.utcnow() - timedelta(days=365)).isoformat()
        completed = [
            c for c in all_bc
            if c.get("badgeEarnedDate") and c.get("badgeEarnedDate", "") > cutoff
        ]
        print(f"Sfide completate (ultimo anno): {len(completed)}")
        for c in completed:
            bid = c.get("badgeId")
            if not bid or bid in challenges:
                continue
            uuid = c.get("badgeUuid", "")
            challenges[bid] = {
                "badgeId": bid,
                "challengeName": c.get("badgeChallengeName", c.get("badgeName", "Sfida")),
                "badgeUuid": uuid,
                "imageUrl": make_image_url(uuid),
                "startDate": c.get("startDate", ""),
                "endDate": c.get("endDate", ""),
                "challengeTarget": c.get("badgeTargetValue") or 0,
                "currentValue": c.get("badgeProgressValue") or c.get("badgeTargetValue") or 0,
                "badgeUnitId": c.get("badgeUnitId"),
                "statusType": "COMPLETED",
            }
    except Exception as e:
        print(f"Errore sfide completate: {e}")

    # 3. SFIDE DISPONIBILI (non iscritte)
    try:
        available = client.get_available_badges()
        monthly = [
            b for b in available
            if b.get("badgeStartDate") and b.get("badgeTargetValue")
        ]
        print(f"Sfide disponibili (non iscritte): {len(monthly)}")
        for b in monthly:
            bid = b.get("badgeId")
            if not bid or bid in challenges:
                continue
            uuid = b.get("badgeUuid", "")
            challenges[bid] = {
                "badgeId": bid,
                "challengeName": b.get("badgeName", "Sfida"),
                "badgeUuid": uuid,
                "imageUrl": make_image_url(uuid),
                "startDate": b.get("badgeStartDate", ""),
                "endDate": b.get("badgeEndDate", ""),
                "challengeTarget": b.get("badgeTargetValue") or 0,
                "currentValue": 0,
                "badgeUnitId": b.get("badgeUnitId"),
                "statusType": "NOT_JOINED",
            }
    except Exception as e:
        print(f"Errore sfide disponibili: {e}")

    result = list(challenges.values())
    completate = sum(1 for c in result if c["statusType"] == "COMPLETED")
    attive = sum(1 for c in result if c["statusType"] == "ACTIVE")
    disponibili = sum(1 for c in result if c["statusType"] == "NOT_JOINED")
    print(f"Sfide totali: {len(result)} "
          f"({completate} completate, {attive} attive, {disponibili} disponibili)")
    return result


def main():
    if not TOKEN_B64 and not (EMAIL and PASSWORD):
        print("ERRORE: Nessuna credenziale!")
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

    print(f"\nbadges.json: {len(badges)} badge, {len(challenges)} sfide.")


if __name__ == "__main__":
    main()
