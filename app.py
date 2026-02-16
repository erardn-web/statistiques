import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Analyseur Facturation Suisse", layout="wide", page_icon="🏥")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_index=True)

# --- LOGIQUE DE CALCUL ---
def convertir_date(val):
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    try:
        return pd.to_datetime(str(val).strip(), dayfirst=True, errors="coerce")
    except:
        return pd.NaT

def calculer_liquidites_fournisseur(f_attente, p_hist, horizons):
    liq, taux = {}, {}
    if p_hist.empty:
        return {h: 0.0 for h in horizons}, {h: 0.0 for h in horizons}
    
    # Pré-calcul des probabilités pour performance
    stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean() for h in horizons).to_dict()
    
    for h in horizons:
        taux_h = (p_hist["delai"] <= h).mean()
        # Mapping rapide pour la simulation
        prob_map = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean())
        prob_fourn = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean())
        
        total_h = 0.0
        for _, row in f_attente.iterrows():
            p = prob_map.get((row["assureur"], row["fournisseur"]), 
                             prob_fourn.get(row["fournisseur"], taux_h))
            total_h += row["montant"] * p
        liq[h] = total_h
        taux[h] = taux_h
    return liq, taux

# --- INTERFACE ---
st.title("🏥 Analyseur de Facturation")

if 'view' not in st.session_state: st.session_state.view = 'analyse'

uploaded_file = st.sidebar.file_uploader("📁 Charger Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file)
        
        # MAPPING DYNAMIQUE (Sécurité)
        cols = {
            "date_facture": df_brut.columns[2],
            "loi": df_brut.columns[4],
            "medecin": df_brut.columns[7],
            "assureur": df_brut.columns[8],
            "fournisseur": df_brut.columns[9],
            "statut": df_brut.columns[12],
            "montant": df_brut.columns[13],
            "ca_encaisse": df_brut.columns[14],
            "date_paiement": df_brut.columns[15]
        }

        # --- SIDEBAR FILTRES ---
        st.sidebar.header("🔍 Configuration")
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", sorted(df_brut[cols["fournisseur"]].dropna().unique()))
        
        if st.sidebar.button("🩺 Mode Médecins Prescripteurs", use_container_width=True):
            st.session_state.view = 'medecin'
        if st.sidebar.button("📊 Retour Analyse Globale", use_container_width=True):
            st.session_state.view = 'analyse'

        # --- MODE ANALYSE GLOBALE ---
        if st.session_state.view == 'analyse':
            # Nettoyage
            df = df_brut.copy()
            df["date_facture"] = df[cols["date_facture"]].apply(convertir_date)
            df["date_paiement"] = df[cols["date_paiement"]].apply(convertir_date)
            df["montant"] = pd.to_numeric(df[cols["montant"]], errors="coerce").fillna(0)
            df["assureur"] = df[cols["assureur"]].fillna("Patient")
            df["statut_clean"] = df[cols["statut"]].astype(str).str.lower().str.strip()
            
            # Filtre Fournisseurs
            if sel_fournisseurs:
                df = df[df[cols["fournisseur"]].isin(sel_fournisseurs)]

            ajd = pd.Timestamp(datetime.today().date())
            f_att = df[df["statut_clean"].str.contains("en attente") & ~df["statut_clean"].str.contains("annulé")].copy()
            f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days

            # KPI
            st.metric("💰 TOTAL EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
            
            tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
            
            options_p = {"Global": None, "4 mois": 4, "2 mois": 2}
            
            for p_name, m_val in options_p.items():
                limit = ajd - pd.DateOffset(months=m_val) if m_val else df["date_facture"].min()
                df_p = df[df["date_facture"] >= limit]
                p_hist = df_p[df_p["date_paiement"].notna()].copy()
                p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days

                with tab1:
                    st.subheader(f"Estimations : {p_name}")
                    horizons = [10, 20, 30]
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                    res_df = pd.DataFrame({
                        "Horizon": [f"Sous {h}j" for h in horizons],
                        "Cash Estimé": [f"{liq[h]:,.0f} CHF" for h in horizons],
                        "Fiabilité": [f"{t[h]:.1%}" for h in horizons]
                    })
                    st.table(res_df)

                with tab2:
                    if not p_hist.empty:
                        st.subheader(f"Top 10 Délais ({p_name})")
                        stats = p_hist.groupby(cols["assureur"])["delai"].median().sort_values(ascending=False).head(10)
                        st.bar_chart(stats)

                with tab3:
                    st.subheader(f"Retards > 30j ({p_name})")
                    retards = f_att[f_att["delai_actuel"] > 30]
                    if not retards.empty:
                        st.dataframe(retards[[cols["date_facture"], cols["assureur"], "montant", "delai_actuel"]], use_container_width=True)
                    else: st.success("Aucun retard critique détecté.")

            with tab4:
                st.subheader("Tendances de remboursement")
                # Logique simplifiée de l'évolution (Line Chart)
                df_ev = p_hist.set_index("date_facture").resample('M')['delai'].mean()
                st.line_chart(df_ev)

        # --- MODE MÉDECINS ---
        else:
            st.header("👨‍⚕️ Top Médecins Prescripteurs")
            df_m = df_brut.copy()
            df_m["ca"] = pd.to_numeric(df_m[cols["ca_encaisse"]], errors="coerce").fillna(0)
            df_m["date_f"] = df_m[cols["date_facture"]].apply(convertir_date)
            df_m = df_m[(df_m["ca"] > 0) & df_m[cols["medecin"]].notna()]

            top_meds = df_m.groupby(cols["medecin"])["ca"].sum().nlargest(15)
            choix = st.multiselect("Sélectionner médecins :", top_meds.index.tolist(), default=top_meds.index.tolist()[:5])
            
            if choix:
                df_f = df_m[df_m[cols["medecin"]].isin(choix)].copy()
                df_f["Mois"] = df_f["date_f"].dt.to_period("M").astype(str)
                pivot = df_f.groupby(["Mois", cols["medecin"]])["ca"].sum().unstack().fillna(0)
                st.area_chart(pivot)
                st.subheader("Classement CA Cumulé")
                st.dataframe(df_f.groupby(cols["medecin"])["ca"].sum().sort_values(ascending=False).map("{:,.2f} CHF".format))

    except Exception as e:
        st.error(f"Erreur d'analyse : {e}")
        st.info("Vérifiez que les colonnes de votre fichier correspondent au format standard.")
else:
    st.info("👋 Bienvenue ! Veuillez charger un export Excel pour démarrer l'analyse.")
