"""
Garmin Badge & Challenge Fetcher — Versione definitiva
Scarica badge guadagnati e sfide mensili da Garmin Connect.

Logica sfide:
  - get_available_badges() → catalogo sfide con target (ma senza progresso)
  - get_in_progress_badges() → sfide in corso con progresso reale
  - get_earned_badges() → sfide completate
  I dati vengono incrociati per badgeId per avere il quadro completo.
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

# URL base per le immagini dei badge Garmin
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
        print(f"Token ripristinato: {list(token_data.keys())}")
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


def format_badge(b):
    """Formatta un badge earned per il JSON output."""
    uuid = b.get("badgeUuid", "")
    return {
        "badgeId": b.get("badgeId"),
        "badgeName": b.get("badgeName", "Badge"),
        "badgeUuid": uuid,
        "imageUrl": BADGE_IMG_URL.format(uuid=uuid) if uuid else "",
        "badgeEarnedDate": b.get("badgeEarnedDate"),
        "badgePoints": b.get("badgePoints", 0),
        "badgeCategoryId": b.get("badgeCategoryId"),
        "badgeDifficultyId": b.get("badgeDifficultyId"),
    }


def format_challenge(b, status, progress=None, target=None):
    """Formatta una sfida per il JSON output."""
    uuid = b.get("badgeUuid", "")
    return {
        "badgeId": b.get("badgeId"),
        "challengeName": b.get("badgeName", "Sfida"),
        "badgeUuid": uuid,
        "imageUrl": BADGE_IMG_URL.format(uuid=uuid) if uuid else "",
        "startDate": b.get("badgeStartDate", ""),
        "endDate": b.get("badgeEndDate", ""),
        "challengeTarget": target if target is not None else (b.get("badgeTargetValue") or 0),
        "currentValue": progress if progress is not None else (b.get("badgeProgressValue") or 0),
        "badgeUnitId": b.get("badgeUnitId"),
        "statusType": status,
    }


def fetch_badges(client):
    """Recupera i badge guadagnati (non-sfida)."""
    try:
        earned = client.get_earned_badges()
        print(f"Badge guadagnati totali: {len(earned)}")
        return [format_badge(b) for b in earned]
    except Exception as e:
        print(f"Errore badge: {e}")
        return []


def fetch_challenges(client):
    """
    Recupera le sfide mensili incrociando 3 endpoint:
    1. available_badges → catalogo (target, date)
    2. in_progress_badges → progresso reale per sfide attive
    3. earned_badges → sfide completate di recente
    """
    challenges = []

    # 1. Catalogo: tutte le sfide disponibili con date
    available = {}
    try:
        ab = client.get_available_badges()
        for b in ab:
            if b.get("badgeStartDate") and b.get("badgeTargetValue"):
                available[b["badgeId"]] = b
        print(f"Sfide nel catalogo: {len(available)}")
    except Exception as e:
        print(f"Errore available badges: {e}")

    # 2. In-progress: sfide attive con progresso
    in_progress = {}
    try:
        ip = client.get_in_progress_badges()
        for b in ip:
            in_progress[b["badgeId"]] = b
        print(f"Badge in-progress: {len(in_progress)}")
    except Exception as e:
        print(f"Errore in-progress: {e}")

    # 3. Earned recenti: sfide completate (ultimi 90 giorni)
    earned_recent = {}
    try:
        eb = client.get_earned_badges()
        cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
        for b in eb:
            date = b.get("badgeEarnedDate", "")
            if date and date > cutoff and b.get("badgeTargetValue"):
                earned_recent[b["badgeId"]] = b
        print(f"Sfide completate (ultimi 90gg): {len(earned_recent)}")
    except Exception as e:
        print(f"Errore earned badges: {e}")

    # Unisci i badge IDs da tutti e tre gli endpoint
    all_ids = set(available.keys()) | set(in_progress.keys()) | set(earned_recent.keys())

    seen_ids = set()
    for bid in all_ids:
        if bid in seen_ids:
            continue

        # Priorità: earned > in_progress > available
        if bid in earned_recent:
            b = earned_recent[bid]
            # Prendi le date dal catalogo se disponibili
            cat = available.get(bid, {})
            if cat:
                b.setdefault("badgeStartDate", cat.get("badgeStartDate"))
                b.setdefault("badgeEndDate", cat.get("badgeEndDate"))
            challenges.append(format_challenge(
                b, "COMPLETED",
                progress=b.get("badgeProgressValue") or b.get("badgeTargetValue"),
                target=b.get("badgeTargetValue"),
            ))
            seen_ids.add(bid)

        elif bid in in_progress:
            b = in_progress[bid]
            # Solo se ha un target (è una sfida, non un badge normale)
            if b.get("badgeTargetValue"):
                cat = available.get(bid, {})
                if cat:
                    b.setdefault("badgeStartDate", cat.get("badgeStartDate"))
                    b.setdefault("badgeEndDate", cat.get("badgeEndDate"))
                challenges.append(format_challenge(
                    b, "ACTIVE",
                    progress=b.get("badgeProgressValue") or 0,
                    target=b.get("badgeTargetValue"),
                ))
                seen_ids.add(bid)

        elif bid in available:
            b = available[bid]
            # Sfida disponibile ma non iniziata/iscritta
            challenges.append(format_challenge(b, "NOT_JOINED"))
            seen_ids.add(bid)

    completate = sum(1 for c in challenges if c["statusType"] == "COMPLETED")
    attive = sum(1 for c in challenges if c["statusType"] == "ACTIVE")
    disponibili = sum(1 for c in challenges if c["statusType"] == "NOT_JOINED")
    print(f"Sfide totali: {len(challenges)} "
          f"({completate} completate, {attive} attive, {disponibili} disponibili)")

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

    print(f"\nbadges.json: {len(badges)} badge, {len(challenges)} sfide.")


if __name__ == "__main__":
    main()
