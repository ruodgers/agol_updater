from tratamentos import utils


def get_duplicate_keys():
    """Define as chaves para verificar duplicatas neste tratamento."""
    return utils.get_standard_duplicate_keys("CAMPO_REGISTRO_ID", "CAMPO_ANO", "CAMPO_MES")


def process(df, log_message):
    """
    Aplica a lógica de tratamento genérica para 'Natureza_A'.
    """
    log_message("Executando lógica 'Natureza_A'...")

    is_header_check = len(df) < 1

    if not is_header_check:
        # Filtro de natureza genérico
        df = utils.filter_nature(
            df=df,
            column='CAMPO_CLASSIFICACAO',
            include_regex="VALOR_NATUREZA_A|VALOR_NATUREZA_A_PLURAL",
            exclude_regex="VALOR_EXCLUSAO",
            log_message=log_message
        )

        # Filtro geográfico genérico (apenas cidade alvo)
        df = utils.filter_municipality(
            df=df,
            columns=['CAMPO_MUNICIPIO'],
            target_name='CIDADE_SELECIONADA',
            exclude=False,
            log_message=log_message
        )

    # Ordenação padrão de dia, mês, turno e fuso horário
    df = utils.process_standard_indicators(
        df=df,
        log_message=log_message,
        day_col='CAMPO_DIA',
        month_col='CAMPO_MES',
        turn_col='CAMPO_TURNO'
    )
    df = utils.fix_date_offset(df, log_message)

    return df
