"""Local Streamlit interface for Apple Canada pickup alerts.
Run: streamlit run app.py
"""

from __future__ import annotations

import requests
import streamlit as st

from notifications import configured_channels, email_valid, phone_valid, send_test
from stock_core import (
    FAMILIES, PART_RE, check_pickup, family_for_model, get_catalog,
    storage_sort_key, variants_for_model,
)
from watchlist import create_watch, delete_watch, load_watches


@st.cache_data(ttl=3600, show_spinner=False)
def cached_catalog() -> list[dict[str, str]]:
    return get_catalog()


@st.cache_data(ttl=60, show_spinner=False)
def cached_pickup(part: str, location: str, family: str) -> tuple[list[dict], str]:
    return check_pickup(part, location, family)


st.set_page_config(page_title="iPhone Stock Checker", page_icon="📱", layout="wide")
st.title("📱 iPhone Stock Checker")
st.caption("Apple Store pickup in Canada · Independent, unofficial checker")

col_loc, col_refresh = st.columns([5, 1], vertical_alignment="bottom")
with col_loc:
    location = st.text_input("Canadian city or postal code", value="Toronto", key="location")
with col_refresh:
    if st.button("Reload models", use_container_width=True, help="Re-fetch Apple's product catalogue"):
        cached_catalog.clear()
        st.rerun()

try:
    catalog = cached_catalog()
except (RuntimeError, requests.RequestException) as exc:
    catalog = []
    st.warning(f"Could not load Apple product variants: {exc}")

manual = st.checkbox("Enter an Apple part number manually (advanced)", value=not bool(catalog))
model = storage = color = ""
if manual:
    part = st.text_input("Apple part number", placeholder="Example: MJWA4VC/A").strip().upper()
    family_label = st.selectbox("Product family", list(FAMILIES))
    family = FAMILIES[family_label]
    model = family_label
elif catalog:
    # IMPORTANT: these selectors are OUTSIDE st.form, so model changes rerun the app.
    models = sorted({item["model"] for item in catalog}, reverse=True)
    model = st.selectbox("iPhone model", models, key="model")
    model_items = variants_for_model(catalog, model)
    sizes = sorted({item["storage"] for item in model_items}, key=storage_sort_key)
    storage = st.selectbox("Storage", sizes, key=f"storage:{model}")
    eligible = variants_for_model(catalog, model, storage)
    colors = sorted({item["color"] for item in eligible})
    color = st.selectbox("Colour", colors, key=f"color:{model}:{storage}")
    part = next(v["part"] for v in eligible if v["color"] == color)
    family = family_for_model(model)
    st.caption(f"Exact Apple part number: `{part}` · {len(colors)} colours available for this model/storage")
else:
    part = ""
    family = FAMILIES["iPhone 18 Pro / Pro Max"]
    st.info("Choose advanced mode to enter a part number if Apple's catalogue cannot be loaded.")

if st.button("Check pickup availability", type="primary", use_container_width=True):
    if not location.strip():
        st.error("Enter a city or postal code.")
    elif not PART_RE.fullmatch(part):
        st.error("Enter a valid Apple part number, or select a model and colour.")
    else:
        try:
            with st.spinner("Checking nearby Apple Stores…"):
                rows, checked = cached_pickup(part, location.strip(), family)
            st.session_state["last_result"] = {
                "rows": rows, "checked": checked, "part": part,
                "location": location.strip(), "family": family,
                "model": model, "storage": storage, "color": color,
            }
        except (RuntimeError, ValueError, requests.RequestException) as exc:
            st.error(f"Could not check pickup availability: {exc}")

result = st.session_state.get("last_result")
if result:
    rows = result["rows"]
    st.subheader(f"Last pickup query — {result['location']}")
    st.caption(
        f"{result['model']} {result['storage']} {result['color']} · "
        f"Part {result['part']} · Checked {result['checked']} · UI cache up to 60 seconds"
    )
    # A change in model, storage, colour, or location invalidates the usefulness of prior results.
    selection_is_current = (
        part == result["part"] and location.strip() == result["location"]
        and family == result["family"]
    )
    if not selection_is_current:
        st.warning("These are results for your previous selection. Click Check pickup availability to update them.")
    if rows:
        count = sum(r["Status"] == "Available" for r in rows)
        st.metric("Stores offering pickup", f"{count} / {len(rows)}")
        display = [{k: v for k, v in row.items() if k != "Store ID"} for row in rows]
        st.dataframe(
            display, use_container_width=True, hide_index=True,
            column_config={"Apple link": st.column_config.LinkColumn("Apple link", display_text="Open on Apple")},
        )
        if count:
            st.success("Pickup appears available at one or more stores. Confirm during Apple checkout.")
        elif any(r["Status"] == "Unknown" for r in rows):
            st.warning("Some stores reported unknown availability; don't assume those are sold out.")
        else:
            st.info("No nearby stores currently report pickup availability for this exact configuration.")
    else:
        st.info("Apple returned no nearby stores. Try a different search location.")

st.divider()
st.header("🔔 Stock alerts")
st.write(
    "Save a watch for an **exact iPhone variant**. The Windows scheduled checker can send an "
    "email or SMS when a chosen Apple Store reports pickup availability. "
    "It does not depend on keeping this browser tab open."
)
credentials = configured_channels()
st.caption(
    f"Email sending: {'configured' if credentials['email'] else 'not configured'} · "
    f"SMS sending: {'configured' if credentials['sms'] else 'not configured'} · "
    "Set credentials locally in `.env` (see README)."
)

if result and rows:
    if not selection_is_current:
        st.info("Run a new availability check for your current selection before saving an alert.")
    else:
        with st.container(border=True):
            st.subheader("Add an alert for this configuration")
            all_stores = st.checkbox("Watch any nearby Apple Store", value=True, key="watch_any")
            target_ids = []
            if not all_stores:
                labels = {f"{r['Store']} — {r['City']}": r["Store ID"] for r in rows}
                chosen = st.multiselect("Only these stores", list(labels), key="watch_store_choices")
                target_ids = [labels[label] for label in chosen]
            via_email = st.checkbox("Notify by email", value=True, key="via_email")
            email = st.text_input("Email recipient", placeholder="you@example.com", key="email_recipient") if via_email else ""
            via_sms = st.checkbox("Notify by SMS (Twilio)", value=False, key="via_sms")
            sms = st.text_input("SMS recipient (international format)", placeholder="+14165550123", key="sms_recipient") if via_sms else ""
            if via_sms:
                st.caption("SMS costs may apply. Twilio trial accounts must verify the recipient number.")

            a, b = st.columns(2)
            with a:
                save = st.button("Save alert", type="primary", use_container_width=True)
            with b:
                test = st.button("Send test notification", use_container_width=True)

            valid = (
                (all_stores or bool(target_ids))
                and ((via_email and email_valid(email)) or (via_sms and phone_valid(sms)))
                and (not via_email or email_valid(email))
                and (not via_sms or phone_valid(sms))
                and (not via_email or credentials["email"])
                and (not via_sms or credentials["sms"])
            )
            if save or test:
                if not valid:
                    st.error("Choose stores and at least one channel with a valid recipient and configured credentials.")
                elif test:
                    for channel, recipient in (("email", email), ("sms", sms)):
                        if recipient:
                            try:
                                send_test(channel, recipient)
                                st.success(f"{channel.upper()} test accepted for sending.")
                            except Exception as exc:
                                st.error(f"{channel.upper()} test failed: {exc}")
                else:
                    try:
                        create_watch(
                            part=result["part"], model=result["model"], storage=result["storage"],
                            color=result["color"], location=result["location"], family=result["family"],
                            target_stores=target_ids, email=email, sms=sms,
                        )
                        st.success("Alert saved. Run monitor.py now or install the Windows scheduled task.")
                    except (ValueError, RuntimeError, OSError) as exc:
                        st.error(str(exc))
elif result:
    st.info("No Apple Stores were returned in that query; try another location before creating an alert.")
else:
    st.info("Check availability once to select which stores to monitor and create your first alert.")

st.subheader("Saved alerts")
try:
    watches = load_watches()
    if not watches:
        st.caption("No alerts saved yet.")
    for w in watches:
        with st.container(border=True):
            left, right = st.columns([5, 1], vertical_alignment="center")
            with left:
                st.write(f"**{w['model']} {w['storage']} {w['color']}** · {w['location']}")
                recipients = " and ".join(c for c in ("email" if w.get("email") else "", "SMS" if w.get("sms") else "") if c)
                scope = "Any nearby store" if not w.get("target_stores") else f"{len(w['target_stores'])} specific store(s)"
                st.caption(f"{scope} · {recipients} · Last check: {w.get('last_checked') or 'not yet checked'}")
                if w.get("last_error"):
                    st.error(f"Last monitoring issue: {w['last_error']}")
            with right:
                if st.button("Remove", key=f"remove:{w['id']}", use_container_width=True):
                    delete_watch(w["id"])
                    st.rerun()
except (ValueError, OSError, RuntimeError) as exc:
    st.error(f"Could not load saved alerts: {exc}")

st.divider()
st.caption(
    "Alert triggers once per store while continuously available, and rearms after Apple explicitly "
    "reports Unavailable. The first monitoring run also alerts if the item is already available. "
    "Unknown results and API errors do not trigger false stock-outs. Alerts are best-effort, not reservations. "
    "Apple's undocumented endpoint may change, and your PC must be awake for scheduled checks."
)
