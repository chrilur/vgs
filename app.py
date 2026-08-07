import streamlit as st
import pandas as pd
import altair as alt
import glob
import os
import re
import io

st.set_page_config(page_title="Elevstatistikk", layout="wide")

st.title("Elevstatistikk for videregående skoler")
st.write("Velg fylke, skole og linje for å se historisk utvikling av antall gutter og jenter.")

@st.cache_data
def load_fylker():
    """Laster inn fylkesnavn fra fylker.csv."""
    try:
        df_fylker = pd.read_csv("fylker.csv")
        df_fylker["fylkesnr"] = df_fylker["fylkesnr"].astype(str)
        return dict(zip(df_fylker["fylkesnr"], df_fylker["fylkesnavn"]))
    except FileNotFoundError:
        st.error("Fant ikke filen 'fylker.csv'. Sørg for at den ligger i mappen.")
        return {}

@st.cache_data
def get_file_mapping(fylke_mapping):
    """Leter gjennom mappen etter skole-filer."""
    mapping = []
    for f in glob.glob("*.csv"):
        if f == "fylker.csv" or f == "1_Hele landet.csv":
            continue
            
        base = os.path.basename(f).replace(".csv", "")
        parts = re.split(r'-?_', base, maxsplit=1)
        if len(parts) == 2:
            fylkesnr = parts[0]
            skole = parts[1]
            fylkesnavn = fylke_mapping.get(fylkesnr, f"Ukjent fylke ({fylkesnr})")
            
            mapping.append({"fylkesnavn": fylkesnavn, "skole": skole, "file": f})
            
    return pd.DataFrame(mapping)

@st.cache_data
def load_all_data(df_files):
    """Laster innholdet fra alle CSV-filene inn i én stor felles datatabell."""
    df_list = []
    for index, row in df_files.iterrows():
        try:
            df = pd.read_csv(row["file"])
            # Vi legger til fylkesnavnet som en egen kolonne i dataene
            df["fylkesnavn"] = row["fylkesnavn"]
            df_list.append(df)
        except Exception:
            pass
            
    if df_list:
        # Slår sammen alle tabellene til én
        return pd.concat(df_list, ignore_index=True)
    return pd.DataFrame()

# Laster inn grunnlagsdata
fylke_mapping = load_fylker()
df_files = get_file_mapping(fylke_mapping)

if df_files.empty:
    st.warning("Fant ingen datafiler for skoler. Sørg for at CSV-filene ligger i samme mappe som scriptet.")
else:
    # Laster inn selve elevdataene fra alle filer
    df_all = load_all_data(df_files)
    
    # --- 1. Velg fylke ---
    fylker = ["Ingen valgt", "Alle fylker"] + sorted(df_files["fylkesnavn"].unique().tolist())
    selected_fylke = st.selectbox("Velg fylke", fylker)
    
    if selected_fylke != "Ingen valgt":
        
        # --- 2. Velg skole ---
        if selected_fylke == "Alle fylker":
            # Låser skolevalget til "Alle skoler" og deaktiverer menyen (disabled=True)
            skoler = ["Alle skoler"]
            selected_skole = st.selectbox("Velg skole", skoler, disabled=True)
        else:
            # Viser skolene for det spesifikke fylket
            tilgjengelige_skoler = df_files[df_files["fylkesnavn"] == selected_fylke]["skole"].unique().tolist()
            skoler = ["Ingen valgt", "Alle skoler"] + sorted(tilgjengelige_skoler)
            selected_skole = st.selectbox("Velg skole", skoler)
        
        if selected_skole != "Ingen valgt":
            
            # --- NY LOGIKK FOR "ALLE FYLKER" ---
            if selected_fylke == "Alle fylker":
                # Hvis brukeren har valgt hele landet, leser vi fasit-filen direkte
                try:
                    filtered_df = pd.read_csv("1_Hele landet.csv")
                except FileNotFoundError:
                    st.error("Fant ikke filen '1_Hele landet.csv'. Pass på at den ligger i mappen.")
                    st.stop() # Stopper kjøringen av resten av koden
            else:
                # Hvis de har valgt et spesifikt fylke, filtrerer vi som vanlig
                filtered_df = df_all.copy()
                filtered_df = filtered_df[filtered_df["fylkesnavn"] == selected_fylke]
                if selected_skole != "Alle skoler":
                    filtered_df = filtered_df[filtered_df["skole"] == selected_skole]
            
            # --- 3. Velg linje ---
            if "linje" in filtered_df.columns:
                linjer = ["Ingen valgt"] + sorted(filtered_df["linje"].dropna().unique().tolist())
                selected_linje = st.selectbox("Velg utdanningsprogram (linje)", linjer)
                
                if selected_linje != "Ingen valgt":
                    
                    # Filtrer kun for valgt linje
                    df_linje = filtered_df[filtered_df["linje"] == selected_linje]
                    
                    if not df_linje.empty:
                        # Hent ut unike årstall
                        years = []
                        for col in df_linje.columns:
                            if " gutter" in col:
                                year = col.replace(" gutter", "")
                                
                                # Krever at året er på formatet "2012-13" for å fjerne søppelkolonner (som ...15)
                                if re.match(r"^\d{4}-\d{2}$", year):
                                    if year not in years:
                                        years.append(year)
                        
                        years = sorted(years)
                        gutter = []
                        jenter = []
                        
                        # Summerer tallene (Dette trengs fortsatt hvis man velger "Alle skoler" i ett fylke)
                        for y in years:
                            g_col = f"{y} gutter"
                            j_col = f"{y} jenter"
                            
                            g_sum = df_linje[g_col].sum(skipna=True) if g_col in df_linje.columns else 0
                            j_sum = df_linje[j_col].sum(skipna=True) if j_col in df_linje.columns else 0
                            
                            gutter.append(g_sum)
                            jenter.append(j_sum)
                            
                        # Setter opp data for grafen
                        plot_df = pd.DataFrame({
                            "År": years,
                            "Gutter": gutter,
                            "Jenter": jenter
                        })
                        
                        # 1. "Smelter" dataene
                        plot_df_melted = plot_df.melt(id_vars="År", var_name="Kjønn", value_name="Antall")
                        
                        # 2. Filtrerer bort alle rader der 'Antall' er 0.
                        plot_df_melted = plot_df_melted[plot_df_melted["Antall"] > 0]
                        
                        # Formaterer teksten med riktige store og små bokstaver
                        if selected_skole == "Alle skoler":
                            if selected_fylke == "Alle fylker":
                                fylke_formatert = "alle fylker"
                            else:
                                fylke_formatert = selected_fylke.capitalize()
                                
                            sted_tekst = f"alle skoler ({fylke_formatert})"
                        else:
                            # Beholder skolenavnet slik det står i filen
                            sted_tekst = selected_skole
                            
                        st.subheader(f"Kjønnsfordeling for {selected_linje.lower()} ved {sted_tekst}")
                        
                        if not plot_df_melted.empty:
                            # 3. Oppretter graf med Altair
                            chart = alt.Chart(plot_df_melted).mark_line(point=True).encode(
                                x=alt.X('År:O', title='Skoleår', axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=0)),
                                y=alt.Y('Antall:Q', title='Antall elever'),
                                color=alt.Color('Kjønn:N', scale=alt.Scale(domain=['Gutter', 'Jenter'], range=['#1f77b4', '#ff7f0e'])),
                                tooltip=[
                                    alt.Tooltip('År:O', title='År'),
                                    alt.Tooltip('Kjønn:N', title='Kjønn'),
                                    alt.Tooltip('Antall:Q', title='Antall')
                                ]
                            ).interactive()
                            
                            # Slår av Streamlit-tema for å tvinge x-aksen til å vise alle år
                            st.altair_chart(chart, use_container_width=True, theme=None)
                            
                            # --- NYTT: Nedlastingsknapp for Excel ---
                            
                            # 1. Gjør klar en "minne-buffer" for Excel-filen
                            buffer = io.BytesIO()
                            
                            # 2. Skriver datarammen (vi bruker plot_df, som har År, Gutter, Jenter i separate kolonner) til bufferen
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                plot_df.to_excel(writer, index=False, sheet_name='Elevtall')
                            
                            # 3. Henter ut den ferdige filen fra bufferen
                            excel_data = buffer.getvalue()
                            
                            # 4. Lager et ryddig filnavn (fjerner f.eks. mellomrom og parenteser)
                            rent_sted = sted_tekst.replace(" ", "_").replace("(", "").replace(")", "")
                            rent_linje = selected_linje.replace(" ", "_")
                            filnavn = f"Elevtall_{rent_sted}_{rent_linje}.xlsx"
                            
                            st.divider() # Legger til en tynn grå strek for å skille grafen fra knappen
                            
                            # 5. Viser nedlastingsknappen
                            st.download_button(
                                label="📥 Last ned data som Excel",
                                data=excel_data,
                                file_name=filnavn,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("Det finnes ingen år med registrerte elever for denne kombinasjonen.")
                            
                    else:
                        st.warning("Fant ingen data for denne kombinasjonen.")
            else:
                st.error("Datafilen mangler en kolonne som heter 'linje'.")