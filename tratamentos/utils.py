import pandas as pd
import re

# Dicionários padrão para mapeamento
DIA_DICT = {
    'SEGUNDA-FEIRA': 2,
    'TERCA-FEIRA': 3,
    'QUARTA-FEIRA': 4,
    'QUINTA-FEIRA': 5,
    'SEXTA-FEIRA': 6,
    'SABADO': 7,
    'DOMINGO': 1
}

TURNO_DICT_STANDARD = {
    'MANHA': 2,
    'TARDE': 3,
    'NOITE': 4,
    'MADRUGADA': 1
}

# Usado especificamente no tratamento de Interior
TURNO_DICT_ALT = {
    'MANHA': 1,
    'TARDE': 2,
    'NOITE': 3,
    'MADRUGADA': 4
}

MES_DICT = {
    'JANEIRO': 1, 'FEVEREIRO': 2, 'MARCO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
    'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
}


def get_standard_duplicate_keys(bo_col, ano_col, mes_col):
    """Retorna a estrutura padronizada para chaves de duplicidade."""
    return [
        (bo_col, bo_col, "str"),
        (ano_col, ano_col, "num"),
        (mes_col, mes_col, "str"),
    ]


def fix_date_offset(df, log_message):
    """
    Corrige offset de fuso horário para publicação no ArcGIS Online.
    Define todas as colunas datetime para meio-dia (12:00:00) para evitar
    que a conversão UTC-4 (ou fuso local) retroceda a data para o dia anterior.
    """
    date_cols = [
        col for col in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[col])
    ]

    for col in date_cols:
        df[col] = df[col].dt.normalize() + pd.Timedelta(hours=12)
        log_message(
            f"Offset de data corrigido (UTC-4): '{col}' -> hora definida para 12:00:00."
        )

    return df


def process_standard_indicators(df, log_message, turno_dict=None, day_col='DIA_FATO', month_col='MES_FATO', turn_col='TURNO_FATO'):
    """
    Aplica o mapeamento de ordenação para as colunas padronizadas de
    dia da semana, mês do fato e turno.
    """
    if turno_dict is None:
        turno_dict = TURNO_DICT_STANDARD

    log_message("Aplicando ordenação de indicadores (DIA, MES, TURNO)...")

    if day_col in df.columns:
        df['DIA_ORDEM'] = df[day_col].astype(str).str.upper().str.strip().map(DIA_DICT)
    if turn_col in df.columns:
        df['TURNO_ORDEM'] = df[turn_col].astype(str).str.upper().str.strip().map(turno_dict)
    if month_col in df.columns:
        df['MES_ORDEM'] = df[month_col].astype(str).str.upper().str.strip().map(MES_DICT)

    return df


def filter_nature(df, column, include_regex, exclude_regex=None, log_message=None):
    """
    Filtra o DataFrame mantendo apenas registros onde a coluna de classificação
    casa com include_regex e opcionalmente não casa com exclude_regex.
    """
    if column not in df.columns:
        if log_message:
            log_message(f"AVISO: Coluna de natureza '{column}' não encontrada. Filtro de natureza ignorado.")
        return df

    original_count = len(df)
    
    # Inclusão
    include_mask = df[column].astype(str).str.contains(include_regex, case=False, na=False)
    
    # Exclusão
    if exclude_regex:
        exclude_mask = df[column].astype(str).str.contains(exclude_regex, case=False, na=False)
        df = df[include_mask & ~exclude_mask].copy()
    else:
        df = df[include_mask].copy()

    if log_message:
        log_message(
            f"Filtrado por '{include_regex}' em '{column}'"
            + (f" (excluindo '{exclude_regex}')" if exclude_regex else "")
            + f". Registros: {original_count} -> {len(df)}"
        )

    return df


def filter_municipality(df, columns, target_name="MANAUS", exclude=False, log_message=None):
    """
    Filtra o DataFrame para incluir ou excluir determinado município.
    Suporta busca em múltiplas colunas candidatas (ex: ['MUNICIPIO_FATO', 'MUNICIPIO']).
    """
    # Identifica a primeira coluna disponível dentre as opções fornecidas
    mun_col = None
    if isinstance(columns, str):
        columns = [columns]

    for col in columns:
        if col in df.columns:
            mun_col = col
            break

    if not mun_col:
        if log_message:
            log_message(f"AVISO: Nenhuma coluna de município encontrada em {columns}. Filtro geográfico ignorado.")
        return df

    original_count = len(df)
    target_clean = str(target_name).strip().upper()
    
    # Máscara para matching
    mask = df[mun_col].astype(str).str.upper().str.strip() == target_clean
    
    if exclude:
        df = df[~mask].copy()
        msg_action = "!="
    else:
        df = df[mask].copy()
        msg_action = "=="

    if log_message:
        log_message(f"Filtrado por {mun_col} {msg_action} '{target_clean}'. Registros: {original_count} -> {len(df)}")

    return df
