import pandas as pd
import glob
import os
import re

# ------------------------------------------------------------------
# 1. Collect ALL AVAILABILITY-data CSV files
#    - "AVAILABILITY-data.csv"           (no tag)
#    - "AVAILABILITY-data (1).csv" … (100)
#    - "AVAILABILITY-data - 2026-*.csv"  (timestamped copies)
# ------------------------------------------------------------------
carpeta = os.path.dirname(os.path.abspath(__file__))
archivos = glob.glob(os.path.join(carpeta, "AVAILABILITY-data*.csv"))

print(f"Archivos encontrados: {len(archivos)}")

# ------------------------------------------------------------------
# 2. Read each file → extract (time, available_stores) pairs
# ------------------------------------------------------------------
all_records = []

for archivo in archivos:
    try:
        df = pd.read_csv(archivo, header=0)

        # The first 4 columns are metadata:
        #   Plot name | metric (sf_metric) | Value Prefix | Value Suffix
        # The remaining columns are timestamps with store-count values.
        timestamp_cols = df.columns[4:]  # timestamp strings
        values = df.iloc[0, 4:]          # corresponding store counts

        temp = pd.DataFrame({
            "time": timestamp_cols,
            "available_stores": values.values
        })

        all_records.append(temp)
    except Exception as e:
        print(f"  ⚠ Error leyendo {os.path.basename(archivo)}: {e}")

# ------------------------------------------------------------------
# 3. Concatenate, parse dates, deduplicate & sort
# ------------------------------------------------------------------
df_total = pd.concat(all_records, ignore_index=True)

# Convert available_stores to numeric (some cells may be empty)
df_total["available_stores"] = pd.to_numeric(df_total["available_stores"], errors="coerce")

# Clean the timezone text so pd.to_datetime can parse it
# "Sun Feb 01 2026 06:11:20 GMT-0500 (hora estándar de Colombia)"
# → "Sun Feb 01 2026 06:11:20 GMT-0500"
df_total["time"] = df_total["time"].str.replace(r"\s*\(.*\)\s*$", "", regex=True).str.strip()

# Parse to datetime
df_total["time"] = pd.to_datetime(df_total["time"], format="%a %b %d %Y %H:%M:%S GMT%z")

# Drop duplicates (overlapping edges between files) – keep first
df_total = df_total.drop_duplicates(subset="time", keep="first")

# Sort chronologically
df_total = df_total.sort_values("time").reset_index(drop=True)

# ------------------------------------------------------------------
# 4. Save result
# ------------------------------------------------------------------
output_path = os.path.join(carpeta, "Base_Unificada.csv")
df_total.to_csv(output_path, index=False)

print(f"\nFilas totales (sin duplicados): {len(df_total)}")
print(f"Rango: {df_total['time'].min()}  →  {df_total['time'].max()}")
print(f"Guardado en: {output_path}")
print("¡Proceso terminado!")
