"""
================================================================
  INTEGRAÇÃO SUPABASE — SINAIS B3
  Envia os sinais gerados pelo motor para o banco de dados
================================================================

INSTALAÇÃO (rode uma vez):
  pip install supabase

CONFIGURAÇÃO:
  1. Cole suas credenciais do Supabase abaixo
  2. SUPABASE_URL e SUPABASE_KEY estão em:
     Supabase → seu projeto → Settings → API
================================================================
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Adiciona o diretório pai ao path para importar o motor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from supabase import create_client, Client
except ImportError:
    print("Instale o cliente Supabase: pip install supabase")
    sys.exit(1)


# ================================================================
#  CONFIGURAÇÕES — cole suas credenciais aqui
# ================================================================


SUPABASE_URL = "https://kbtosekiqecbuibwnjbg.supabase.co"
SUPABASE_KEY = "sb_secret_GJ0u7H2pHQY4vjOq3ONdQA_h2VA6dje"   # Use a service_role key (não a anon key)
                                         # Settings → API → service_role


# ================================================================
#  CLIENTE SUPABASE
# ================================================================

def get_client() -> Client:
    if "SEU_PROJETO" in SUPABASE_URL or "SUA_SERVICE" in SUPABASE_KEY:
        print("⚠  Configure SUPABASE_URL e SUPABASE_KEY antes de usar.")
        sys.exit(1)
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ================================================================
#  ENVIAR SINAIS DO DIA
# ================================================================

def enviar_sinais(df: pd.DataFrame) -> bool:
    """
    Envia o ranking do dia para a tabela 'sinais' no Supabase.
    Usa upsert — se o sinal do dia já existe, atualiza. Se não, cria.
    """
    if df.empty:
        print("DataFrame vazio — nada a enviar.")
        return False

    client = get_client()
    hoje   = datetime.now().strftime("%Y-%m-%d")

    # Colunas que existem na tabela sinais
    colunas_tabela = [
        "data", "ticker", "preco", "variacao_dia", "tendencia",
        "rsi", "macd_hist", "bb_posicao", "vol_variacao", "score",
        "opcao_direcao", "opcao_conf", "opcao_codigo",
        "opcao_strike", "opcao_venc", "opcao_premio", "opcao_dias",
    ]

    registros = []
    for _, row in df.iterrows():
        registro = {"data": hoje}
        for col in colunas_tabela[1:]:   # pula "data" que já adicionamos
            val = row.get(col)
            if pd.isna(val) if isinstance(val, float) else val is None:
                registro[col] = None
            elif isinstance(val, float):
                registro[col] = round(val, 4)
            else:
                registro[col] = val
        registros.append(registro)

    try:
        # Upsert — atualiza se já existe (data + ticker), insere se não existe
        result = client.table("sinais").upsert(
            registros,
            on_conflict="data,ticker"
        ).execute()

        print(f"✓ {len(registros)} sinais enviados para o Supabase ({hoje})")
        return True

    except Exception as e:
        print(f"✗ Erro ao enviar sinais: {e}")
        return False


# ================================================================
#  BUSCAR RANKING DO DIA
# ================================================================

def buscar_ranking_hoje() -> list:
    """Busca o ranking de hoje direto do Supabase."""
    client = get_client()
    try:
        result = (
            client.table("sinais")
            .select("*")
            .eq("data", datetime.now().strftime("%Y-%m-%d"))
            .order("score", desc=True)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"Erro ao buscar ranking: {e}")
        return []


# ================================================================
#  BUSCAR HISTÓRICO DE UM TICKER
# ================================================================

def buscar_historico_ticker(ticker: str, dias: int = 30) -> list:
    """Busca o histórico de sinais de um ticker nos últimos N dias."""
    client = get_client()
    try:
        result = (
            client.table("sinais")
            .select("data, score, rsi, opcao_direcao, opcao_conf, preco")
            .eq("ticker", ticker.upper())
            .order("data", desc=True)
            .limit(dias)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return []


# ================================================================
#  VERIFICAR SE USUÁRIO TEM PLANO ATIVO
# ================================================================

def verificar_plano(usuario_id: str) -> str:
    """
    Retorna o plano do usuário: 'free', 'starter' ou 'pro'.
    Usado pelo app para liberar ou bloquear funcionalidades.
    """
    client = get_client()
    try:
        result = (
            client.table("usuarios")
            .select("plano, status")
            .eq("id", usuario_id)
            .single()
            .execute()
        )
        if result.data and result.data["status"] == "ativo":
            return result.data["plano"]
        return "free"
    except Exception:
        return "free"


# ================================================================
#  TESTE DE CONEXÃO
# ================================================================

def testar_conexao():
    """Testa se a conexão com o Supabase está funcionando."""
    print("\n=== TESTE DE CONEXÃO SUPABASE ===\n")
    try:
        client = get_client()
        result = client.table("sinais").select("count", count="exact").execute()
        total  = result.count or 0
        print(f"✓ Conexão OK!")
        print(f"✓ Tabela 'sinais': {total} registros")

        result2 = client.table("usuarios").select("count", count="exact").execute()
        total2  = result2.count or 0
        print(f"✓ Tabela 'usuarios': {total2} registros")
        print(f"\nSupabase configurado e pronto para uso!\n")
        return True
    except Exception as e:
        print(f"✗ Erro de conexão: {e}")
        print("\nVerifique:")
        print("  1. SUPABASE_URL está correto")
        print("  2. SUPABASE_KEY é a service_role key (não a anon key)")
        print("  3. As tabelas foram criadas (rode criar_tabelas.sql)\n")
        return False


# ================================================================
#  EXECUÇÃO DIRETA — testa conexão e envia sinais de exemplo
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Integração Supabase — Sinais B3")
    parser.add_argument("--testar",  action="store_true", help="Testa conexão com Supabase")
    parser.add_argument("--ranking", action="store_true", help="Busca ranking de hoje")
    parser.add_argument("--ticker",  type=str,            help="Busca histórico de um ticker")
    args = parser.parse_args()

    if args.testar:
        testar_conexao()

    elif args.ranking:
        print("\n=== RANKING DE HOJE ===\n")
        ranking = buscar_ranking_hoje()
        if ranking:
            for i, r in enumerate(ranking, 1):
                print(f"  {i}. {r['ticker']:<8} Score: {r['score']:.1f}  "
                      f"RSI: {r['rsi']:.1f}  {r['opcao_direcao']}")
        else:
            print("  Nenhum sinal encontrado para hoje.")

    elif args.ticker:
        print(f"\n=== HISTÓRICO {args.ticker.upper()} ===\n")
        historico = buscar_historico_ticker(args.ticker)
        for r in historico:
            print(f"  {r['data']}  Score: {r['score']:.1f}  "
                  f"RSI: {r['rsi']:.1f}  {r['opcao_direcao']}  "
                  f"Conf: {r['opcao_conf']}%")

    else:
        testar_conexao()
