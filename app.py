import streamlit as st
import pandas as pd
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- DICTIONNAIRE DE MAPPAGE (Pour éviter les iloc) ---
# On définit ici les mots-clés pour retrouver les colonnes automatiquement
COL_MAP = {
    "date_facture": ["date", "facture"],
    "loi": ["loi", "type"],
    "assureur": ["assureur", "garant"],
    "fournisseur": ["fournisseur", "site"],
    "statut": ["statut", "etat"],
    "montant": ["montant", "total"],
    "date_paiement": ["paiement", "remboursement"],
    "medecin": ["médecin", "prescripteur", "exécutant"],
    "ca": ["ca", "chiffre", "honoraire"]
}

# --- FONCTIONS UTILITAIRES & CACHING ---
@st.cache_data
def charger_et_nettoyer(file):
    """Charge le fichier et tente de mapper les colonnes intelligemment."""
    df = pd.read_excel(file, header=0)
    
    # Mapping intelligent des colonnes
    new_columns = {}
    for key, keywords in COL_MAP.items():
        for i, col in enumerate(df.columns):
            if any(k.lower() in str(col).lower() for k in keywords):
                new_columns[i] = key
                break
    
    # Renommage et conversion
    df = df.rename(columns={df.columns[i]: name for i, name in new_columns.items()})
    
    # Sécurité : Si une colonne manque, on évite le crash
    expected = ["date_facture", "montant", "fournisseur"]
    for col in expected:
        if col not in df.columns:
            st.error(f"⚠️ La colonne '{col}' n'a pas été détectée. Vérifiez l'entête du fichier.")
            return None

    df["date_facture"] = pd.to_datetime(df["date_facture"], dayfirst=True, errors="coerce")
    df["date_paiement"] = pd.to_datetime(df["date_paiement"], dayfirst=True, errors="coerce")
    df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
    return df

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    if p_hist.empty: return liq, taux_glob
    
    for h in jours_horizons:
        # Calcul des probabilités de paiement sous H jours
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
if 'page' not in st.session_state: st.session_state.page = "accueil"

# ==========================================
# 🏠 NAVIGATION
# ==========================================
def changer_page(nom_page):
    st.session_state.page = nom_page
    st.rerun()

if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Facturation")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.info("📊 **MODULE FACTURATION**")
        if st.button("Accéder à l'Analyse Facturation", use_container_width=True): changer_page("factures")
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        if st.button("Accéder à l'Analyse Médecins", use_container_width=True): changer_page("medecins")

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    st.sidebar.button("⬅️ Retour", on_click=changer_page, args=("accueil",))
    st.title("📊 Analyse de la Facturation")
    
    uploaded_file = st.sidebar.file_uploader("Fichier Excel", type="xlsx")
    
    if uploaded_file:
        df_full = charger_et_nettoyer(uploaded_file)
        if df_full is not None:
            # Filtres dynamiques
            fournisseurs = sorted(df_full["fournisseur"].dropna().unique())
            sel_fourn = st.sidebar.multiselect("Fournisseurs", fournisseurs, default=fournisseurs)
            
            df = df_full[df_full["fournisseur"].isin(sel_fourn)].copy()
            
            # KPI Rapides
            ajd = pd.Timestamp.now().normalize()
            f_att = df[df["statut"].astype(str).str.lower().str.contains("attente")].copy()
            f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
            
            c1, c2 = st.columns(2)
            c1.metric("💰 TOTAL EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
            c2.metric("📋 FACTURES OUVERTES", len(f_att))

            # --- ANALYSE DES DÉLAIS ---
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
            
            tabs = st.tabs(["💰 Prévisions Liquidités", "🕒 Performance Assureurs", "⚠️ Retards"])
            
            with tabs[0]:
                st.subheader("Estimation des rentrées d'argent")
                h_list = [10, 20, 30]
                liq, probas = calculer_liquidites_fournisseur(f_att, p_hist, h_list)
                
                res_df = pd.DataFrame({
                    "Horizon": [f"Sous {h} jours" for h in h_list],
                    "Montant Estimé": [f"{v:,.2f} CHF" for v in liq.values()],
                    "Confiance": [f"{probas[h]*100:.1f}%" for h in h_list]
                })
                st.table(res_df)
            
            with tabs[1]:
                stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'count']).reset_index()
                st.dataframe(stats.sort_values("mean", ascending=False), use_container_width=True)

# ==========================================
# 👨‍⚕️ MODULE MÉDECINS
# ==========================================
elif st.session_state.page == "medecins":
    st.sidebar.button("⬅️ Retour", on_click=changer_page, args=("accueil",))
    st.title("👨‍⚕️ Performance Médecins")
    
    uploaded_file = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="med_up")
    
    if uploaded_file:
        df_med = charger_et_nettoyer(uploaded_file)
        if df_med is not None:
            # Nettoyage spécifique Médecins
            df_med = df_med[df_med["loi"].astype(str).str.upper() != "TG"]
            
            # Visualisation
            top_n = st.slider("Nombre de médecins à afficher", 5, 50, 10)
            
            ca_med = df_med.groupby("medecin")["montant"].sum().sort_values(ascending=False).head(top_n).reset_index()
            
            chart = alt.Chart(ca_med).mark_bar().encode(
                x=alt.X('montant:Q', title="Chiffre d'Affaires"),
                y=alt.Y('medecin:N', sort='-x', title="Médecin"),
                color=alt.Color('montant:Q', scale=alt.Scale(scheme='greens'))
            ).properties(height=400)
            
            st.altair_chart(chart, use_container_width=True)
            st.dataframe(ca_med, use_container_width=True)
