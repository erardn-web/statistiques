import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur de Facturation Suisse", layout="wide", page_icon="🏥")

# --- FONCTIONS DE CALCUL ---

def nettoyer_donnees(df):
    """Normalisation et nettoyage des colonnes"""
    # Renommage basé sur l'index pour la robustesse
    df = df.rename(columns={
        df.columns[2]: "date_facture", 
        df.columns[8]: "assureur",
        df.columns[9]: "fournisseur",
        df.columns[12]: "statut", 
        df.columns[13]: "montant", 
        df.columns[15]: "date_paiement"
    })
    
    # Conversion dates
    for col in ["date_facture", "date_paiement"]:
        df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
    
    # Nettoyage types
    df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
    df["statut"] = df["statut"].astype(str).str.lower().str.strip()
    df["assureur"] = df["assureur"].fillna("Patient")
    return df

def estimer_liquidites(f_attente, p_hist, jours):
    """Calcule le montant estimé encaissable dans un délai de X jours"""
    if p_hist.empty or jours < 0:
        return 0.0, 0.0
    
    # Probabilité de paiement par assureur
    taux_par_assur = p_hist.groupby("assureur")["delai"].apply(lambda x: (x <= jours).mean())
    taux_moyen = (p_hist["delai"] <= jours).mean()
    
    # Application du taux historique sur les montants en attente
    f_attente = f_attente.copy()
    f_attente["probabilite"] = f_attente["assureur"].map(taux_par_assur).fillna(taux_moyen)
    total_estime = (f_attente["montant"] * f_attente["probabilite"]).sum()
    
    return total_estime, taux_moyen

# --- INTERFACE STREAMLIT ---

st.title("🏥 Analyseur de Facturation Pro")
st.markdown("Optimisation de la trésorerie et analyse des délais assureurs.")

uploaded_file = st.sidebar.file_uploader("📁 Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        # Chargement
        df_brut = pd.read_excel(uploaded_file)
        df = nettoyer_donnees(df_brut)
        
        # --- SIDEBAR FILTRES ---
        st.sidebar.header("🔍 Filtres & Options")
        fournisseurs = sorted(df["fournisseur"].dropna().unique().tolist())
        selection = st.sidebar.multiselect("Fournisseurs :", fournisseurs, default=fournisseurs)
        
        # Filtre sur la sélection
        df = df[df["fournisseur"].isin(selection)]
        
        # Option Date Future
        st.sidebar.markdown("---")
        st.sidebar.subheader("📅 Estimation Future")
        activer_estim = st.sidebar.checkbox("Estimer à une date précise")
        date_cible = None
        jours_delta = 0
        
        if activer_estim:
            date_cible = st.sidebar.date_input("Choisir une date cible", value=datetime.today())
            jours_delta = (pd.Timestamp(date_cible) - pd.Timestamp(datetime.today().date())).days

        if st.sidebar.button("🚀 Lancer l'analyse", type="primary"):
            # Séparation Attente vs Historique
            ajd = pd.Timestamp.now().normalize()
            
            # Factures en attente (Global)
            f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].str.contains("annulé")].copy()
            f_att["retard_actuel"] = (ajd - f_att["date_facture"]).dt.days
            
            # Historique de paiement
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
            p_hist = p_hist[p_hist["delai"] >= 0]

            # --- AFFICHAGE ---
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités & Prévisions", "🕒 Analyse Délais", "⚠️ Retards"])

            with tab1:
                # Section Date Spécifique
                if activer_estim and jours_delta >= 0:
                    val_estimee, prob_globale = estimer_liquidites(f_att, p_hist, jours_delta)
                    st.success(f"### Prévision au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta} jours)")
                    c1, c2 = st.columns(2)
                    c1.metric("Encaissement estimé", f"{val_estimee:,.0f} CHF")
                    c2.metric("Indice de confiance", f"{prob_globale:.1%}")
                    st.divider()

                # Section Horizons Classiques
                st.subheader("Estimations standards")
                cols = st.columns(3)
                for i, h in enumerate([10, 20, 30]):
                    val, taux = estimer_liquidites(f_att, p_hist, h)
                    cols[i].metric(f"Sous {h} jours", f"{val:,.0f} CHF", f"Taux: {taux:.0%}")
                
                st.info(f"Total brut actuellement en attente : {f_att['montant'].sum():,.2f} CHF")

            with tab2:
                st.subheader("Performance par Assureur")
                if not p_hist.empty:
                    stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std', 'count']).reset_index()
                    stats = stats.rename(columns={'mean': 'Moyenne (j)', 'median': 'Médiane (j)', 'count': 'Nb Factures'})
                    
                    # Graphique
                    st.bar_chart(stats.set_index("assureur")["Moyenne (j)"])
                    st.dataframe(stats.sort_values("Moyenne (j)"), use_container_width=True)
                else:
                    st.warning("Aucune donnée historique de paiement trouvée.")

            with tab3:
                st.subheader("Analyse des Retards")
                retards_30 = f_att[f_att["retard_actuel"] > 30].copy()
                st.error(f"Il y a **{len(retards_30)}** factures avec plus de 30 jours de retard.")
                
                if not retards_30.empty:
                    st.dataframe(retards_30[["date_facture", "assureur", "montant", "retard_actuel"]].sort_values("retard_actuel", ascending=False))
                    st.write(f"Total à relancer : **{retards_30['montant'].sum():,.2f} CHF**")

    except Exception as e:
        st.error(f"Erreur d'analyse : {e}")
        st.info("Vérifiez que votre fichier Excel possède les colonnes attendues (Date, Assureur, Statut, Montant).")
else:
    st.info("👋 Bienvenue ! Veuillez charger un fichier Excel dans la barre latérale pour analyser vos données.")
