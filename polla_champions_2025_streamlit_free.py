from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

# NEW: seguridad al escribir archivos
from contextlib import contextmanager
from filelock import FileLock  # pip install filelock

APP_TITLE = "Desafío Champions 2025-26 - OPP 🏆⚽"
DATA_DIR = Path("data")
FIXTURES_CSV = DATA_DIR / "fixtures.csv"
PICKS_CSV = DATA_DIR / "picks.csv"
RESULTS_CSV = DATA_DIR / "results.csv"
CONFIG_JSON = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "points_exact": 3,
    "points_outcome": 1,
    "admin_password": "admin123",
    "show_local_time": True,
}

# -------------------- Persistencia --------------------

def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# NEW: helpers de escritura segura
@contextmanager
def _locked(path: Path, timeout: int = 5):
    """Candado por archivo para evitar colisiones de escritura."""
    lock = FileLock(str(path) + ".lock", timeout=timeout)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()

def _write_atomic_csv(df: pd.DataFrame, path: Path):
    """Escritura atómica: escribe a .tmp y reemplaza."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)

def load_config() -> dict:
    ensure_data_dir()
    if not CONFIG_JSON.exists():
        CONFIG_JSON.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    cfg = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg

def save_config(cfg: dict) -> None:
    ensure_data_dir()
    with _locked(CONFIG_JSON):
        CONFIG_JSON.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def load_picks() -> pd.DataFrame:
    ensure_data_dir()
    if not PICKS_CSV.exists():
        cols = ["name", "match_id", "home_pred", "away_pred", "ts_utc"]
        pd.DataFrame(columns=cols).to_csv(PICKS_CSV, index=False)
    df = pd.read_csv(PICKS_CSV)
    if not df.empty:
        df["match_id"] = df["match_id"].astype(int)
        df["home_pred"] = df["home_pred"].astype(int)
        df["away_pred"] = df["away_pred"].astype(int)
    return df

def save_picks(df: pd.DataFrame) -> None:
    """Ahora escribe con candado + atómico para evitar pisadas."""
    ensure_data_dir()
    with _locked(PICKS_CSV):
        _write_atomic_csv(df, PICKS_CSV)

def load_results() -> pd.DataFrame:
    ensure_data_dir()
    if not RESULTS_CSV.exists():
        cols = ["match_id", "home_goals", "away_goals"]
        pd.DataFrame(columns=cols).to_csv(RESULTS_CSV, index=False)
    df = pd.read_csv(RESULTS_CSV)
    if not df.empty:
        df["match_id"] = df["match_id"].astype(int)
        df["home_goals"] = df["home_goals"].astype(int)
        df["away_goals"] = df["away_goals"].astype(int)
    return df

def save_results(df: pd.DataFrame) -> None:
    """Ahora escribe con candado + atómico para evitar pisadas."""
    ensure_data_dir()
    with _locked(RESULTS_CSV):
        _write_atomic_csv(df, RESULTS_CSV)

def load_fixtures() -> pd.DataFrame:
    if not FIXTURES_CSV.exists():
        return pd.DataFrame(columns=["match_id", "stage", "kickoff_utc", "home", "away"])  # vacío
    df = pd.read_csv(FIXTURES_CSV)
    need = {"match_id", "stage", "kickoff_utc", "home", "away"}
    if not need.issubset(df.columns):
        st.error(f"El fixtures.csv no tiene columnas requeridas: {need - set(df.columns)}")
        return pd.DataFrame(columns=list(need))
    df["match_id"] = pd.to_numeric(df["match_id"], errors="coerce").fillna(0).astype(int)
    return df

# -------------------- Utilidades --------------------

def parse_to_aware_utc(s: str | None):
    if not s or str(s).strip() in ("", "nan"):
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def outcome(h: int, a: int) -> str:
    if h > a: return "H"
    if h < a: return "A"
    return "D"

def compute_scores(fixtures: pd.DataFrame, picks: pd.DataFrame, results: pd.DataFrame, points_exact: int, points_outcome: int):
    if picks.empty or results.empty:
        return pd.DataFrame(columns=["name", "points"]), pd.DataFrame(columns=[])
    df = picks.merge(results, on="match_id", how="inner")
    if df.empty:
        return pd.DataFrame(columns=["name", "points"]), pd.DataFrame(columns=[])
    exact = (df["home_pred"] == df["home_goals"]) & (df["away_pred"] == df["away_goals"])
    same_outcome = df.apply(lambda r: outcome(int(r.home_pred), int(r.away_pred)) == outcome(int(r.home_goals), int(r.away_goals)), axis=1)
    df["points"] = 0
    df.loc[same_outcome, "points"] = points_outcome
    df.loc[exact, "points"] = points_exact
    ranking = df.groupby("name", as_index=False)["points"].sum().sort_values(["points", "name"], ascending=[False, True])
    detail_cols = ["name", "match_id", "home_pred", "away_pred", "home_goals", "away_goals", "points"]
    detail = df[detail_cols].copy()
    return ranking, detail

def is_locked(kickoff_utc: str | None) -> bool:
    dt = parse_to_aware_utc(kickoff_utc)
    if dt is None: return False
    return datetime.now(timezone.utc) >= dt

# -------------------- Estilos --------------------
CSS = """
<style>
/* Ancho general controlado y espacio superior para que el título no se corte */
.block-container { max-width: 980px !important; padding-top: 1.6rem !important; }
h1 { margin-top: .1rem !important; }

/* Cabecera de etapa */
.stage-header { margin: 18px 0 8px; padding: 10px 14px; font-weight: 700; background: #1f2937; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08); }

/* Grid: 2 tarjetas por fila */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

/* Tarjeta más liviana (sin bloques gruesos) */
.card { background: transparent; border: none; padding: 6px 8px; }
/* Línea divisoria fina reutilizable */
.thin-sep { height:1px; background: rgba(255,255,255,0.14); margin: 10px 0 4px; border-radius: 0; }
.card .thin-sep:not(:last-child) { display: none; }

/* Cabecera de tarjeta */
.card-top { font-size: 12px; opacity: .85; display:flex; justify-content: space-between; align-items:center; margin-bottom: 6px; }
.status { display:inline-flex; align-items:center; gap: 6px; font-size: 12px; font-weight: 600; }
.dot { width: 10px; height: 10px; border-radius: 50%; display:inline-block; background:#22c55e; }

/* Filas de equipos */
.team-row { display:grid; grid-template-columns: 1fr auto; align-items:center; padding: 6px 0; }
.team-name { font-weight: 600; }

/* Inputs compactos */
input[type="number"] { width: 70px !important; }
</style>
"""

# -------------------- UI --------------------

st.set_page_config(page_title=APP_TITLE, page_icon="⚽", layout="wide")
st.title(APP_TITLE)
st.markdown(CSS, unsafe_allow_html=True)

cfg = load_config()
fixtures = load_fixtures()
picks = load_picks()
results = load_results()

with st.expander("ℹ️ ¿Cómo funciona?", expanded=False):
    st.markdown(
        f"""
        **Participa:** Ingresa tu nombre y tus pronósticos por partido. Cada partido se cierra automáticamente a la hora de inicio.

        **Puntaje:**  
        - ✅ Resultado exacto **{cfg['points_exact']} puntos**
        - ➕ Acertar solo el ganador/empate: **{cfg['points_outcome']} punto**.

        **Admin:** Con la contraseña puedes cargar o editar los resultados oficiales y ajustar la tabla de partidos o la puntuación.
        """
    )

participar_tab, admin_tab, ranking_tab, consulta_tab, config_tab = st.tabs(["🎟️ Participar", "🛠️ Admin", "🏆 Ranking", "🔎 Mis pronósticos", "⚙️ Configuración"])

# ---------- Render de tarjeta de partido ----------

def _utc_lima_text(dt_utc: datetime | None, show_lima=True) -> str:
    if not dt_utc:
        return ""
    utc_txt = dt_utc.strftime('%a, %d %b %H:%M')
    lima_txt = ''
    if show_lima:
        lima = dt_utc.astimezone(ZoneInfo('America/Lima'))
        lima_txt = f" · Lima: {lima.strftime('%Y-%m-%d %H:%M')}"
    return f"UTC: {utc_txt}{lima_txt}"

def render_match_card(row, name: str, picks_df: pd.DataFrame, cfg: dict):
    match_id = int(row['match_id'])
    home = str(row['home']); away = str(row['away'])
    dt_utc = parse_to_aware_utc(row.get('kickoff_utc'))
    locked = is_locked(row.get('kickoff_utc'))

    # Recuperar predicciones previas del usuario (si existen)
    h_prev = a_prev = 0
    if name and not picks_df.empty:
        prev = picks_df[(picks_df['name'].astype(str).str.lower()==name.lower()) & (picks_df['match_id']==match_id)]
        if not prev.empty:
            h_prev = int(prev['home_pred'].iloc[0]); a_prev = int(prev['away_pred'].iloc[0])

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    # línea divisoria fina arriba (reemplaza separadores gruesos)
    st.markdown("<div class='thin-sep'></div>", unsafe_allow_html=True)

    # Cabecera (hora + estado)
    status_text = "Abierto" if not locked else "Cerrado"
    utc_lima_txt = _utc_lima_text(dt_utc, cfg.get("show_local_time", True))
    top_html = (
        f"<div class='card-top'>{utc_lima_txt}"
        f"<span class='status'><span class='dot'></span> {status_text}</span></div>"
    )
    st.markdown(top_html, unsafe_allow_html=True)

    # Fila HOME
    c1, c2 = st.columns([1.0, 0.32])
    with c1:
        st.markdown(f"<div class='team-row'><div class='team-name'>{home}</div></div>", unsafe_allow_html=True)
    with c2:
        st.number_input(" ", 0, 20, h_prev, key=f"h_{match_id}", disabled=locked, label_visibility="collapsed")

    # Fila AWAY
    c1, c2 = st.columns([1.0, 0.32])
    with c1:
        st.markdown(f"<div class='team-row'><div class='team-name'>{away}</div></div>", unsafe_allow_html=True)
    with c2:
        st.number_input("  ", 0, 20, a_prev, key=f"a_{match_id}", disabled=locked, label_visibility="collapsed")

    # línea divisoria fina abajo
    st.markdown("<div class='thin-sep'></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)  # /card

def render_result_card_admin(row, results_df: pd.DataFrame, cfg: dict):
    """Tarjeta idéntica visualmente a las de pronóstico, pero con inputs de RESULTADO oficial."""
    match_id = int(row['match_id'])
    home = str(row['home']); away = str(row['away'])
    dt_utc = parse_to_aware_utc(row.get('kickoff_utc'))

    # valores actuales (si existen)
    h_prev = a_prev = 0
    if not results_df.empty:
        prev = results_df[results_df['match_id'] == match_id]
        if not prev.empty:
            h_prev = int(prev['home_goals'].iloc[0]); a_prev = int(prev['away_goals'].iloc[0])

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='thin-sep'></div>", unsafe_allow_html=True)

    utc_lima_txt = _utc_lima_text(dt_utc, cfg.get("show_local_time", True))
    top_html = (
        f"<div class='card-top'>{utc_lima_txt}"
        f"<span class='status'><span class='dot'></span> Resultado</span></div>"
    )
    st.markdown(top_html, unsafe_allow_html=True)

    # HOME
    c1, c2 = st.columns([1.0, 0.32])
    with c1:
        st.markdown(f"<div class='team-row'><div class='team-name'>{home}</div></div>", unsafe_allow_html=True)
    with c2:
        st.number_input(" ", 0, 20, h_prev, key=f"res_h_{match_id}", label_visibility="collapsed")

    # AWAY
    c1, c2 = st.columns([1.0, 0.32])
    with c1:
        st.markdown(f"<div class='team-row'><div class='team-name'>{away}</div></div>", unsafe_allow_html=True)
    with c2:
        st.number_input("  ", 0, 20, a_prev, key=f"res_a_{match_id}", label_visibility="collapsed")

    st.markdown("<div class='thin-sep'></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)  # /card

# ------------- Participar -------------
with participar_tab:
    st.subheader("Ingresa tus pronósticos")
    name = st.text_input("Tu nombre (Alias)", max_chars=40)
    if name and (picks["name"].astype(str).str.lower()==name.lower()).any():
        st.info("Si vuelves a enviar, se **actualizan** para partidos abiertos.")

    st.caption("Las horas se basan en UTC y, opcionalmente, en hora Lima.")

    if fixtures.empty:
        st.warning("No hay fixtures cargados. Ve a Admin para subir fixtures.csv")
    else:
        fx = fixtures.copy()
        fx['_dt'] = fx['kickoff_utc'].apply(parse_to_aware_utc)
        fx = fx.sort_values(['_dt','stage','match_id']).drop(columns=['_dt']).reset_index(drop=True)

        stages = fx['stage'].dropna().unique().tolist()
        stage_filter = st.selectbox("Filtrar por jornada / etapa", ["Todas"] + stages, index=0)
        if stage_filter != "Todas":
            fx = fx[fx['stage']==stage_filter]

        for stage, df_stage in fx.groupby('stage', sort=False):
            st.markdown(f"<div class='stage-header'>{stage}</div>", unsafe_allow_html=True)
            # Pinta SIEMPRE 2 partidos por fila usando st.columns
            pairs = [df_stage.iloc[i:i+2] for i in range(0, len(df_stage), 2)]
            for pair in pairs:
                c1, c2 = st.columns(2, gap="small")
                with c1:
                    render_match_card(pair.iloc[0], name, picks, cfg)
                with c2:
                    if len(pair) > 1:
                        render_match_card(pair.iloc[1], name, picks, cfg)

    if st.button("Enviar/Actualizar mis pronósticos", type="primary", use_container_width=True):
        if not name or not name.strip():
            st.error("Ingresa tu nombre.")
        elif fixtures.empty:
            st.warning("No hay fixtures cargados.")
        else:
            new_rows = []
            for _, row in fx.iterrows():
                match_id = int(row['match_id'])
                if is_locked(row.get('kickoff_utc')): continue
                h_val = int(st.session_state.get(f"h_{match_id}", 0))
                a_val = int(st.session_state.get(f"a_{match_id}", 0))
                new_rows.append({
                    "name": name.strip(), "match_id": match_id,
                    "home_pred": h_val, "away_pred": a_val,
                    "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                })
            if new_rows:
                df_new = pd.DataFrame(new_rows)
                open_ids = df_new['match_id'].unique()
                keep = ~((picks['name'].astype(str).str.lower()==name.lower()) & (picks['match_id'].isin(open_ids)))
                picks_updated = pd.concat([picks[keep], df_new], ignore_index=True)
                save_picks(picks_updated)
                st.success("¡Pronósticos guardados/actualizados!")
            else:
                st.info("No había partidos abiertos para actualizar.")

# ------------- Admin -------------
with admin_tab:
    st.subheader("Administración")
    pwd = st.text_input("Contraseña de admin", type="password")
    ok = False
    try:
        secret_pwd = st.secrets["ADMIN_PASSWORD"]
    except Exception:
        secret_pwd = None
    expected = secret_pwd or cfg.get("admin_password", "admin123")
    if pwd == expected:
        ok = True
        st.success("Acceso concedido")
    else:
        st.info("Ingresa la contraseña para editar resultados o configuración")

    if ok:
        st.markdown("### Fixtures (CSV)")
        st.caption("Columnas: match_id, stage, kickoff_utc (UTC: YYYY-MM-DD HH:MM), home, away")
        c1,c2,c3 = st.columns(3)
        with c1:
            if st.button("Cargar ejemplo (auto)"):
                sample = [
                    (1, "Fase de liga - J1", "2025-09-16 19:00", "Real Madrid", "Inter"),
                    (2, "Fase de liga - J1", "2025-09-16 19:00", "Man City", "Bayern"),
                    (3, "Fase de liga - J1", "2025-09-17 19:00", "Barcelona", "PSG"),
                    (4, "Fase de liga - J1", "2025-09-17 19:00", "Arsenal", "Juventus"),
                    (100, "Octavos de final", "2026-02-17 20:00", "Real Madrid", "Juventus"),
                ]
                df_ex = pd.DataFrame(sample, columns=["match_id","stage","kickoff_utc","home","away"])
                ensure_data_dir(); df_ex.to_csv(FIXTURES_CSV, index=False)
                st.success("Ejemplo guardado. Recarga la página.")
        with c2:
            st.download_button(
                "Descargar plantilla fixtures.csv",
                data=pd.DataFrame(columns=["match_id","stage","kickoff_utc","home","away"]).to_csv(index=False).encode("utf-8"),
                file_name="fixtures_template.csv",
            )
        with c3:
            up = st.file_uploader("Subir fixtures.csv", type=["csv"], accept_multiple_files=False)
            if up is not None:
                try:
                    new_fx = pd.read_csv(up)
                    need = {"match_id","stage","kickoff_utc","home","away"}
                    if not need.issubset(new_fx.columns):
                        st.error(f"Faltan columnas requeridas: {need}")
                    else:
                        new_fx["match_id"] = pd.to_numeric(new_fx["match_id"], errors="coerce").fillna(0).astype(int)
                        new_fx.to_csv(FIXTURES_CSV, index=False)
                        st.success("Fixtures actualizados. Recarga la página.")
                except Exception as e:
                    st.error(f"Error al procesar CSV: {e}")

        st.markdown("### Resultados oficiales")

        fx_admin = load_fixtures()
        if fx_admin.empty:
            st.warning("Carga fixtures antes de editar resultados.")
        else:
            # merge para saber resultados actuales
            res_admin = results.copy()
            base = fx_admin.merge(res_admin, on="match_id", how="left")
            base["home_goals"] = base["home_goals"].fillna(0).astype(int)
            base["away_goals"] = base["away_goals"].fillna(0).astype(int)

            # === Filtro por jornada/etapa (igual que Participar) ===
            stages = base['stage'].dropna().unique().tolist()
            stage_filter_admin = st.selectbox("Filtrar por jornada / etapa", ["Todas"] + stages, index=0, key="stage_admin")
            if stage_filter_admin != "Todas":
                base = base[base['stage'] == stage_filter_admin]

            # Orden lógico por fecha
            base['_dt'] = base['kickoff_utc'].apply(parse_to_aware_utc)
            base = base.sort_values(['_dt','stage','match_id']).drop(columns=['_dt']).reset_index(drop=True)

            # Render por etapa, en 2 tarjetas por fila (mismo look & feel)
            edits = []
            for stage, df_stage in base.groupby('stage', sort=False):
                st.markdown(f"<div class='stage-header'>{stage}</div>", unsafe_allow_html=True)
                pairs = [df_stage.iloc[i:i+2] for i in range(0, len(df_stage), 2)]
                for pair in pairs:
                    c1, c2 = st.columns(2, gap="small")
                    with c1:
                        r0 = pair.iloc[0]
                        render_result_card_admin(r0, res_admin, cfg)
                        edits.append({
                            "match_id": int(r0["match_id"]),
                            "home_goals": int(st.session_state.get(f"res_h_{int(r0['match_id'])}", 0)),
                            "away_goals": int(st.session_state.get(f"res_a_{int(r0['match_id'])}", 0)),
                        })
                    with c2:
                        if len(pair) > 1:
                            r1 = pair.iloc[1]
                            render_result_card_admin(r1, res_admin, cfg)
                            edits.append({
                                "match_id": int(r1["match_id"]),
                                "home_goals": int(st.session_state.get(f"res_h_{int(r1['match_id'])}", 0)),
                                "away_goals": int(st.session_state.get(f"res_a_{int(r1['match_id'])}", 0)),
                            })

            # Botón de guardado
            if st.button("Guardar resultados", type="primary"):
                if edits:
                    save_results(pd.DataFrame(edits))
                    st.success("Resultados guardados.")
                else:
                    st.info("No hay partidos para guardar en el filtro actual.")

# ------------- Ranking -------------
with ranking_tab:
    st.subheader("Tabla de posiciones")
    ranking, detail = compute_scores(load_fixtures(), picks, results, cfg["points_exact"], cfg["points_outcome"]) if not picks.empty else (pd.DataFrame(), pd.DataFrame())
    if ranking is None or ranking.empty:
        st.info("Aún no hay ranking.")
    else:
        st.dataframe(ranking, use_container_width=True)
        st.markdown("### Detalle por partido")
        fixtures_now = load_fixtures()
        if detail is not None and not detail.empty and not fixtures_now.empty:
            teams = fixtures_now.set_index("match_id")[ ["home", "away"] ]
            detail = detail.merge(teams, left_on="match_id", right_index=True, how="left")
            cols = ["name","match_id","home","away","home_pred","away_pred","home_goals","away_goals","points"]
            st.dataframe(detail[cols].sort_values(["name","match_id"]))

# ------------- Mis pronósticos -------------
with consulta_tab:
    st.subheader("Consulta tus pronósticos por nombre")

    # Recargamos picks por si hubo cambios durante la sesión
    picks_all = load_picks()
    fx_all = load_fixtures()

    if picks_all.empty:
        st.info("Aún no hay pronósticos registrados.")
    else:
        # Lista de nombres registrados (únicos)
        nombres = sorted(picks_all["name"].astype(str).unique().tolist())

        # Si el usuario ya escribió su nombre en "Participar", lo preseleccionamos:
        preseleccion = 0
        if 'name' in locals() and isinstance(name, str) and name.strip():
            try:
                preseleccion = nombres.index(name.strip())
            except ValueError:
                preseleccion = 0

        nombre_sel = st.selectbox("Selecciona tu nombre (tal como lo registraste)", nombres, index=preseleccion)

        # Filtrado case-insensitive
        df_user = picks_all[picks_all["name"].astype(str).str.lower() == nombre_sel.lower()].copy()

        # Enriquecer con datos del fixture para mostrar equipos, etapa y hora
        if not fx_all.empty and not df_user.empty:
            df_user = df_user.merge(
                fx_all[["match_id", "stage", "kickoff_utc", "home", "away"]],
                on="match_id", how="left"
            )

            # Hora UTC y (opcional) hora Lima usando tus utilidades
            df_user["_dt"] = df_user["kickoff_utc"].apply(parse_to_aware_utc)

            # Formato hora Lima si la preferencia está activa
            if cfg.get("show_local_time", True):
                df_user["hora_lima"] = df_user["_dt"].apply(
                    lambda d: d.astimezone(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M") if d else ""
                )

            # Orden bonito por etapa y partido
            df_user = df_user.sort_values(["stage", "match_id"]).reset_index(drop=True)

            # Selección de columnas a mostrar
            cols_base = ["stage", "match_id", "home", "away", "home_pred", "away_pred", "kickoff_utc"]
            if "hora_lima" in df_user.columns:
                cols_base.insert(cols_base.index("kickoff_utc") + 1, "hora_lima")
            cols_base.append("ts_utc")  # marca de tiempo del envío

            st.dataframe(df_user[cols_base], use_container_width=True)

            # Descarga en CSV
            st.download_button(
                "Descargar mis pronósticos (CSV)",
                data=df_user[cols_base].to_csv(index=False).encode("utf-8"),
                file_name=f"pronosticos_{nombre_sel}.csv",
                use_container_width=True
            )
        else:
            st.info("No hay fixtures cargados o el usuario aún no tiene pronósticos.")

# ------------- Config -------------
with config_tab:
    st.subheader("Puntuación y preferencias")
    c1,c2 = st.columns(2)
    with c1:
        p_exact = st.number_input("Puntos por marcador exacto", 1, 10, int(cfg["points_exact"]))
        admin_password = st.text_input("Contraseña admin (local)", value=str(cfg.get("admin_password","admin123")), type="password")
    with c2:
        p_out = st.number_input("Puntos por ganador/empate", 0, 5, int(cfg["points_outcome"]))
        show_local_time = st.checkbox("Mostrar hora Lima (además de UTC)", value=bool(cfg.get("show_local_time", True)))
    if st.button("Guardar Configuración", type="primary"):
        save_config({
            "points_exact": int(p_exact),
            "points_outcome": int(p_out),
            "admin_password": admin_password,
            "show_local_time": bool(show_local_time),
        })
        st.success("Configuración guardada.")
