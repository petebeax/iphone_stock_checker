# iPhone Stock Checker — Canada (v2.1, faster checks)

A small local **Streamlit** app that checks Apple Store pickup availability for a selected iPhone configuration and sends **email and/or SMS alerts** when that configuration becomes available. The app uses Apple's **unofficial, undocumented** storefront endpoint, which may change.

## 1. Install and run (Windows PowerShell)

Use **Python 3.12 (64-bit)**. Open PowerShell in the folder containing `app.py` and `requirements.txt`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**. If you already installed the original app, extract the **new zip into a new folder** and use the above commands. Do not copy over any old `.env` or watchlist without checking contents; if you want your existing config, transfer the `.env` yourself.

## 2. Choose the correct model / colour

Select your model, storage, then colour. **Selections react immediately without pressing Check**, and the colour dropdown only contains colours that Apple lists for that *model and storage*. If Apple's catalogue changes, click **Reload models**. The catalogue is cached for 1 hour and stock checks for up to 60 seconds in the browser.

Click **Check pickup availability** to see nearby stores. The app displays the Apple part number and shows a warning if the results refer to an older selection. Manual Apple part number entry remains available.

## 3. Set up email notification (recommended first)

The app can send mail via your own email account's SMTP server. To use Gmail, enable 2-Step Verification and generate a Google **App Password** (a normal account password is not suitable for SMTP automation). Some managed Google accounts may not permit app passwords.

1. Copy `.env.example` to `.env` in the **same folder as `app.py`**.
2. Fill in `SMTP_USER` (your sending address), `SMTP_PASSWORD` (app password), and `EMAIL_FROM`. The sample already has Gmail host `smtp.gmail.com`, port `587`.
3. **Restart Streamlit** after modifying `.env` so the credentials are reloaded.
4. In the app, click **Check pickup availability**, select **Notify by email**, enter your recipient address, and click **Send test notification**. Once the test arrives, click **Save alert**.

Do **not** publish `.env`, share it in a ZIP, or paste a password into chat. `.env` and `data/` are intentionally ignored by Git.

## 4. Optional SMS notification (Twilio)

To send actual SMS, you need a Twilio account, an SMS-enabled Twilio sending number, and the account SID/auth token. Add these keys to `.env`:

```ini
TWILIO_ACCOUNT_SID=AC...your SID...
TWILIO_AUTH_TOKEN=your-secret-token
TWILIO_FROM=+1yourTwilioNumber
```

Restart Streamlit; choose **Notify by SMS**, enter the recipient in international format such as `+14165550123`, and send a test. A Twilio trial may require **verifying the destination number**, and **SMS charges may apply**. You can enable both email and SMS on the same watch.

[Twilio Messages API documentation](https://www.twilio.com/docs/messaging/api/message-resource)

## 5. Start checking in the background (Windows Task Scheduler)

**Saving an alert does not start a background service.** You must run the monitor manually or install its scheduled task.

After saving an alert, check the monitor once:

```powershell
.\.venv\Scripts\python.exe monitor.py
```

If the item is already available, this **first check sends an alert immediately**. A later check won't send a duplicate while the store remains available. Once Apple explicitly reports *Unavailable*, that store becomes eligible for a new alert the next time it is available.

To register an automatic check **every 5 minutes** on your Windows PC (or update an existing 15-minute task):

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```

For example, to switch to **10 minutes**:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1 -IntervalMinutes 10
```

To use another interval (2–60 minutes), rerun the script with e.g. `-IntervalMinutes 10`. Five minutes is recommended; shorter intervals make rate limiting more likely, especially with multiple watches. The scheduled task calls `run_monitor.cmd`, which logs checks to `data\monitor.log`. You can verify and run it:

```powershell
schtasks /query /tn iPhoneStockChecker
schtasks /run /tn iPhoneStockChecker
Get-Content .\data\monitor.log -Tail 30
```

To remove the scheduled checker:

```powershell
schtasks /delete /tn iPhoneStockChecker /f
```

**Important:** Your PC must be switched on and awake; the Streamlit browser tab **does not** need to stay open. If Windows or antivirus blocks the scheduled task, open **Task Scheduler** and inspect the task's history. To run independently of your own computer, this app would need to be deployed to an always-on computer or cloud host.

**Be respectful of Apple's service:** The default interval is 5 minutes. Each saved alert performs its own lookup, so avoid many duplicate watches, and stop checking if rate-limited. An Apple HTTP 429/541 response means the tool should back off for at least 15–30 minutes.

## 6. How alerting works

- Watches are saved locally in `data/watchlist.json` (contains recipients but no passwords).
- Each watch identifies an exact **model, storage, colour / part number, location**, plus **any nearby store** or specific chosen stores.
- Notifications fire for each newly available store, but **are batched into one email or SMS per watch and check**, so multiple stores appearing at once result in one alert per channel.
- A store must explicitly be reported `Unavailable` before that store will trigger another alert. `Unknown`, missing store results, connectivity errors, and Apple rate-limiting **never** rearm or mark a store unavailable.
- If email succeeds but SMS fails, only the unsuccessful channel retries on the next check. Sending is best-effort: an interruption after delivery but before saving state can still cause a duplicate.
- Email and SMS mean *pickup availability*, not held inventory or a reservation. Confirm the exact configuration directly in Apple's checkout.
- The app itself is a local personal tool, not a production-grade monitoring service; don't expose its Streamlit port publicly because saved recipients are visible to anyone with access to the UI.

## Troubleshooting and tests

Run all offline tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
```

If the old NumPy/PyArrow conflict recurs, create a new `.venv` and install from `requirements.txt` instead of relying on globally installed packages. If the model catalogue fails to parse, use the manual part-number mode until the site's HTML parser is updated. No live Apple, email or Twilio calls are performed by tests.
