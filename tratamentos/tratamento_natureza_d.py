import pandas as pd
from tratamentos import utils


def get_duplicate_keys():
    """Define as chaves para verificar duplicatas neste tratamento."""
    return [
        ("protocolo", "protocolo", "num"),
        ("ano", "ano", "num"),
        ("mes", "mes", "num"),
    ]


def process(df, log_message):
    """
    Aplica a lógica de tratamento genérica para 'Natureza_D'.
    """
    log_message("Executando lógica 'Natureza_D'...")

    # Padroniza nomes das colunas em minúsculas
    df.columns = [c.lower() for c in df.columns]

    if 'data_geracao' in df.columns:
        log_message("Encontrada coluna 'data_geracao'. Convertendo para datetime...")

        # Converte a coluna para datetime no formato brasileiro (dia primeiro: DD/MM/YYYY)
        dt_geracao = pd.to_datetime(df['data_geracao'], dayfirst=True, errors='coerce')

        # Extrai os componentes da data (hora, mês, ano) ANTES de alterar para 12:00
        df['hora'] = dt_geracao.dt.hour
        df['mes'] = dt_geracao.dt.month
        df['ano'] = dt_geracao.dt.year

        # Aplica correção de offset AGOL (12:00:00) na coluna 'data_geracao'
        df['data_geracao'] = dt_geracao.dt.normalize() + pd.Timedelta(hours=12)

        log_message("Colunas hora, mes e ano criadas com sucesso (preservando hora real da ocorrência).")
    else:
        log_message("AVISO: Coluna 'data_geracao' não encontrada no Excel. Tratamento 'Natureza_D' não pôde ser aplicado.")

    # Correção automática para todas as outras colunas datetime
    df = utils.fix_date_offset(df, log_message)

    log_message("Tratamento 'Natureza_D' concluído.")
    return df
