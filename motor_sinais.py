"""
================================================================
  MOTOR DE SINAIS B3 — Alpha Vantage Edition
  Calcula RSI + MACD + Bollinger Bands + Volume
  Gera ranking diário de ações e sinais de opções PUT/CALL
  Fonte de dados: Alpha Vantage (gratuito — 25 req/dia)
================================================================

INSTALAÇÃO (rode uma vez no terminal):
  pip install requests pandas numpy colorama tabulate

CONFIGURAÇÃO:
  1. Acesse https://www.alphavantage.co/support/#api-key
  2. Cadastre-se gratuitamente e copie sua chave
  3. Cole sua chave na variável AV_API_KEY abaixo

COMO USAR:
  python motor_sinais.py

LIMITE GRATUITO:
  25 requisições/dia — o script processa até 25 ações por dia
  Para processar mais, rode em dias diferentes ou assine o plano
  premium do Alpha Vantage (~$50/mês)
================================================================
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os
import json
import warnings

warnings.filterwarnings("ignore")

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ================================================================
#  CONFIGURAÇÕES — EDITE AQUI
# ================================================================

AV_API_KEY    = "RLTAZUQ4OM5F99Y2"     # Obtenha grátis em alphavantage.co/support OLMOL6MHD8DMW4EN RLTAZUQ4OM5F99Y2
# Opções: usando B3 diretamente (100% gratuito, sem API key)

# Top 15 ações mais líquidas da B3
# 15 ações = ~3 min na primeira execução, segundos nas seguintes (cache)
ACOES_B3 = [
    "PETR4.SAO",    # Petrobras       — maior volume da B3
    "VALE3.SAO",    # Vale            — segunda maior
    "ITUB4.SAO",    # Itaú Unibanco   — maior banco
    "BBDC4.SAO",    # Bradesco
    "BBAS3.SAO",    # Banco do Brasil
    "ABEV3.SAO",    # Ambev
    "WEGE3.SAO",    # WEG             — industrial top
    "PRIO3.SAO",    # PRIO            — petróleo
    "RADL3.SAO",    # Raia Drogasil
    "GGBR4.SAO",    # Gerdau
    "RENT3.SAO",    # Localiza        — locação de veículos
    "SUZB3.SAO",    # Suzano          — papel e celulose
    "EQTL3.SAO",    # Equatorial      — energia elétrica
    "HAPV3.SAO",    # Hapvida         — saúde
    "LREN3.SAO",    # Lojas Renner    — varejo
    "EMBJ3.SAO",    # Embraer         — aeronáutica
]

# Quantas ações processar (máximo 25 no plano gratuito)
MAX_ACOES = 16

# Pausa entre requisições — 5 req/minuto no plano gratuito = 12s de pausa
# Na segunda execução do dia o cache evita qualquer pausa
PAUSA_SEGUNDOS = 12

# Cache local — salva os dados baixados para não reprocessar
USAR_CACHE    = True
PASTA_CACHE   = "cache_av"

PESO_RSI       = 25
PESO_MACD      = 25
PESO_BOLLINGER = 25
PESO_VOLUME    = 25


# ================================================================
#  ALPHA VANTAGE — DOWNLOAD
# ================================================================

BASE_URL = "https://www.alphavantage.co/query"

def cache_path(ticker: str) -> str:
    os.makedirs(PASTA_CACHE, exist_ok=True)
    data_hoje = datetime.now().strftime("%Y%m%d")
    return f"{PASTA_CACHE}/{ticker}_{data_hoje}.json"


def baixar_dados_av(ticker: str) -> pd.DataFrame:
    """
    Baixa série diária do Alpha Vantage.
    Usa cache local para não gastar requisições desnecessárias.
    Retorna DataFrame com colunas: open, high, low, close, volume
    """
    # Verifica cache do dia
    if USAR_CACHE:
        caminho = cache_path(ticker)
        if os.path.exists(caminho):
            with open(caminho, "r") as f:
                dados = json.load(f)
            return _parse_av(dados, ticker)

    # Faz requisição ao Alpha Vantage
    params = {
        "function"   : "TIME_SERIES_DAILY",
        "symbol"     : ticker,
        "outputsize" : "compact",   # últimos 100 dias — suficiente para os indicadores
        "apikey"     : AV_API_KEY,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        dados = resp.json()

        # Salva cache
        if USAR_CACHE and "Time Series (Daily)" in dados:
            with open(cache_path(ticker), "w") as f:
                json.dump(dados, f)

        return _parse_av(dados, ticker)

    except Exception as e:
        return pd.DataFrame()


def _parse_av(dados: dict, ticker: str) -> pd.DataFrame:
    """Converte resposta do Alpha Vantage em DataFrame padronizado."""
    chave = "Time Series (Daily)"
    if chave not in dados:
        # Exibe mensagem de erro da API se houver
        if "Note" in dados:
            print(f"\n{Fore.YELLOW}  [AVISO] Limite de requisições por minuto atingido. "
                  f"Aguarde 1 minuto.{Style.RESET_ALL}")
        elif "Information" in dados:
            print(f"\n{Fore.RED}  [LIMITE DIÁRIO] As 25 requisições gratuitas de hoje foram esgotadas.")
            print(f"  Soluções:")
            print(f"    1. Apague a pasta cache_av e tente após meia-noite (1h horário Brasília)")
            print(f"    2. Use uma segunda chave gratuita em alphavantage.co/support")
            print(f"    3. Assine o plano premium do Alpha Vantage{Style.RESET_ALL}")
        elif "Error Message" in dados:
            print(f"\n{Fore.RED}  [ERRO API] {dados['Error Message']}{Style.RESET_ALL}")
        return pd.DataFrame()

    ts = dados[chave]
    df = pd.DataFrame(ts).T
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Renomeia colunas
    df.columns = [c.split(". ")[1] for c in df.columns]   # "1. open" → "open"
    df = df.astype(float)

    if len(df) < 30:
        return pd.DataFrame()

    return df


# ================================================================
#  INDICADORES
# ================================================================

def calc_rsi(closes: pd.Series, periodo: int = 14) -> float:
    delta = closes.diff()
    ganho = delta.clip(lower=0).rolling(periodo).mean()
    perda = (-delta.clip(upper=0)).rolling(periodo).mean()
    rs    = ganho / (perda + 1e-9)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def calc_macd(closes: pd.Series,
              rapida: int = 12, lenta: int = 26, sinal: int = 9):
    ema_r = closes.ewm(span=rapida, adjust=False).mean()
    ema_l = closes.ewm(span=lenta,  adjust=False).mean()
    linha = ema_r - ema_l
    sig   = linha.ewm(span=sinal,   adjust=False).mean()
    hist  = linha - sig
    return (
        round(float(linha.iloc[-1]), 6),
        round(float(sig.iloc[-1]),   6),
        round(float(hist.iloc[-1]),  6),
    )


def calc_bollinger(closes: pd.Series, periodo: int = 20, desvios: float = 2.0):
    media   = closes.rolling(periodo).mean()
    std     = closes.rolling(periodo).std()
    sup     = media + desvios * std
    inf     = media - desvios * std
    preco   = float(closes.iloc[-1])
    largura = float(sup.iloc[-1]) - float(inf.iloc[-1])
    posicao = ((preco - float(inf.iloc[-1])) / largura * 100) if largura > 0 else 50
    return (
        round(float(sup.iloc[-1]),   4),
        round(float(media.iloc[-1]), 4),
        round(float(inf.iloc[-1]),   4),
        round(float(posicao),        1),
    )


def calc_volume(volumes: pd.Series) -> dict:
    media_20 = float(volumes.rolling(20).mean().iloc[-1])
    atual    = float(volumes.iloc[-1])
    variacao = ((atual / media_20) - 1) * 100 if media_20 > 0 else 0
    return {
        "atual"    : int(atual),
        "media_20" : int(media_20),
        "variacao" : round(variacao, 1),
    }


# ================================================================
#  SCORE (0–100)
# ================================================================

def calcular_score_compra(rsi, macd_hist, macd_hist_ant,
                          bb_posicao, vol_variacao) -> float:
    if   rsi < 30: score_rsi = 100
    elif rsi < 40: score_rsi = 100 - (rsi - 30) * 3
    elif rsi < 50: score_rsi = 70  - (rsi - 40) * 3
    elif rsi < 65: score_rsi = 40  - (rsi - 50) * 2
    else:          score_rsi = max(0, 10 - (rsi - 65))

    if   macd_hist > 0 and macd_hist > macd_hist_ant: score_macd = 100
    elif macd_hist > 0:                                score_macd = 65
    elif macd_hist < 0 and macd_hist > macd_hist_ant: score_macd = 35
    else:                                              score_macd = 10

    if   bb_posicao < 20: score_bb = 100
    elif bb_posicao < 35: score_bb = 85
    elif bb_posicao < 50: score_bb = 60
    elif bb_posicao < 70: score_bb = 35
    else:                 score_bb = 10

    if   vol_variacao > 50:  score_vol = 100
    elif vol_variacao > 20:  score_vol = 80
    elif vol_variacao > 0:   score_vol = 65
    elif vol_variacao > -20: score_vol = 45
    else:                    score_vol = 20

    return round(
        score_rsi  * PESO_RSI       / 100 +
        score_macd * PESO_MACD      / 100 +
        score_bb   * PESO_BOLLINGER / 100 +
        score_vol  * PESO_VOLUME    / 100, 1
    )


# ================================================================
#  SINAL DE OPÇÕES
# ================================================================

def sinal_opcao(rsi, macd_hist, macd_hist_ant,
                bb_posicao, variacao_dia) -> dict:
    call, put = 0, 0

    if   rsi < 40: call += 3
    elif rsi < 55: call += 1
    if   rsi > 60: put  += 3
    elif rsi > 45: put  += 1

    if   macd_hist > 0 and macd_hist > macd_hist_ant: call += 3
    elif macd_hist > 0:                                call += 1
    if   macd_hist < 0 and macd_hist < macd_hist_ant: put  += 3
    elif macd_hist < 0:                                put  += 1

    if bb_posicao < 35: call += 2
    if bb_posicao > 65: put  += 2

    if variacao_dia >  1: put  += 1
    if variacao_dia < -1: call += 1

    total = call + put
    if total == 0:
        return {"direcao": "NEUTRO", "confianca": 0}
    if call > put:
        return {"direcao": "CALL", "confianca": round(call / total * 100)}
    if put > call:
        return {"direcao": "PUT",  "confianca": round(put  / total * 100)}
    return {"direcao": "NEUTRO", "confianca": 50}


# ================================================================
#  B3 PÚBLICA — SÉRIES DE OPÇÕES (100% GRATUITO, SEM API KEY)
# ================================================================
#
#  A B3 disponibiliza dois arquivos públicos e gratuitos:
#
#  1. COTAHIST_Dxx.ZIP — cotações do dia (inclui prêmio das opções)
#     URL: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_Dxx.ZIP
#
#  2. Séries Autorizadas — strike + vencimento de todas as opções
#     URL: https://www.b3.com.br/pesquisapregao/download?filelist=SA.zip
#
#  Ambos atualizados diariamente após o fechamento do pregão.
# ================================================================

import zipfile
import io
import struct
from datetime import date, timedelta

# Arquivo anual — contém mercados 070 (CALL) e 080 (PUT) com dados reais
# O diário só tem mercado 030 (termo), não serve para opções
B3_COTAHIST_URL  = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{aaaa}.ZIP"
PASTA_B3_CACHE   = "cache_b3"
_COTAHIST_LINHAS = None   # cache em memória — evita baixar 70MB várias vezes

# Alguns tickers usam prefixo diferente nas opções da B3
# Ex: EMBR3 → opções começam com EMBJ (não EMBR)
TICKER_PREFIXO_OPCAO = {
    "EMBJ3" : "EMBJ",   # Embraer
    "BBAS3" : "BBAS",   # Banco do Brasil (confirmar)
}


def _baixar_zip(url: str) -> bytes | None:
    """Baixa um arquivo ZIP de uma URL e retorna o conteúdo em bytes."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.content
        return None
    except Exception:
        return None


def _ano_atual() -> int:
    """Retorna o ano atual para o COTAHIST anual."""
    return datetime.now().year


def buscar_opcoes_b3(ticker: str, direcao: str, preco_acao: float) -> dict | None:
    """
    Busca a opção ATM (mais próxima do dinheiro) para o ticker,
    usando os arquivos públicos e gratuitos da B3.

    Estratégia:
      1. Baixa COTAHIST do último pregão (contém prêmio das opções)
      2. Filtra opções do ticker com vencimento >= 30 dias
      3. Retorna a opção com strike mais próximo do preço atual
    """
    os.makedirs(PASTA_B3_CACHE, exist_ok=True)

    global _COTAHIST_LINHAS

    ano = _ano_atual()
    cache_file = f"{PASTA_B3_CACHE}/cotahist_{ano}_{ticker}.json"

    # 1. Usa cache JSON do ticker se existir (mais rápido)
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            opcoes_cache = json.load(f)
        return _selecionar_atm(opcoes_cache, direcao, preco_acao)

    # 2. Usa arquivo já carregado em memória (evita baixar 70MB várias vezes)
    if _COTAHIST_LINHAS is None:
        url = B3_COTAHIST_URL.format(aaaa=ano)
        print(f"\n    {Fore.CYAN}[Opções] Baixando COTAHIST {ano} (~70MB, só uma vez...){Style.RESET_ALL}")
        conteudo = _baixar_zip(url)
        if not conteudo:
            print(f"\n    {Fore.YELLOW}[Opções] Não foi possível baixar o COTAHIST anual.{Style.RESET_ALL}")
            return None
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
            nome_txt = [n for n in z.namelist() if n.endswith(".TXT")][0]
            _COTAHIST_LINHAS = z.read(nome_txt).decode("latin-1").splitlines()
            print(f"    {Fore.GREEN}[Opções] COTAHIST carregado — {len(_COTAHIST_LINHAS):,} linhas{Style.RESET_ALL}")
        except Exception as e:
            print(f"    {Fore.RED}[Opções] Erro ao ler COTAHIST: {e}{Style.RESET_ALL}")
            return None

    # 3. Usa as linhas já carregadas em memória
    linhas = _COTAHIST_LINHAS
    if not linhas:
        return None

    # Parseia o COTAHIST (formato fixo — layout B3)
    # Tipo 01 = mercado de opções de compra / 02 = opções de venda
    # Referência do layout: https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E1JA1KOMU00/SeriesHistoricas_Layout.pdf
    hoje = date.today()
    opcoes_encontradas = []
    ticker_upper = ticker.upper()

    # Layout COTAHIST confirmado via diagnóstico do arquivo anual:
    # Mercado 070 = opções de COMPRA (CALL)
    # Mercado 080 = opções de VENDA (PUT)
    # Posições:
    #   [12:24] código da opção (ex: PETRV437)
    #   [24:27] mercado (070=CALL, 080=PUT)
    #   [108:121] preço de fechamento (13 dígitos, 2 decimais implícitos)
    #   [147:152] total de negócios
    #   [152:170] quantidade de títulos negociados (volume)
    #   [188:201] strike (13 dígitos, 2 decimais implícitos)
    #   [202:210] data de vencimento (AAAAMMDD)

    for linha in linhas:
        if len(linha) < 245:
            continue

        # Só tipo 01
        if linha[0:2] != "01":
            continue

        # Só mercados de opções: 070 (CALL) e 080 (PUT)
        tipo_mercado = linha[24:27].strip()
        if tipo_mercado not in ("070", "080"):
            continue

        # Verifica se é opção do ticker buscado
        # Usa mapeamento especial quando o prefixo da opção difere do ticker
        # Ex: EMBR3 → opções usam prefixo EMBJ na B3
        codigo_opcao = linha[12:24].strip()
        ticker_base5 = ticker_upper[:5]  # ex: PRIO3, BBDC4
        ticker_base4 = ticker_upper[:4]  # ex: PRIO, BBDC
        prefixo_especial = TICKER_PREFIXO_OPCAO.get(ticker_upper, "")

        match = (codigo_opcao.startswith(ticker_base5) or
                 codigo_opcao.startswith(ticker_base4))
        if prefixo_especial:
            match = match or codigo_opcao.startswith(prefixo_especial)
        if not match:
            continue

        try:
            # Vencimento
            vencimento_str = linha[202:210].strip()
            if len(vencimento_str) < 8 or not vencimento_str.isdigit():
                continue
            venc_dt = date(
                int(vencimento_str[0:4]),
                int(vencimento_str[4:6]),
                int(vencimento_str[6:8])
            )
            dias_venc = (venc_dt - hoje).days
            if dias_venc < 30:
                continue

            # Strike (posição 188:201, 2 decimais implícitos)
            strike_str = linha[188:201].strip()
            strike = int(strike_str) / 100 if strike_str.isdigit() else 0
            if strike == 0:
                continue

            # Prêmio = preço de fechamento (posição 108:121, 2 decimais)
            preco_str = linha[108:121].strip()
            premio = int(preco_str) / 100 if preco_str.isdigit() else 0

            # Volume (posição 152:170)
            vol_str = linha[152:170].strip()
            volume = int(vol_str) if vol_str.isdigit() else 0

            # CALL ou PUT pelo mercado
            lado = "CALL" if tipo_mercado == "070" else "PUT"

            opcoes_encontradas.append({
                "codigo"     : codigo_opcao,
                "lado"       : lado,
                "strike"     : strike,
                "vencimento" : venc_dt.strftime("%d/%m/%Y"),
                "venc_dt"    : venc_dt.isoformat(),
                "dias_venc"  : dias_venc,
                "premio"     : premio,
                "volume"     : volume,
            })
        except Exception:
            continue

    # Salva cache
    if opcoes_encontradas:
        with open(cache_file, "w") as f:
            json.dump(opcoes_encontradas, f)

    return _selecionar_atm(opcoes_encontradas, direcao, preco_acao)


def _selecionar_atm(opcoes: list, direcao: str, preco_acao: float) -> dict | None:
    """Filtra por direção e retorna a opção ATM com maior volume."""
    if not opcoes:
        return None

    filtradas = [o for o in opcoes if o["lado"] == direcao and o["volume"] > 0]
    if not filtradas:
        filtradas = [o for o in opcoes if o["lado"] == direcao]
    if not filtradas:
        return None

    # Ordena pelo vencimento mais próximo (>= 30 dias) e pelo strike mais próximo do preço
    filtradas.sort(key=lambda o: (o["dias_venc"], abs(o["strike"] - preco_acao)))
    return filtradas[0]


# ================================================================
#  PROCESSAR AÇÃO
# ================================================================

def processar_acao(ticker: str) -> dict | None:
    df = baixar_dados_av(ticker)
    if df.empty:
        return None

    closes  = df["close"]
    volumes = df["volume"]

    rsi                              = calc_rsi(closes)
    macd_l, macd_s, macd_h          = calc_macd(closes)
    macd_h_ant                       = calc_macd(closes.iloc[:-1])[2]
    bb_sup, bb_med, bb_inf, bb_pos   = calc_bollinger(closes)
    vol                              = calc_volume(volumes)

    preco_atual  = round(float(closes.iloc[-1]), 2)
    preco_ant    = round(float(closes.iloc[-2]), 2)
    variacao_dia = round(((preco_atual / preco_ant) - 1) * 100, 2)

    score = calcular_score_compra(
        rsi, macd_h, macd_h_ant, bb_pos, vol["variacao"]
    )
    opcao = sinal_opcao(
        rsi, macd_h, macd_h_ant, bb_pos, variacao_dia
    )

    mm9  = float(closes.rolling(9).mean().iloc[-1])
    mm21 = float(closes.rolling(21).mean().iloc[-1])

    # Ticker limpo para exibição (remove .SAO)
    ticker_limpo = ticker.replace(".SAO", "").replace(".SA", "")

    # Busca opção ATM nos arquivos públicos da B3 (100% gratuito)
    # Só busca para sinais com confiança >= 60%
    opcao_detalhe = None
    if opcao["direcao"] in ("CALL", "PUT") and opcao["confianca"] > 69:
        opcao_detalhe = buscar_opcoes_b3(
            ticker_limpo, opcao["direcao"], preco_atual
        )

    return {
        "ticker"        : ticker_limpo,
        "preco"         : preco_atual,
        "variacao_dia"  : variacao_dia,
        "tendencia"     : "ALTA" if mm9 > mm21 else "BAIXA",
        "rsi"           : rsi,
        "macd_hist"     : macd_h,
        "bb_posicao"    : bb_pos,
        "vol_variacao"  : vol["variacao"],
        "score"         : score,
        "opcao_direcao" : opcao["direcao"],
        "opcao_conf"    : opcao["confianca"],
        "opcao_codigo"  : opcao_detalhe["codigo"]     if opcao_detalhe else "—",
        "opcao_strike"  : opcao_detalhe["strike"]     if opcao_detalhe else 0,
        "opcao_venc"    : opcao_detalhe["vencimento"] if opcao_detalhe else "—",
        "opcao_dias"    : opcao_detalhe["dias_venc"]  if opcao_detalhe else 0,
        "opcao_premio"  : opcao_detalhe["premio"]     if opcao_detalhe else 0,
        "bb_sup"        : bb_sup,
        "bb_med"        : bb_med,
        "bb_inf"        : bb_inf,
    }


# ================================================================
#  RANKING
# ================================================================

def gerar_ranking() -> pd.DataFrame:
    print(f"\n{Fore.CYAN}{Style.BRIGHT}=== MOTOR DE SINAIS B3 — Alpha Vantage ==={Style.RESET_ALL}")
    print(f"Data  : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"Ações : {min(len(ACOES_B3), MAX_ACOES)} ações")
    print(f"Cache : {'Ativado' if USAR_CACHE else 'Desativado'}")
    print()

    if AV_API_KEY == "SUA_CHAVE_AQUI":
        print(f"{Fore.RED}⚠  ATENÇÃO: Configure sua chave do Alpha Vantage!")
        print(f"   1. Acesse: https://www.alphavantage.co/support/#api-key")
        print(f"   2. Cadastre-se gratuitamente")
        print(f"   3. Substitua 'SUA_CHAVE_AQUI' pela sua chave no arquivo{Style.RESET_ALL}")
        return pd.DataFrame()

    resultados = []
    acoes = ACOES_B3[:MAX_ACOES]

    for i, ticker in enumerate(acoes, 1):
        ticker_limpo = ticker.replace(".SAO", "")
        print(f"  [{i:02d}/{len(acoes)}] {ticker_limpo:<10}", end=" ", flush=True)

        # Verifica se vai usar cache ou fazer requisição
        usa_cache = USAR_CACHE and os.path.exists(cache_path(ticker))

        dado = processar_acao(ticker)

        if dado:
            resultados.append(dado)
            cor = (Fore.GREEN  if dado["score"] >= 60 else
                   Fore.YELLOW if dado["score"] >= 40 else Fore.RED)
            fonte = "(cache)" if usa_cache else ""
            print(f"{cor}Score: {dado['score']:5.1f} | "
                  f"RSI: {dado['rsi']:5.1f} | "
                  f"{dado['opcao_direcao']:<6} {fonte}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Erro ao baixar dados{Style.RESET_ALL}")

        # Pausa entre requisições (só se não usou cache)
        if not usa_cache and i < len(acoes):
            time.sleep(PAUSA_SEGUNDOS)

    if not resultados:
        print(f"\n{Fore.RED}Nenhum dado obtido. Verifique sua chave e conexão.{Style.RESET_ALL}")
        return pd.DataFrame()

    df = (pd.DataFrame(resultados)
            .sort_values("score", ascending=False)
            .reset_index(drop=True))
    df.index += 1
    return df


# ================================================================
#  EXIBIÇÃO
# ================================================================

def exibir_ranking(df: pd.DataFrame):
    if df.empty:
        return

    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*70}")
    print(f"  TOP 16 AÇÕES DA B3 — {datetime.now().strftime('%d/%m/%Y')}")
    print(f"{'='*70}{Style.RESET_ALL}\n")

    top16 = df.head(16)

    if HAS_TABULATE:
        tabela = []
        for i, row in top16.iterrows():
            var_str  = f"+{row['variacao_dia']}%" if row['variacao_dia'] >= 0 else f"{row['variacao_dia']}%"
            tend_str = "▲ ALTA" if row['tendencia'] == "ALTA" else "▼ BAIXA"
            tabela.append([
                i, row['ticker'],
                f"R$ {row['preco']:.2f}", var_str, tend_str,
                f"{row['rsi']:.1f}", f"{row['score']:.1f}",
                row['opcao_direcao'], f"{row['opcao_conf']}%",
            ])
        print(tabulate(tabela,
            headers=["#","Ticker","Preço","Var%","Tendência","RSI","Score","Opção","Conf."],
            tablefmt="rounded_outline"))
    else:
        print(f"{'#':<4}{'Ticker':<8}{'Preço':>10}{'Var%':>8}{'Tend':>8}"
              f"{'RSI':>6}{'Score':>7}{'Opção':>8}{'Conf':>7}")
        print("─" * 70)
        for i, row in top16.iterrows():
            var_str  = f"+{row['variacao_dia']}%" if row['variacao_dia'] >= 0 else f"{row['variacao_dia']}%"
            tend_str = "▲" if row['tendencia'] == "ALTA" else "▼"
            print(f"{i:<4}{row['ticker']:<8}R${row['preco']:>8.2f}"
                  f"{var_str:>8}{tend_str:>7}{row['rsi']:>6.1f}"
                  f"{row['score']:>7.1f}{row['opcao_direcao']:>8}"
                  f"{row['opcao_conf']:>6}%")

    # Opções
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*70}")
    print(f"  SINAIS DE OPÇÕES")
    print(f"{'='*70}{Style.RESET_ALL}\n")

    # Exibe só as que têm confiança > 69% E opção encontrada no COTAHIST
    calls = df[
        (df["opcao_direcao"] == "CALL") &
        (df["opcao_conf"] > 69) &
        (df["opcao_codigo"] != "—")
    ]
    puts = df[
        (df["opcao_direcao"] == "PUT") &
        (df["opcao_conf"] > 69) &
        (df["opcao_codigo"] != "—")
    ]

    def linha_opcao(r, cor):
        acao   = f"{r['ticker']:<8} R$ {r['preco']:>7.2f}"
        conf   = f"Conf: {r['opcao_conf']:>3}%"
        codigo = r.get("opcao_codigo", "—")
        strike = r.get("opcao_strike", 0)
        venc   = r.get("opcao_venc", "—")
        dias   = r.get("opcao_dias", 0)
        premio = r.get("opcao_premio", 0)
        print(f"  {cor}{Style.BRIGHT}{acao}  {conf}{Style.RESET_ALL}")
        if codigo != "—":
            print(f"    {'Código':<12}: {codigo}")
            print(f"    {'Strike':<12}: R$ {strike:.2f}")
            print(f"    {'Vencimento':<12}: {venc}  ({dias} dias)")
            if premio > 0:
                print(f"    {'Prêmio':<12}: R$ {premio:.2f}")
            else:
                print(f"    {'Prêmio':<12}: indisponível")
        else:
            # Opção não encontrada no COTAHIST — pode ser bloqueio ou arquivo ainda não disponível
            print(f"    {'Código':<12}: buscando no COTAHIST B3...")
            print(f"    {'Status':<12}: arquivo disponível após 19h do pregão")
            print(f"    {'Dica':<12}: rode novamente após as 19h para ver os detalhes")
        print()

    print(f"{Fore.GREEN}{Style.BRIGHT}  CALL — apostar em ALTA:{Style.RESET_ALL}\n")
    if calls.empty:
        print(f"    Nenhum sinal de CALL hoje\n")
    for _, r in calls.iterrows():
        linha_opcao(r, Fore.GREEN)

    print(f"{Fore.RED}{Style.BRIGHT}  PUT — apostar em QUEDA:{Style.RESET_ALL}\n")
    if puts.empty:
        print(f"    Nenhum sinal de PUT hoje\n")
    for _, r in puts.iterrows():
        linha_opcao(r, Fore.RED)


# ================================================================
#  SALVAR CSV — uma aba (planilha) por data, histórico completo
# ================================================================
#
#  Estrutura gerada:
#    resultados/
#      historico_sinais_b3.xlsx   ← arquivo único com uma aba por dia
#      sinais_20260911.csv        ← backup CSV individual por dia
#
#  Instale openpyxl uma vez:
#    pip install openpyxl
# ================================================================

ARQUIVO_HISTORICO = "resultados/historico_sinais_b3.xlsx"

def salvar_csv(df: pd.DataFrame):
    """
    Salva os sinais do dia de duas formas:
      1. CSV individual por dia (backup simples)
      2. Excel (.xlsx) com uma aba por data — histórico completo
    """
    if df.empty:
        return

    pasta = "resultados"
    os.makedirs(pasta, exist_ok=True)
    hoje  = datetime.now().strftime("%Y%m%d")
    nome_aba = datetime.now().strftime("%d-%m-%Y")

    # --- 1. CSV individual (backup) ---
    nome_csv = f"{pasta}/sinais_{hoje}.csv"
    df.to_csv(nome_csv, index=True)
    print(f"\n{Fore.GREEN}✓ CSV salvo em: {nome_csv}{Style.RESET_ALL}")

    # --- 2. Excel com histórico (uma aba por dia) ---
    try:
        from openpyxl import load_workbook
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        # Colunas a exibir na planilha
        colunas = {
            "ticker"        : "Ticker",
            "preco"         : "Preço (R$)",
            "variacao_dia"  : "Var. Dia %",
            "tendencia"     : "Tendência",
            "rsi"           : "RSI",
            "macd_hist"     : "MACD Hist",
            "bb_posicao"    : "Bollinger %",
            "vol_variacao"  : "Vol. Var %",
            "score"         : "Score",
            "opcao_direcao" : "Opção",
            "opcao_conf"    : "Confiança %",
            "opcao_codigo"  : "Cód. Opção",
            "opcao_strike"  : "Strike",
            "opcao_venc"    : "Vencimento",
            "opcao_premio"  : "Prêmio (R$)",
        }
        # Só usa colunas que existem no DataFrame
        colunas_ok = {k: v for k, v in colunas.items() if k in df.columns}

        # Carrega arquivo existente ou cria novo
        if os.path.exists(ARQUIVO_HISTORICO):
            wb = load_workbook(ARQUIVO_HISTORICO)
        else:
            wb = Workbook()
            # Remove aba padrão vazia
            if "Sheet" in wb.sheetnames:
                del wb["Sheet"]

        # Remove aba do dia se já existir (sobrescreve)
        if nome_aba in wb.sheetnames:
            del wb[nome_aba]

        # Cria nova aba para o dia — insere sempre na primeira posição
        ws = wb.create_sheet(title=nome_aba, index=0)

        # --- Linha 1: título ---
        ws.merge_cells("A1:O1")
        ws["A1"] = f"Sinais B3 — {nome_aba} — gerado às {datetime.now().strftime('%H:%M')}"
        ws["A1"].font      = Font(bold=True, size=12, color="FFFFFF")
        ws["A1"].fill      = PatternFill("solid", fgColor="1F4E79")
        ws["A1"].alignment = Alignment(horizontal="center")

        # --- Linha 2: cabeçalho das colunas ---
        cabecalhos = ["Rank"] + list(colunas_ok.values())
        for col_idx, cab in enumerate(cabecalhos, 1):
            cell = ws.cell(row=2, column=col_idx, value=cab)
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="2E75B6")
            cell.alignment = Alignment(horizontal="center")

        # --- Linhas de dados ---
        for row_idx, (i, row) in enumerate(df.iterrows(), 3):
            ws.cell(row=row_idx, column=1, value=i)  # Rank
            for col_idx, col_key in enumerate(colunas_ok.keys(), 2):
                val = row.get(col_key, "—")
                if isinstance(val, float):
                    val = round(val, 2)
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.alignment = Alignment(horizontal="center")

                # Cor da linha alternada
                if row_idx % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="DEEAF1")

                # Destaque score alto
                if col_key == "score":
                    if isinstance(val, (int, float)) and val >= 60:
                        cell.font = Font(bold=True, color="006400")
                    elif isinstance(val, (int, float)) and val < 40:
                        cell.font = Font(color="8B0000")

                # Destaque opção CALL/PUT
                if col_key == "opcao_direcao":
                    if val == "CALL":
                        cell.font = Font(bold=True, color="006400")
                    elif val == "PUT":
                        cell.font = Font(bold=True, color="8B0000")

        # Ajusta largura das colunas automaticamente
        for col_idx in range(1, len(cabecalhos) + 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 14

        # Congela linha do cabeçalho
        ws.freeze_panes = "A3"

        # Salva
        wb.save(ARQUIVO_HISTORICO)
        print(f"{Fore.GREEN}✓ Histórico atualizado: {ARQUIVO_HISTORICO}")
        print(f"  Aba criada: '{nome_aba}' ({len(df)} ações){Style.RESET_ALL}")

    except ImportError:
        print(f"{Fore.YELLOW}⚠  Para salvar o histórico Excel instale: pip install openpyxl{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}⚠  Erro ao salvar histórico: {e}{Style.RESET_ALL}")
# ================================================================
#  MAIN
# ================================================================

if __name__ == "__main__":
    ranking = gerar_ranking()
    exibir_ranking(ranking)
    salvar_csv(ranking)

    # --- Envia automaticamente para o Supabase ---
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "supabase"))
        from supabase_client import enviar_sinais
        print(f"\n{Fore.CYAN}Enviando sinais para o Supabase...{Style.RESET_ALL}")
        enviar_sinais(ranking)
    except ImportError:
        print(f"\n{Fore.YELLOW}⚠  supabase_client.py não encontrado na pasta supabase/")
        print(f"   Siga o GUIA_SUPABASE.txt para configurar.{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}⚠  Erro ao enviar para Supabase: {e}{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Rode novamente após as 18h para pegar o fechamento do dia.")
    print(f"Os dados do dia ficam em cache — não gasta requisições extras.{Style.RESET_ALL}\n")
