# app/ui/safety_display.py
"""Shared safety scoring panel renderer — used by chat_page and explore_page."""
import streamlit as st

_BAND_EMOJI = {
    "very low": "🔵",
    "low":      "🟢",
    "moderate": "🟡",
    "high":     "🟠",
    "very high":"🔴",
}

_LGBT_LABELS = {
    1: ("Criminalized — serious legal risk", "🔴"),
    2: ("Hostile — discrimination common", "🟠"),
    3: ("Neutral — limited legal protections", "🟡"),
    4: ("Accepting — legal protections exist", "🟢"),
    5: ("Very Safe — full legal equality", "🔵"),
}

def render_safety_panel(result: dict, label: str = "") -> None:
    """Render safety scoring outputs as a clean tabbed panel.
    
    Drop-in replacement for both chat_page and explore_page versions.
    Takes the best features from both: emoji bands, v9b error fallback,
    model agreement, feature expanders, risk-conditional notes, LGBT alerts.
    """
    score         = result.get("safety_score")
    band          = result.get("risk_band", "—")
    band_emoji    = _BAND_EMOJI.get(band, "⚪")
    model_version = result.get("model_version", "—")

    if label:
        st.markdown(f"**{label}**")

    m1, m2, m3 = st.columns(3)
    m1.metric("Safety Score", f"{score:.1f}/100" if score is not None else "—")
    m2.metric("Risk Band", f"{band_emoji} {band}")
    m3.metric("Model", model_version)

    details = result.get("details") or {}
    weather = result.get("weather_risk") or {}
    ecuador = result.get("ecuador_risk") or {}
    peru_r  = result.get("peru_risk") or {}
    lgbt    = result.get("lgbt_safety") or details.get("lgbt_safety") or {}

    # ── Build tab list dynamically ────────────────────────────────────
    tab_labels = ["📊 Score Details"]
    if isinstance(weather, dict) and weather and not weather.get("error"):
        tab_labels.append("🌦️ Weather")
    if isinstance(ecuador, dict) and ecuador.get("applicable"):
        tab_labels.append("🐆 Ecuador")
    if isinstance(peru_r, dict) and peru_r.get("applicable"):
        tab_labels.append("🐆 Peru")
    if isinstance(lgbt, dict) and "lgbt_safety_score" in lgbt:
        tab_labels.append("🏳️‍🌈 LGBT")

    tabs    = st.tabs(tab_labels)
    tab_idx = 0

    # ── Score Details ─────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**Model breakdown**")
            mlp = details.get("mlp_score_v6")
            rf  = details.get("rf_score_v6")
            v9b = details.get("v9b_score")
            if mlp is not None: st.metric("MLP v6",           f"{mlp:.1f}")
            if rf  is not None: st.metric("Random Forest v6", f"{rf:.1f}")
            if v9b is not None:
                st.metric("v9b MLP", f"{v9b:.1f}")
            else:
                st.caption(f"⚠️ v9b not loaded: {details.get('v9b_error', 'artifacts missing or failed to load')}")
            st.caption(f"Active model: {model_version}")
            agreement = details.get("agreement_band", "—")
            spread    = details.get("model_spread")
            st.caption(f"Model agreement: **{agreement}**" + (f" (spread: {spread:.1f})" if spread else ""))
        with d2:
            st.markdown("**Location**")
            lat, lon  = result.get("latitude"), result.get("longitude")
            country   = result.get("country", "—")
            if lat and lon:
                st.caption(f"📍 {lat:.4f}, {lon:.4f}")
            st.caption(f"🌍 {country}")
            feat_count = details.get("feature_count")
            if feat_count:
                st.caption(f"Features used: {feat_count}")

        # Feature values expander
        features = details.get("features") or details.get("features_used") or {}
        if features:
            with st.expander("🔬 Feature values used in prediction", expanded=False):
                if isinstance(features, dict):
                    for fname, fval in sorted(features.items()):
                        try:
                            st.caption(f"**{fname}**: {fval:.4f}" if isinstance(fval, float) else f"**{fname}**: {fval}")
                        except Exception:
                            st.caption(f"**{fname}**: {fval}")
                else:
                    st.json(features)

        with st.expander("🗂️ Full prediction output", expanded=False):
            st.json({k: v for k, v in result.items() if k != "details"})
            if details:
                st.markdown("**details:**")
                st.json(details)

    # ── Weather ───────────────────────────────────────────────────────
    if isinstance(weather, dict) and weather and not weather.get("error") and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            w_score = weather.get("weather_risk_score", "—")
            w_label = weather.get("weather_risk_label", "—")
            st.metric("Weather Risk", f"{w_score}/5 — {w_label}")
            if assessment := weather.get("travel_month_assessment", ""):
                st.info(assessment)
            risks = weather.get("active_risks") or weather.get("risks", [])
            if risks:
                st.markdown("**Active risks this month:**")
                for r in risks:
                    if isinstance(r, dict):
                        sev  = r.get("severity", 0)
                        name = r.get("type") or r.get("name") or r.get("risk", "Unknown")
                        name = name.replace("_", " ").title()
                        desc = r.get("description") or r.get("notes", "")
                        with st.expander(f"{'🔴' * min(sev, 5)} {name}", expanded=sev >= 4):
                            if desc: st.write(desc)
                    elif isinstance(r, str):
                        with st.expander(f"🔴 {r}"):
                            st.write(r)

    # ── Ecuador ───────────────────────────────────────────────────────
    if isinstance(ecuador, dict) and ecuador.get("applicable") and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            e1, e2, e3 = st.columns(3)
            e1.metric("Overall Risk",  f"{ecuador.get('overall_risk',  '—')}/5")
            e2.metric("Crime Risk",    f"{ecuador.get('crime_risk',    '—')}/5")
            e3.metric("Wildlife Risk", f"{ecuador.get('wildlife_risk', '—')}/5")
            province = ecuador.get("province") or ecuador.get("region", "")
            hr       = ecuador.get("homicide_rate_per_100k") or ecuador.get("homicide_rate")
            parts = []
            if province: parts.append(f"Province: **{province}**")
            if hr is not None: parts.append(f"Homicide rate: {hr}/100k")
            if parts: st.caption(" · ".join(parts))
            note = ecuador.get("crime_notes") or ecuador.get("note") or ecuador.get("summary", "")
            if note:
                (st.warning if ecuador.get("overall_risk", 0) >= 4 else st.info)(note)

    # ── Peru ──────────────────────────────────────────────────────────
    if isinstance(peru_r, dict) and peru_r.get("applicable") and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            p1, p2, p3 = st.columns(3)
            p1.metric("Overall Risk",  f"{peru_r.get('overall_risk',  '—')}/5")
            p2.metric("Crime Risk",    f"{peru_r.get('crime_risk',    '—')}/5")
            p3.metric("Wildlife Risk", f"{peru_r.get('wildlife_risk', '—')}/5")
            province = peru_r.get("province") or peru_r.get("region", "")
            hr       = peru_r.get("homicide_rate_per_100k") or peru_r.get("homicide_rate")
            parts = []
            if province: parts.append(f"Region: **{province}**")
            if hr is not None: parts.append(f"Homicide rate: {hr}/100k")
            if parts: st.caption(" · ".join(parts))
            note = peru_r.get("crime_notes") or peru_r.get("note") or peru_r.get("summary", "")
            if note:
                (st.warning if peru_r.get("overall_risk", 0) >= 4 else st.info)(note)

    # ── LGBT ──────────────────────────────────────────────────────────
    if isinstance(lgbt, dict) and "lgbt_safety_score" in lgbt and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            score_l   = lgbt.get("lgbt_safety_score")
            legal_idx = lgbt.get("lgbt_legal_index")
            l1, l2    = st.columns(2)
            l1.metric("LGBT Safety Score", f"{score_l}/5" if score_l else "—")
            if legal_idx is not None:
                l2.metric("Legal Index", f"{legal_idx:.1f}/100")
            label_l, _ = _LGBT_LABELS.get(score_l, ("—", ""))
            st.markdown(f"**{label_l}**")
            confidence = lgbt.get("lgbt_confidence") or lgbt.get("confidence", "—")
            st.caption(f"Data confidence: {confidence}")
            if lgbt.get("death_penalty_risk"):
                st.error("🚨 Death penalty or corporal punishment may apply to same-sex relations.")
            elif lgbt.get("criminalized"):
                st.warning("⚠️ Same-sex relations are criminalized. Exercise extreme caution.")
            st.caption("Source: ILGA World, Rainbow Map, and WayFinder LGBT classifier (1 = Criminalized → 5 = Very Safe)")