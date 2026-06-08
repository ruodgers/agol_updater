import pandas as pd
from tratamentos import utils

# Mapeamentos regionais genéricos de exemplo
SUB_REGIOES_EXEMPLO = {
    'MUNICIPIO_EXEMPLO_A': 1, 'MUNICIPIO_EXEMPLO_B': 1,
    'MUNICIPIO_EXEMPLO_C': 2, 'MUNICIPIO_EXEMPLO_D': 2,
    'OUTRO_MUNICIPIO': -1
}

SUB_REGIOES_CALHA_EXEMPLO = {
    -1: 'N.I',
    1: 'REGIAO_NORTE',
    2: 'REGIAO_SUL'
}


def get_duplicate_keys():
    """Define as chaves para verificar duplicatas neste tratamento."""
    return [
        ("CAMPO_REGISTRO_SINESP", "CAMPO_REGISTRO_ID", "str"),
        ("CAMPO_ANO_INICIO", "CAMPO_ANO", "num"),
        ("CAMPO_MES_INICIO", "CAMPO_MES", "str"),
    ]


def process(df, log_message):
    """
    Aplica a lógica de tratamento genérica para 'Natureza_C'.
    """
    log_message("Executando lógica 'Natureza_C'...")

    is_header_check = len(df) < 1

    # Filtro geográfico genérico: exclui a capital/cidade principal
    if not is_header_check:
        df = utils.filter_municipality(
            df=df,
            columns=['CAMPO_MUNICIPIO'],
            target_name='CIDADE_SELECIONADA',
            exclude=True,
            log_message=log_message
        )

    # Ordenação padrão usando a escala de turnos alternativa (1-4)
    df = utils.process_standard_indicators(
        df=df,
        log_message=log_message,
        turno_dict=utils.TURNO_DICT_ALT,
        day_col='CAMPO_DIA',
        month_col='CAMPO_MES',
        turn_col='CAMPO_TURNO'
    )

    if 'CAMPO_MUNICIPIO' in df.columns:
        df['SUB_REGIAO_ORDEM'] = df['CAMPO_MUNICIPIO'].astype(str).str.upper().str.strip().map(SUB_REGIOES_EXEMPLO)

    if 'CAMPO_HORA' in df.columns:
        hora_numerica = pd.to_numeric(df['CAMPO_HORA'].astype(str).str.replace(':', ''), errors='coerce')
        df['HORA_ORDEM'] = hora_numerica

    if 'SUB_REGIAO_ORDEM' in df.columns:
        df['SUB_REGIAO_CALHAS'] = df['SUB_REGIAO_ORDEM'].map(SUB_REGIOES_CALHA_EXEMPLO)

    # Correção de offset AGOL no final
    df = utils.fix_date_offset(df, log_message)

    return df
