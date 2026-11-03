# iPhone Stock Checker — Cloud Monitor

Monitor Apple Store iPhone pickup availability and receive email alerts when a selected configuration becomes available. Monitoring runs in GitHub Actions, triggered by cron-job.org; the watchlist is managed through a GitHub Pages website. **Your personal computer does not need to be on.**

> Apple pickup availability is not a reservation. Apple's inventory service is unofficial and may change or rate-limit requests. A five-minute schedule is a request, not a guaranteed execution time.

## Quick links

| Task | Link |
| --- | --- |
| **Manage phones and notification emails** | **[Open iPhone Watchlist Manager](https://petebeax.github.io/iphone_stock_checker/)** |
| View workflow runs and logs | [GitHub Actions — iPhone Stock Checker](https://github.com/petebeax/iphone_stock_checker/actions/workflows/iphone-stock-checker.yml) |
| Manage the external schedule | [cron-job.org console](https://console.cron-job.org/) |
| Update workflow secrets | [Repository Actions secrets](https://github.com/petebeax/iphone_stock_checker/settings/secrets/actions) |
| View the repository | [Source code](https://github.com/petebeax/iphone_stock_checker) |

## Add or edit an iPhone alert

1. Open **[iPhone Watchlist Manager](https://petebeax.github.io/iphone_stock_checker/)** from a personal, trusted device.
2. Enter the **encryption passphrase** that matches the GitHub Actions secret `WATCHLIST_PASSPHRASE` and your **fine-grained GitHub token** with **Contents: read and write** access to this repository. These are separate from the token used by cron-job.org.
3. Choose **Load existing alerts** to preserve and edit your saved configurations. Use **Start new watchlist** only when you intentionally want to replace the existing list.
4. Add or edit each alert's iPhone model, storage, colour, location, monitored stores and **notification email address**. Different alerts can notify different recipients.
5. Click **Save watchlist to GitHub**. The manager writes an encrypted `secure_watchlist.json` file; never put unencrypted recipient lists, passphrases or tokens into repository files.
6. Open the next GitHub Actions run and inspect **Check and notify** to verify it reports the expected number of watches (e.g., `Finished: 2 watch(es), ...`). A successful run does not necessarily send email when no new availability is found.

**Important:** The existing `WATCHLIST_JSON` secret is only a fallback until an encrypted watchlist has been saved. Once using `secure_watchlist.json`, manage alerts through the website; don't keep editing two separate lists. Keep a secure backup of your passphrase. Losing it can make the encrypted watchlist unrecoverable.

## How automatic monitoring works

1. **cron-job.org** sends an authenticated HTTP POST request approximately every **5 minutes**.
2. The GitHub Actions `workflow_dispatch` trigger starts `cloud_monitor.py` on `main`.
3. The monitor reads and decrypts `secure_watchlist.json`, checks pickup availability for each saved configuration, and sends Gmail alerts when new availability is detected.
4. Notification history is retained to reduce repeat alerts for unchanged availability.

Externally triggered runs may display **“Manually run”** in GitHub because they use the workflow-dispatch API, even though cron-job.org initiated them automatically. To confirm the schedule is active, check **both** cron-job.org execution history and the corresponding GitHub Actions runs. A successful cron HTTP response confirms GitHub accepted the dispatch, not that the stock check succeeded.

## Verify monitoring and test notifications

- **Is it checking?** Open [GitHub Actions history](https://github.com/petebeax/iphone_stock_checker/actions/workflows/iphone-stock-checker.yml). Open a recent run and expand **Check and notify**; verify the expected watch count and store-check messages.
- **Is it triggered regularly?** Open [cron-job.org](https://console.cron-job.org/) and inspect the job's **Enabled** setting, five-minute schedule, and execution history.
- **Does Gmail work?** In GitHub Actions, choose **Run workflow**, select `test_email` and inspect the **Send test email** step and your inbox. The normal `check_stock` mode does not guarantee an email if stock is unavailable or already reported.
- **Need an immediate stock check?** Choose **Run workflow → check_stock** in GitHub Actions.

Do not enable both the original GitHub `schedule:` trigger and the external cron job unless duplicate runs are intentional. The external approach needs `workflow_dispatch:` retained in the workflow YAML.

## Credentials and security

| Item | Where it belongs | Purpose |
| --- | --- | --- |
| `SMTP_USER`, `SMTP_PASSWORD` | GitHub Actions Secrets | Gmail sender account and app password |
| `WATCHLIST_PASSPHRASE` | GitHub Actions Secret and supplied manually in the manager | Decrypt encrypted watchlist |
| Watchlist-manager token | Enter into manager when editing; keep in password manager | Fine-grained token with **Contents: read and write**, restricted to this repository |
| cron-job.org token | cron-job.org authorization header | Separate fine-grained token with **Actions: read and write**, restricted to this repository |
| `secure_watchlist.json` | Repository | Encrypted watchlist; never commit plaintext watchlists |

**This is a public repository and the GitHub Pages management URL is public.** The page is not a traditional password-protected login portal. Do not enter tokens on lookalike websites; protect your GitHub account with MFA, restrict and rotate tokens, and review repository files **and commit history** for exposed credentials or personal information.

GitHub Pages itself hosts only the management interface; **GitHub Actions runs the checker**. Changing the webpage does not change the monitoring frequency.

## Costs, reliability and limitations

- Standard GitHub-hosted runners for a public repository generally do not incur standard Actions-minute charges, subject to GitHub's current terms and abuse limits. Check billing before changing repository visibility or runner type.
- cron-job.org is an external scheduling dependency. Its requests, GitHub runner starts and Apple availability checks can be delayed or fail.
- Apple may rate-limit or change its undocumented inventory endpoint. Limit unnecessary duplicate watches and investigate repeated errors in workflow logs.
- Avoid sending unsolicited email to others; use recipients who expect these alerts.

## Optional legacy local version

Some files (`app.py`, `monitor.py`, `watchlist.py`) support the earlier Windows/Streamlit version. It is **not required** for the cloud workflow. If you use the cloud manager and cron-job.org, you do not need to keep your computer awake or run Windows Task Scheduler.

---

**Main entry point:** [Manage my iPhone watchlist](https://petebeax.github.io/iphone_stock_checker/)
