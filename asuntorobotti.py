import feedparser
import smtplib
import os
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from anthropic import Anthropic

# --- Asetukset ---
RSS_URL = "https://asunnot.oikotie.fi/myytavat-asunnot?locations=%5B%5B64,6,%22Helsinki%22%5D%5D&price=0-400000&format=rss"
SEEN_FILE = "seen.txt"

KRITEERIT = """
- Hinta: mieluiten alle 350 000€ (paras alle 300 000€)
- Koko: vähintään 55 m²
- Sijainti: Helsinki tai Espoo, lähellä metroa tai junaa
- Yhtiövastike: maksimissaan 500€/kk
- Rakennusvuosi: mieluiten 1990 jälkeen
"""

# --- API-avaimet (tulevat GitHub Secretseistä) ---
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS    = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
EMAIL_TO         = os.environ["EMAIL_TO"]


def lataa_nähdy() -> set:
    """Lataa jo nähtyjen asuntojen URL-lista tiedostosta."""
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def tallenna_nähty(url: str):
    """Lisää URL nähtyjen listaan."""
    with open(SEEN_FILE, "a") as f:
        f.write(url + "\n")


def arvioi_asunto(otsikko: str, kuvaus: str, url: str) -> str:
    """Lähettää asunnon tiedot Claudelle ja palauttaa arvion."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Olet asuntoarviointirobotti. Arvioi alla oleva asuntoilmoitus kriteereideni perusteella.

KRITEERINI:
{KRITEERIT}

ASUNNON TIEDOT:
Otsikko: {otsikko}
Kuvaus: {kuvaus}
Linkki: {url}

ANNA ARVIO TÄSSÄ MUODOSSA:
KOKONAISARVOSANA: X/10
HINTA: X/10 — [kommentti]
SIJAINTI: X/10 — [kommentti]
KOKO: X/10 — [kommentti]
YHTEENVETO: [2-3 lausetta]
SUOSITUS: KATSO HETI / EHKÄ / OHITA"""

    viesti = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return viesti.content[0].text


def lähetä_sähköposti(otsikko: str, arvio: str, url: str):
    """Lähettää arvion sähköpostiin Gmailin kautta."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 Uusi asunto: {otsikko}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = EMAIL_TO

    # Tekstiversio
    teksti = f"{otsikko}\n\n{arvio}\n\nLinkki: {url}"

    # HTML-versio
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#1d4ed8;">🏠 {otsikko}</h2>
      <pre style="background:#f8fafc;padding:16px;border-radius:8px;
                  white-space:pre-wrap;font-size:14px;">{arvio}</pre>
      <a href="{url}" style="display:inline-block;margin-top:16px;
         background:#1d4ed8;color:white;padding:10px 22px;
         border-radius:8px;text-decoration:none;">
        → Avaa ilmoitus Oikotiellä
      </a>
    </div>
    """

    msg.attach(MIMEText(teksti, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, EMAIL_TO, msg.as_string())
    print(f"  ✅ Sähköposti lähetetty: {otsikko}")


def main():
    print("🔍 Haetaan asuntoja RSS-syötteestä...")
    syöte = feedparser.parse(RSS_URL)
    nähdy = lataa_nähdy()

    uusia = 0
    for kohde in syöte.entries:
        url     = kohde.get("link", "")
        otsikko = kohde.get("title", "Ei otsikkoa")
        kuvaus  = kohde.get("summary", "")

        if url in nähdy:
            print(f"  ⏭ Jo nähty: {otsikko}")
            continue

        print(f"  🆕 Uusi asunto: {otsikko}")
        arvio = arvioi_asunto(otsikko, kuvaus, url)
        print(f"  🧠 Arvio saatu")

        # Lähetetään vain jos suositus ei ole OHITA
        if "OHITA" not in arvio.upper():
            lähetä_sähköposti(otsikko, arvio, url)
        else:
            print(f"  🚫 Ohitetaan (ei sähköpostia)")

        tallenna_nähty(url)
        uusia += 1

    print(f"\n✨ Valmis! Uusia asuntoja: {uusia} / {len(syöte.entries)}")


if __name__ == "__main__":
    main()
