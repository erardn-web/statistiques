import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- CONSTANTES ET LOGIQUE MÉTIER ---
MOTS_EXCLUSION = {"BERNOIS", "NEUCHATELOIS", "VALAISANS", "GENEVOIS", "VAUDOIS", "FRIBOURGEOIS"}
COULEURS_PROF = {"Physiothérapie": "#00CCFF", "Ergothérapie": "#FF9900", "Massage": "#00CC96", "Autre": "#AB63FA"}

def assigner_profession(code):
    c = str(code).strip().lower()
    if 'rem' in c: return "Autre"
    if any(x in c for x in ['privé', 'abo', 'thais']) or c.startswith(('73', '25', '15.30')): 
        return "Physiothérapie"
    if any(x in c for x in ['foyer']) or c.startswith(('76', '31', '32')): 
        return "Ergothérapie"
    if c.startswith('1062'): 
        return "Massage"
    return "Autre"

def convertir_date(val):
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.to_datetime(val, errors="coerce")

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    if p_hist.empty: return liq, taux_glob
    for h in jours_horizons:
        stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        stats_fourn = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        total_h = 0.0
        for _, row in f_attente.iterrows():
            key = (row["assureur"], row["fournisseur"])
            prob = stats_croisees.get(key, stats_fourn.get(row["fournisseur"], taux_glob[h]))
            total_h += row["montant"] * prob
        liq[h] = total_h
    return liq, taux_glob

# --- INITIALISATION DE L'ÉTAT ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"

# ==========================================
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse Médicale")
    st.markdown("---")
    
    col_a, col_b = st.columns(2)
    col_c, col_d = st.columns(2)

    with col_a:
        st.info("📊 **MODULE FACTURATION**")
        st.write("Analyse des liquidités et des retards.")
        if st.button("Accéder à la Facturation", use_container_width=True):
            st.session_state.page = "factures"; st.rerun()
            
    with col_b:
        st.success("🩺 **MODULE MÉDECINS**")
        st.write("Performance par prescripteurs.")
        if st.button("Accéder aux Médecins", use_container_width=True):
            st.session_state.page = "medecins"; st.rerun()

    with col_c:
        st.warning("🏷️ **MODULE TARIFS**")
        st.write("Revenus mensuels par profession.")
        if st.button("Accéder aux Tarifs", use_container_width=True):
            st.session_state.page = "tarifs"; st.rerun()

    with col_d:
        st.info("🏦 **BILAN COMPTABLE**")
        st.write("CA (Prestations) et Impayés (Factures) au 31.12.")
        if st.button("Accéder au Bilan", use_container_width=True, type="primary"):
            st.session_state.page = "bilan"; st.rerun()

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour"): st.session_state.page = "accueil"; st.rerun()
    st.title("📊 Analyse de la Facturation")
    up = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="f_up")
    if up:
        try:
            df_brut = pd.read_excel(up, header=0)
            fourn = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_f = st.sidebar.multiselect("Fournisseurs :", fourn, default=fourn)
            df = df_brut[df_brut.iloc[:, 9].isin(sel_f)].copy()
            df = df.rename(columns={df.columns[2]: "date_facture", df.columns[8]: "assureur", df.columns[9]: "fournisseur", df.columns[12]: "statut", df.columns[13]: "montant", df.columns[15]: "date_paiement"})
            df["date_facture"] = df["date_facture"].apply(convertir_date)
            df["date_paiement"] = df["date_paiement"].apply(convertir_date)
            df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
            f_att = df[df["statut"].astype(str).str.lower().str.contains("en attente")].copy()
            st.metric("💰 TOTAL EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
            t1, t2 = st.tabs(["💰 Liquidités", "🕒 Délais"])
            with t1:
                h = [10, 20, 30]; liq, pr = calculer_liquidites_fournisseur(f_att, p_hist, h)
                st.table(pd.DataFrame({"Horizon": [f"Sous {x}j" for x in h], "Estimation (CHF)": [f"{round(liq[x]):,}" for x in h], "Probabilité": [f"{round(pr[x]*100)}%" for x in h]}))
            with t2:
                st.dataframe(p_hist.groupby("assureur")["delai"].agg(['mean', 'median']).sort_values("mean", ascending=False), use_container_width=True)
        except Exception as e: st.error(e)

# ==========================================
# 🩺 MODULE MÉDECINS
# ==========================================
elif st.session_state.page == "medecins":
    if st.sidebar.button("⬅️ Retour"): st.session_state.page = "accueil"; st.rerun()
    st.header("👨‍⚕️ Performance Médecins")
    up = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="m_up")
    if up:
        try:
            df = pd.read_excel(up, header=0)
            df["medecin"] = df.iloc[:, 7]
            df["ca"] = pd.to_numeric(df.iloc[:, 14], errors="coerce").fillna(0)
            ca_tot = df.groupby("medecin")["ca"].sum().sort_values(ascending=False).reset_index()
            st.altair_chart(alt.Chart(ca_tot.head(15)).mark_bar().encode(x='ca:Q', y=alt.Y('medecin:N', sort='-x'), color='ca:Q'), use_container_width=True)
            st.dataframe(ca_tot, use_container_width=True)
        except Exception as e: st.error(e)

# ==========================================
# 🏷️ MODULE TARIFS
# ==========================================
elif st.session_state.page == "tarifs":
    if st.sidebar.button("⬅️ Retour"): st.session_state.page = "accueil"; st.rerun()
    st.title("🏷️ Analyse par Métier")
    up = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="t_up")
    if up:
        try:
            df = pd.read_excel(up, sheet_name='Prestation')
            c_code, c_sum = df.columns[2], df.columns[11]
            c_date = [c for c in df.columns if 'Date' in str(c)][0]
            df[c_sum] = pd.to_numeric(df[c_sum], errors='coerce')
            df[c_date] = pd.to_datetime(df[c_date], errors='coerce')
            df['Profession'] = df[c_code].apply(assigner_profession)
            df['Mois'] = df[c_date].dt.to_period('M').dt.to_timestamp()
            df_p = df.groupby(['Mois', 'Profession'])[c_sum].sum().reset_index()
            st.plotly_chart(px.bar(df_p, x='Mois', y=c_sum, color='Profession', color_discrete_map=COULEURS_PROF, barmode='group'), use_container_width=True)
        except Exception as e: st.error(e)

# ==========================================
# 🏦 MODULE BILAN COMPTABLE
# ==========================================
elif st.session_state.page == "bilan":
    if st.sidebar.button("⬅️ Retour"): st.session_state.page = "accueil"; st.rerun()
    st.title("🏦 Bilan Comptable au 31 Décembre")
    up = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="b_up")
    if up:
        try:
            xl = pd.ExcelFile(up)
            # Gestion souple du nom de l'onglet Facture(s)
            onglet_factures = next((s for s in xl.sheet_names if 'Facture' in s), None)
            
            if 'Prestation' not in xl.sheet_names or onglet_factures is None:
                st.error("L'onglet 'Prestation' ou 'Factures' est manquant.")
                st.stop()
            
            df_pres = pd.read_excel(up, sheet_name='Prestation')
            df_fact = pd.read_excel(up, sheet_name=onglet_factures)
            
            annee = st.sidebar.number_input("Année de clôture :", 2020, 2030, 2024)
            date_limite = pd.Timestamp(year=annee, month=12, day=31)

            # 1. CA (Onglet Prestation, Colonne L / Index 11)
            col_ca = df_pres.columns[11]
            ca_total = pd.to_numeric(df_pres[col_ca], errors='coerce').sum()

            # 2. Impayés (Onglet Factures, Col O / Index 14 et P / Index 15)
            col_m_f, col_d_p = df_fact.columns[14], df_fact.columns[15]
            df_fact[col_d_p] = pd.to_datetime(df_fact[col_d_p], errors='coerce')
            df_fact[col_m_f] = pd.to_numeric(df_fact[col_m_f], errors='coerce').fillna(0)

            # Sécurité Export : vérifier si des paiements existent après le 31.12
            futures = df_fact[df_fact[col_d_p] > date_limite]
            if not futures.empty:
                st.error("🛑 **EXPORT NON TRAITABLE**")
                st.warning(f"L'onglet '{onglet_factures}' contient des paiements après le 31.12.{annee}.")
                st.stop()

            # Calcul Impayés : Montant non-nul (Col O) et Date paiement vide (Col P)
            df_impayes = df_fact[(df_fact[col_m_f] != 0) & (df_fact[col_d_p].isna())].copy()
            total_impayes = df_impayes[col_m_f].sum()
            
            c1, c2 = st.columns(2)
            c1.metric(f"📈 CA Annuel {annee}", f"{ca_total:,.2f} CHF")
            c2.metric(f"⏳ Impayés au 31.12.{annee}", f"{total_impayes:,.2f} CHF")
            
            st.markdown("---")
            st.write(f"### Détail des factures impayées au 31.12.{annee}")
            df_view = df_impayes[[df_fact.columns[2], df_fact.columns[8], col_m_f]]
            st.dataframe(df_view.sort_values(df_fact.columns[2]), use_container_width=True)
            
        except Exception as e: st.error(f"Erreur : {e}")
