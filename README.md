# AGOL Updater (Atualizador do ArcGIS Online)

Este é um aplicativo de interface gráfica desenvolvido em Python para atualização e tratamento de dados de indicadores operacionais diretamente nas Feature Layers do ArcGIS Online (AGOL). O aplicativo se comunica com a REST API do ArcGIS para buscar registros existentes, identificar novos dados em planilhas Excel, aplicar regras de tratamento específicas por natureza de ocorrência de forma parametrizada e realizar uploads e deleções de registros com segurança.

## Arquitetura e Replicabilidade

O aplicativo foi projetado sob os princípios de modularidade e de-duplicação de código, tratando as regras de tratamento de dados como elementos replicáveis.

### 1. Modulo Utilitário Comum (utils.py)
Toda a lógica compartilhada de limpeza e ordenação foi extraída para o arquivo `tratamentos/utils.py`. Esse arquivo centraliza:
- Correção de fuso horário UTC-4 para publicação no ArcGIS Online.
- Geração automática das colunas de ordenação de dia da semana, mês do fato e turno.
- Lógica parametrizada de filtro de natureza (expressões regulares de inclusão e exclusão).
- Lógica parametrizada de filtro de município (inclusão ou exclusão de cidades geográficas).
- Geração da estrutura de chaves compostas para identificação de registros duplicados.

### 2. Módulos de Tratamento (Templates)
A pasta `tratamentos/` armazena scripts dinâmicos (iniciando com o prefixo `tratamento_`). O aplicativo lê os nomes desses scripts no momento da inicialização e os carrega como opções disponíveis de processamento. 

Para que as referências não fossem expostas publicamente no histórico, o repositório traz quatro scripts de exemplo com nomes genéricos:
- `tratamento_natureza_a.py`
- `tratamento_natureza_b.py`
- `tratamento_natureza_c.py`
- `tratamento_natureza_d.py`

### 3. Como Customizar para Suas Camadas Reais

Para utilizar suas próprias regras locais sem expô-las no Git:
1. Crie ou copie o arquivo de template (ex: `tratamento_natureza_a.py`) dando o nome da sua natureza de interesse (ex: `Tratamento_Roubo.py` ou `Tratamento_Furto.py` - usando a inicial maiúscula para que o `.gitignore` o ignore automaticamente no seu repositório local).
2. Edite os parâmetros de colunas e valores dentro do seu novo arquivo de tratamento de produção.
3. Configure o ID do item da camada correspondente na aba de "Configurações" da interface gráfica do app ou preenchendo o arquivo local `camadas_ids.json`.

---

## Configuração e Execução (Ambiente de Desenvolvimento)

### Pré-requisitos
- Python 3.10 ou superior instalado na máquina.
- Variáveis de ambiente configuradas ou preenchimento de campos diretamente na interface gráfica.

### Instalação

1. Clone o repositório:
```bash
git clone https://github.com/ruodgers/agol_updater.git
cd agol_updater
```

2. Crie e ative um ambiente virtual:
```bash
python -m venv venv
venv\Scripts\activate  # No Windows
```

3. Instale as dependências recomendadas:
```bash
pip install pandas openpyxl arcgis beautifulsoup4 lxml Pillow pyinstaller
```

4. Execute o aplicativo:
```bash
python Agol_Updater.py
```

---

## Funcionamento da Interface Gráfica

O aplicativo possui uma divisão clara de fluxo em duas abas principais:

### Aba 1: Operação
1. **Conexão com o ArcGIS Online**: Insira a URL do Portal, Usuário e Senha. Ao clicar em Conectar, o app estabelece a sessão.
2. **Seleção de Origem e Filtro**: Escolha o arquivo Excel a ser processado, o tipo de tratamento (natureza) e o mês correspondente.
3. **Mapeamento de Campos**: O app analisa o cabeçalho do Excel processado pelo script de tratamento e exibe campos dinâmicos para mapear as colunas do Excel para os campos correspondentes da tabela de destino no ArcGIS Online. O status dos campos muda de cor (verde para mapeado, vermelho para não mapeado).
4. **Execução**: Permite rodar o processamento, verificar duplicatas em tempo de execução e subir os dados em chunks em segundo plano, ou realizar a exclusão de dados do período selecionado de forma limpa.

### Aba 2: Configuração
Permite visualizar, adicionar, editar e remover os Item IDs das Feature Layers do ArcGIS Online. As alterações feitas aqui são salvas no arquivo local `camadas_ids.json` (que é ignorado pelo Git para garantir segurança operacional).

---

## Compilação do Executável (.exe)

O projeto inclui um script chamado `build.bat` que automatiza o empacotamento da aplicação para distribuição (sem necessidade de instalar o Python no computador de destino).

1. Com o ambiente virtual ativo, execute:
```bash
build.bat
```
2. O PyInstaller compilará o código em modo pasta (otimizando a velocidade de abertura do app).
3. O executável estará disponível em `dist/AGOL_Updater/AGOL_Updater.exe`.
4. Para distribuir, copie a pasta `dist/AGOL_Updater/` inteira contendo o executável, os arquivos JSON e a pasta de tratamentos.
