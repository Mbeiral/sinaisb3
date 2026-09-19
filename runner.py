"""
================================================================
  RUNNER — Execução agendada no Render.com
  Roda o motor de sinais e envia para o Supabase
  Configurado para executar todo dia às 18h (horário Brasília)
================================================================
"""

import os
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("Runner")

def main():
    log.info("=== RUNNER INICIADO ===")
    log.info(f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # Verifica variáveis de ambiente obrigatórias
    av_key       = os.environ.get("AV_API_KEY")
    sb_url       = os.environ.get("SUPABASE_URL")
    sb_key       = os.environ.get("SUPABASE_KEY")

    if not av_key:
        log.error("AV_API_KEY não configurada nas variáveis de ambiente!")
        sys.exit(1)
    if not sb_url or not sb_key:
        log.error("SUPABASE_URL ou SUPABASE_KEY não configuradas!")
        sys.exit(1)

    log.info("Variáveis de ambiente OK")

    # Importa e executa o motor
    try:
        # Injeta as configurações via variáveis de ambiente
        import motor_sinais as motor

        # Sobrescreve as configurações com as variáveis de ambiente
        motor.AV_API_KEY    = av_key
        motor.USAR_CACHE    = False   # No servidor não usa cache local

        # IMPORTANTE: injeta as credenciais do Supabase ANTES de chamar
        # gerar_ranking(), pois o motor agora também LÊ do Supabase durante
        # a geração do ranking (fechamentos anteriores confiáveis), não só
        # no envio final. Se isso rodar depois de gerar_ranking(), a
        # consulta de leitura usa a chave antiga hardcoded no arquivo
        # (não registrada) em vez da chave real vinda do GitHub Secret.
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "supabase"))
        import supabase_client as sb_client
        sb_client.SUPABASE_URL = sb_url
        sb_client.SUPABASE_KEY = sb_key

        log.info("Gerando ranking...")
        ranking = motor.gerar_ranking()

        if ranking.empty:
            log.error("Ranking vazio — verifique a chave do Alpha Vantage")
            sys.exit(1)

        motor.exibir_ranking(ranking)

        # Envia para o Supabase
        log.info("Enviando para o Supabase...")
        from supabase_client import enviar_sinais

        sucesso = enviar_sinais(ranking)
        if sucesso:
            log.info("=== RUNNER CONCLUÍDO COM SUCESSO ===")
        else:
            log.error("Falha ao enviar para o Supabase")
            sys.exit(1)

    except Exception as e:
        log.error(f"Erro durante execução: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
