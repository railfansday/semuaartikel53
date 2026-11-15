import os
import sqlite3
import smtplib
import time
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- KONFIGURASI ---
DB_PATH = "database.sqlite"
SENT_LOG_FILE = "blogger_sent.txt"
MAX_POSTS_PER_RUN = 5  # Maksimal artikel yang dikirim setiap kali build agar aman dari limit Gmail

GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
if "/" in GH_REPO:
    gh_owner, gh_name = GH_REPO.split("/", 1)
    BASE_URL = f"https://{gh_owner.lower()}.github.io/{gh_name}"
else:
    BASE_URL = "https://railfansday.github.io/semuaartikel53"


def get_sent_ids():
    if not os.path.exists(SENT_LOG_FILE):
        return set()
    with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip().isdigit()}


def save_sent_id(artikel_id):
    with open(SENT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{artikel_id}\n")


def clean_article_html(konten_html):
    soup = BeautifulSoup(konten_html, "html.parser")
    # Hapus semua tag script dan div iklan agar email bersih
    for script in soup(["script", "style"]):
        script.decompose()
    body_div = soup.find("div", class_="article-body")
    if body_div:
        return str(body_div)
    return str(soup)


def send_to_blogger():
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    blogger_email = os.environ.get("BLOGGER_SECRET_EMAIL")

    if not all([gmail_user, gmail_pass, blogger_email]):
        print("[SKIP] Secrets (GMAIL_USER, GMAIL_APP_PASSWORD, BLOGGER_SECRET_EMAIL) belum lengkap.")
        return

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database {DB_PATH} tidak ditemukan.")
        return

    sent_ids = get_sent_ids()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, judul, konten, gambar FROM artikel ORDER BY id DESC LIMIT 30")
    rows = cursor.fetchall()
    conn.close()

    # Filter hanya artikel yang belum pernah dikirim ke Blogspot
    unsent_articles = [row for row in rows if str(row[0]) not in sent_ids]

    if not unsent_articles:
        print("[INFO] Tidak ada artikel baru yang perlu dikirim ke Blogspot.")
        return

    # Ambil maksimal sesuai batas dan urutkan dari terlama ke terbaru agar urutan terbit rapi
    to_send = list(reversed(unsent_articles[:MAX_POSTS_PER_RUN]))

    print(f"[*] Ditemukan {len(unsent_articles)} artikel belum terkirim. Mengirim {len(to_send)} artikel ke Blogspot...")

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)

        for artikel_id, judul, konten, gambar in to_send:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = judul
            msg["From"] = gmail_user
            msg["To"] = blogger_email

            clean_body = clean_article_html(konten)
            portal_link = f"{BASE_URL}/index.html#artikel-{artikel_id}"
            img_tag = f'<div style="text-align:center;margin-bottom:16px;"><img src="{gambar}" alt="{judul}" style="max-width:100%;border-radius:8px;"/></div>' if gambar else ""

            html_payload = f"""
            {img_tag}
            {clean_body}
            <hr style="margin:20px 0;"/>
            <p><strong>Baca versi interaktif & ringkasan lengkap di:</strong> <a href="{portal_link}">{portal_link}</a></p>
            """

            msg.attach(MIMEText(html_payload, "html"))
            server.sendmail(gmail_user, blogger_email, msg.as_string())

            save_sent_id(artikel_id)
            print(f"[✅] Terkirim (#{artikel_id}): {judul[:50]}...")
            time.sleep(3)

        server.quit()
        print("\n[SELESAI] Sinkronisasi ke Blogspot selesai!")
    except Exception as e:
        print(f"[ERROR SMTP] Gagal mengirim ke Blogspot: {e}")


if __name__ == "__main__":
    send_to_blogger()
