"""
Garmin Badge & Challenge Fetcher
Scarica badge guadagnati e sfide mensili da Garmin Connect,
salvandoli in JSON per la dashboard su Netlify.
"""

import json
import os
from datetime import datetime
from garminconnect import Garmin

# Credenziali dalle variabili d'ambiente di GitHub Actions
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

# Percorso per salvare/ripristinare il token di sessione
TOKEN_DIR = os.path.expanduser("~/.garth")


def get_client():
    """
    Crea un client Garmin con gestione del token.
    Prima prova a ripristinare una sessione salvata,
    se fallisce fa login con email e password.
    """
    client = Garmin(EMAIL, PASSWORD)

    # Prova a ripristinare la sessione precedente
    if os.path.exists(TOKEN_DIR):
        try:
            client.login(TOKEN_DIR)
            print("Sessione ripristinata dal token salvato.")
            return client
        except Exception:
            print("Token scaduto, nuovo login in corso...")

    # Login fresco con credenziali
    client.login()
    # Salva il token per le prossime esecuzioni
    client.garth.dump(TOKEN_DIR)
    print("Login effettuato e token salvato.")
    return client


def fetch_badges(client):
    """Recupera i badge guadagnati."""
    try:
        all_badges = client.get_badges()
        earned = [b for b in all_badges if b.get("badgeEarnedDate") is not None]
        print(f"Badge guadagnati: {len(earned)} su {len(all_badges)} totali.")
        return earned
    except Exception as e:
        print(f"Errore nel recupero badge: {e}")
        return []


def fetch_challenges(client):
    """
    Recupera le sfide (challenges) mensili.
    Usa l'endpoint interno di Garmin Connect.
    """
    try:
        # Sfide a cui sei iscritto (attive e completate)
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
                # COMPLETED = obiettivo raggiunto, ACTIVE = in corso
            })

        completate = sum(1 for c in challenges if c["statusType"] == "COMPLETED")
        print(f"Sfide trovate: {len(challenges)} ({completate} completate).")
        return challenges

    except Exception as e:
        print(f"Errore nel recupero sfide: {e}")
        print("(L'endpoint potrebbe non essere disponibile per il tuo account)")
        return []


def main():
    if not EMAIL or not PASSWORD:
        print("ERRORE: Variabili GARMIN_EMAIL e GARMIN_PASSWORD non impostate!")
        return

    client = get_client()

    badges = fetch_badges(client)
    challenges = fetch_challenges(client)

    # Crea un unico file JSON con timestamp
    output = {
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "badges": badges,
        "challenges": challenges,
    }

    with open("badges.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"File badges.json aggiornato alle {output['lastUpdated']}")


if __name__ == "__main__":
    main()
