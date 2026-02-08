import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Analytics Facturation", layout="wide", page_icon="🏥")

def nettoyer_donnees(df):
    """Normalisation des colonnes et types"""
    # On renomme par index pour la flexibilité, mais avec sécurité
    cols = {
        df.columns[2]: "date_facture", 
        df.columns[8]: "assureur",
        df.columns[12]: "statut", 
        df.columns[13]: "montant", 
        df.columns[15]: "date_paiement",
        df.columns[9]: "fournisseur"
    }
    df = df.rename(columns=cols).copy()
    
    for col in ["date_facture", "date_paiement"]:
        df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
    
    df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
    df["statut"] = df["statut"].astype(str).str.lower().str.strip()
    df["assureur"] = df["assureur"].fillna("Patient")
    return df

def calculer_liquidites_vectorise(f_attente, p_hist):
    """Calcul rapide sans boucles imbriquées"""
    if p_hist.empty:
        return {h: 0.0 for h in [10, 20, 30]}, {h: 0.0 for h in [10, 20, 30]}
    
    # Calcul des taux de paiement par assureur et par horizon
    horizons = [10, 20, 30]
    taux_par_assur = {}
    
    for h in horizons:
        # Taux de succès historique par assureur pour l'horizon H
        p_hist[f'paye_{h}'] = p_hist['delai'] <= h
        taux_par_assur[h] = p_hist.groupby('assureur')[f'paye_{h}'].mean()

    liq_estime = {}
    taux_moyen_global = {}
    
    for h in horizons:
        # Mapper les taux sur les factures en attente
        f_attente[f'taux_{h}'] = f_attente['assureur'].map(taux_par_assur[h]).fillna(p_hist[f'paye_{h}'].mean())
        liq_estime[h] = (f_attente['montant'] * f_attente[f'taux_{h}']).sum()
        taux_moyen_global[h] = p_hist[f'paye_{h}'].mean()
        
    return liq_estime, taux_moyen_global

# --- INTERFACE ---
st.title("🏥 Analyseur de Facturation Pro")

uploaded_file = st.sidebar.file_uploader("Fichier Excel", type="xlsx")

if uploaded_file:
    df_brut = pd.read_excel(uploaded_file)
    df = nettoyer_donnees(df_brut)
    
    # Sidebar : Filtres
    fournisseurs = sorted(df["fournisseur"].dropna().unique())
    selection = st.sidebar.multiselect("Fournisseurs", fournisseurs, default=fournisseurs)
    df = df[df["fournisseur"].isin(selection)]
    
    # Logique de dates
    ajd = pd.Timestamp.now().normalize()
    f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].contains("annulé")].copy()
    f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
    
    tab1, tab2, tab3 = st.tabs(["💰 Cash-Flow", "📊 Performance Assureurs", "⚠️ Risques"])

    with tab1:
        st.subheader("Prévisions d'encaissement")
        p_hist = df[df["date_paiement"].notna()].copy()
        p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
        p_hist = p_hist[p_hist["delai"] >= 0]
        
        liq, taux = calculer_liquidites_vectorise(f_att, p_hist)
        
        c1, c2, c3 = st.columns(3)
        metrics = [(c1, 10), (c2, 20), (c3, 30)]
        for col, h in metrics:
            col.metric(f"Sous {h} jours", f"{liq[h]:,.0f} CHF", f"{taux[h]:.1%}")

    with tab2:
        st.subheader("Délais de paiement moyens")
        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'count']).rename(columns={'mean': 'Jours', 'count': 'Volume'})
        st.bar_chart(stats['Jours'])
        st.dataframe(stats.sort_values("Jours", ascending=False), use_container_width=True)

    with tab3:
        st.subheader("Factures critiques (>30 jours)")
        retards = f_att[f_att["delai_actuel"] > 30].sort_values("delai_actuel", ascending=False)
        st.warning(f"Il y a {len(retards)} factures en souffrance pour un total de {retards['montant'].sum():,.2f} CHF.")
        st.dataframe(retards[["date_facture", "assureur", "montant", "delai_actuel"]])

else:
    st.info("💡 Chargez un export Excel pour débuter l'analyse.")
