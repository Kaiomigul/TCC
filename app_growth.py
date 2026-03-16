"""
App Streamlit: estratégia Growth (versão para GitHub / Streamlit Cloud).
Idêntico ao dashboard_growth.py, mas com caminhos relativos ao diretório do script.
Use: streamlit run app_growth.py (no deploy web).
"""
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path

# Versão web: caminhos relativos (repo no GitHub / Streamlit Cloud)
# Aceita CSV na pasta CSV/ ou na raiz do repo (junto do app_growth.py)
BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "CSV"
PATH_CONSOLIDADO = CSV_DIR / "consolidado_growth.csv" if (CSV_DIR / "consolidado_growth.csv").exists() else BASE_DIR / "consolidado_growth.csv"
PATH_RANKING = CSV_DIR / "ranking_growth.csv" if (CSV_DIR / "ranking_growth.csv").exists() else BASE_DIR / "ranking_growth.csv"


def valor_br_para_numero(s):
    if pd.isna(s) or s in ["-", ""]:
        return np.nan
    if isinstance(s, (int, float)):
        return float(s) if pd.notna(s) else np.nan
    s = str(s).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


@st.cache_data
def carregar_dados():
    if not PATH_CONSOLIDADO.exists() or not PATH_RANKING.exists():
        msg = (
            "Arquivos consolidado_growth e/ou ranking_growth não encontrados. "
            f"Procurados em: **{BASE_DIR.resolve()}** (raiz do repo) ou em **CSV/** dentro dela. "
            "Inclua no GitHub os arquivos **consolidado_growth.csv** e **ranking_growth.csv** na raiz ou na pasta CSV/."
        )
        return None, msg

    con = pd.read_csv(PATH_CONSOLIDADO, sep=";", encoding="latin1")
    rank = pd.read_csv(PATH_RANKING, sep=";", encoding="latin1")

    con["Data"] = pd.to_datetime(con["Data"], errors="coerce")
    rank["Data"] = pd.to_datetime(rank["Data"], errors="coerce")
    con = con.dropna(subset=["Data"])
    rank = rank.dropna(subset=["Data"])

    if "preco_fechamento" not in con.columns or "rank_agregado_ordem" not in rank.columns:
        return None, "Colunas preco_fechamento ou rank_agregado_ordem ausentes."

    df = rank.merge(
        con[["Ticker", "Data", "preco_fechamento"]],
        on=["Ticker", "Data"],
        how="inner",
    )
    df["preco"] = df["preco_fechamento"].apply(valor_br_para_numero)
    df = df.dropna(subset=["preco", "rank_agregado_ordem"])

    return df, None


def aplicar_top_bottom_n(df: pd.DataFrame, n: int) -> pd.DataFrame:
    df = df.copy()
    df["_max_rank"] = df.groupby("Data")["rank_agregado_ordem"].transform("max")
    df["top_quintil"] = df["rank_agregado_ordem"] <= n
    df["bottom_quintil"] = df["rank_agregado_ordem"] > df["_max_rank"] - n
    df = df.drop(columns=["_max_rank"])
    return df


def retornos_e_base100(df):
    datas = sorted(df["Data"].unique())
    if len(datas) < 2:
        return pd.DataFrame(), pd.DataFrame()

    preco_largo = df.drop_duplicates(subset=["Ticker", "Data"])[["Ticker", "Data", "preco"]].pivot(
        index="Ticker", columns="Data", values="preco"
    )
    preco_largo = preco_largo.sort_index(axis=1)

    linhas = []
    for i in range(len(datas) - 1):
        d0, d1 = datas[i], datas[i + 1]
        sub = df[df["Data"] == d0]
        top_tickers = set(sub[sub["top_quintil"]]["Ticker"])
        bot_tickers = set(sub[sub["bottom_quintil"]]["Ticker"])

        if d0 not in preco_largo.columns or d1 not in preco_largo.columns:
            continue

        retornos = (preco_largo[d1] - preco_largo[d0]) / preco_largo[d0]
        r_top = retornos[retornos.index.isin(top_tickers)].dropna()
        r_bot = retornos[retornos.index.isin(bot_tickers)].dropna()

        n_top, n_bot = len(r_top), len(r_bot)
        ret_long = r_top.mean() if n_top else 0.0
        ret_bot_raw = r_bot.mean() if n_bot else 0.0
        ret_short_pnl = -ret_bot_raw
        ret_comb = ret_long + ret_short_pnl

        linhas.append({
            "Data_ini": d0,
            "Data_fim": d1,
            "ret_long": ret_long,
            "ret_short": ret_short_pnl,
            "ret_combinado": ret_comb,
            "n_long": n_top,
            "n_short": n_bot,
        })

    ret = pd.DataFrame(linhas)
    if ret.empty:
        return ret, pd.DataFrame()

    base = 100.0
    b100_long = [base]
    b100_short = [base]
    b100_comb = [base]
    for _, r in ret.iterrows():
        b100_long.append(b100_long[-1] * (1 + r["ret_long"]))
        b100_short.append(b100_short[-1] * (1 + r["ret_short"]))
        b100_comb.append(b100_comb[-1] * (1 + r["ret_combinado"]))

    datas_b100 = [ret["Data_ini"].iloc[0]] + list(ret["Data_fim"])
    df_b100 = pd.DataFrame({
        "Data": datas_b100,
        "Long_top5": b100_long,
        "Short_bottom5": b100_short,
        "Combinado_long_short": b100_comb,
    })
    return ret, df_b100


def main():
    st.set_page_config(page_title="Estratégia Growth – Base 100", layout="wide")
    st.title("Estratégia Growth: Top 5 vs Bottom 5 (Base 100)")

    df, erro = carregar_dados()
    if erro:
        st.error(erro)
        return

    n_ativos = st.slider(
        "Número de ativos em Long (Buy) e em Short em cada período",
        min_value=3,
        max_value=20,
        value=5,
        step=1,
        help="Em cada trimestre: as N melhores do ranking de crescimento ficam Long, as N piores Short.",
    )
    df = aplicar_top_bottom_n(df, n_ativos)

    st.caption(f"Long = top {n_ativos} (maior crescimento 3Y); Short = bottom {n_ativos} (menor crescimento). Rebalanceamento a cada trimestre.")

    ret_periodo, base100 = retornos_e_base100(df)
    if base100.empty:
        st.warning("Poucos períodos ou dados insuficientes para calcular retornos.")
        return

    st.subheader("Evolução em base 100")
    st.line_chart(
        base100.set_index("Data")[["Long_top5", "Short_bottom5", "Combinado_long_short"]],
        height=400,
    )

    ult = base100.iloc[-1]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Long (top crescimento)", f"{ult['Long_top5']:.1f}", f"{ult['Long_top5'] - 100:.1f} pts")
    with col2:
        st.metric("Short (bottom crescimento)", f"{ult['Short_bottom5']:.1f}", f"{ult['Short_bottom5'] - 100:.1f} pts")
    with col3:
        st.metric("Combinado (long − short)", f"{ult['Combinado_long_short']:.1f}", f"{ult['Combinado_long_short'] - 100:.1f} pts")

    st.subheader("Retornos por período (rebalanceamento)")
    st.caption("**Ret % Short** = retorno da posição short (positivo quando as ações do bottom caem). **Ret % Combinado** = Long + Short.")
    ret_periodo["ret_long"] = (ret_periodo["ret_long"] * 100).round(2)
    ret_periodo["ret_short"] = (ret_periodo["ret_short"] * 100).round(2)
    ret_periodo["ret_combinado"] = (ret_periodo["ret_combinado"] * 100).round(2)
    ret_periodo = ret_periodo.rename(columns={
        "Data_ini": "Início",
        "Data_fim": "Fim",
        "ret_long": "Ret % Long",
        "ret_short": "Ret % Short",
        "ret_combinado": "Ret % Combinado",
        "n_long": "N Long",
        "n_short": "N Short",
    })
    st.dataframe(ret_periodo, use_container_width=True, hide_index=True)

    st.subheader("Por trimestre: Buy vs Short")
    st.caption(f"**Long (Buy)** = top {n_ativos} do ranking de crescimento; **Short** = bottom {n_ativos}. Verde = em Long; vermelho = em Short.")
    st.caption("_Em períodos com menos ativos no universo, Long/Short podem ter menos que N tickers._")
    datas_disponiveis = sorted(df["Data"].unique())
    data_sel = st.selectbox(
        "Escolha o trimestre (t)",
        options=datas_disponiveis,
        format_func=lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x),
    )
    if data_sel is not None:
        sub = df[df["Data"] == data_sel].copy()
        sub = sub.sort_values("rank_agregado_ordem")
        buy_full = sub[["Ticker", "rank_agregado_ordem"]].head(20).rename(columns={"rank_agregado_ordem": "Rank"}).reset_index(drop=True)
        short_full = sub[["Ticker", "rank_agregado_ordem"]].sort_values("rank_agregado_ordem", ascending=False).head(20).rename(columns={"rank_agregado_ordem": "Rank"}).reset_index(drop=True)

        def _verde(s, n):
            return ["background-color: #d4edda" if s.name < n else "" for _ in s]

        def _vermelho(s, n):
            return ["background-color: #f8d7da" if s.name < n else "" for _ in s]

        col_b, col_s = st.columns(2)
        with col_b:
            st.markdown(f"**Long (Buy)** — até 20 (verde = top {n_ativos} em carteira)")
            if buy_full.empty:
                st.info("Nenhum ticker neste trimestre.")
            else:
                n_verde = min(n_ativos, len(buy_full))
                st.dataframe(buy_full.style.apply(lambda s: _verde(s, n_verde), axis=1), use_container_width=True, hide_index=True)
        with col_s:
            st.markdown(f"**Short** — até 20 (vermelho = bottom {n_ativos} em carteira)")
            if short_full.empty:
                st.info("Nenhum ticker neste trimestre.")
            else:
                n_vermelho = min(n_ativos, len(short_full))
                st.dataframe(short_full.style.apply(lambda s: _vermelho(s, n_vermelho), axis=1), use_container_width=True, hide_index=True)

    with st.expander("Ver série base 100 (tabela)"):
        base100_show = base100.copy()
        base100_show["Long_top5"] = base100_show["Long_top5"].round(2)
        base100_show["Short_bottom5"] = base100_show["Short_bottom5"].round(2)
        base100_show["Combinado_long_short"] = base100_show["Combinado_long_short"].round(2)
        st.dataframe(base100_show, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
