import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, font as tkfont
import pandas as pd
from arcgis.gis import GIS
from arcgis.features import Feature
import threading
import concurrent.futures
import sys
from datetime import datetime, date
import unicodedata
import os
import glob
import json
import importlib.util
import warnings
import urllib3

# silencia aviso SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)

# =====================
# CONFIG — compatível com PyInstaller
# =====================
if getattr(sys, 'frozen', False):
    # Executando como .exe compilado
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    # Executando como script .py
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

IDS_FILE = os.path.join(SCRIPT_DIR, "camadas_ids.json")
TREATMENTS_DIR = os.path.join(SCRIPT_DIR, "tratamentos")
TREATMENT_PREFIX = "tratamento_"
TREATMENT_SUFFIX = ".py"

# =====================
# PALETA DE CORES
# =====================
THEMES = {
    'dark': {
        'bg_primary':    '#0d1117',
        'bg_secondary':  '#161b22',
        'bg_card':       '#1c2333',
        'bg_input':      '#0d1117',
        'bg_hover':      '#21262d',
        'accent':        '#0f969c',
        'accent_hover':  '#05c3de',
        'accent_dim':    '#0a6e73',
        'text':          '#e6edf3',
        'text_dim':      '#8b949e',
        'text_muted':    '#484f58',
        'success':       '#06d6a0',
        'error':         '#ef476f',
        'warning':       '#ffd166',
        'border':        '#30363d',
        'border_accent': '#0f969c',
        'btn_primary':   '#0f969c',
        'btn_hover':     '#05c3de',
        'btn_danger':    '#ef476f',
        'btn_danger_hv': '#ff6b8a',
        'log_bg':        '#010409',
        'log_fg':        '#c9d1d9',
        'tab_active':    '#0f969c',
        'tab_inactive':  '#21262d',
    },
    'light': {
        'bg_primary':    '#f6f8fa',
        'bg_secondary':  '#ffffff',
        'bg_card':       '#ffffff',
        'bg_input':      '#ffffff',
        'bg_hover':      '#f3f4f6',
        'accent':        '#0969da',
        'accent_hover':  '#005cc5',
        'accent_dim':    '#0550ae',
        'text':          '#24292f',
        'text_dim':      '#57606a',
        'text_muted':    '#8c959f',
        'success':       '#2da44e',
        'error':         '#cf222e',
        'warning':       '#bf8700',
        'border':        '#d0d7de',
        'border_accent': '#0969da',
        'btn_primary':   '#0969da',
        'btn_hover':     '#005cc5',
        'btn_danger':    '#cf222e',
        'btn_danger_hv': '#a40e26',
        'log_bg':        '#ffffff',
        'log_fg':        '#24292f',
        'tab_active':    '#0969da',
        'tab_inactive':  '#f3f4f6',
    }
}
COLORS = THEMES['dark']

CURRENT_THEME = 'dark'
APP_VERSION = "4.1.0"

# Meses para o filtro de período
MONTHS_LIST = [
    "Todos",
    "Janeiro", "Fevereiro", "Março", "Abril",
    "Maio", "Junho", "Julho", "Agosto",
    "Setembro", "Outubro", "Novembro", "Dezembro"
]

# Mapa de nomes de mês (PT-BR uppercase) -> número
MONTH_NAME_TO_NUM = {
    'JANEIRO': 1, 'FEVEREIRO': 2, 'MARCO': 3, 'MARÇO': 3, 'ABRIL': 4,
    'MAIO': 5, 'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8,
    'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
}


class ArcGISUpdaterApp:
    def __init__(self, master):
        self.master = master
        master.title(f"AGOL Updater v{APP_VERSION}")
        master.geometry("1050x820")
        master.minsize(900, 700)
        master.configure(bg=COLORS['bg_primary'])

        self.init_ok = False

        # estado dinâmico
        self.item_ids = {}
        self.treatment_functions = {}
        self.treatment_keys = {}
        self.TREATMENT_TYPES = []

        # carrega config e tratamentos
        try:
            self.load_configuration()
        except Exception as e:
            messagebox.showerror(
                "Erro Fatal na Carga",
                (
                    "Não foi possível carregar as configurações.\n"
                    f"Verifique {IDS_FILE} e a pasta {TREATMENTS_DIR}.\n\n"
                    f"Detalhe: {e}"
                )
            )
            master.destroy()
            return

        # dicionário de possíveis sinônimos p/ detecção automática
        self.FIELD_SYNONYMS = {
            'X-Coordinate (Longitude)': ['longitude', 'long', 'x', 'lon'],
            'Y-Coordinate (Latitude)': ['latitude', 'lat', 'y'],
            'NARRATIVA': ['descricao'],
            'DATA_INICIO_FATO': ['datafato'],
            'MES_INICIO_FATO': ['mesfato'],
            'ANO_INICIO_FATO': ['anofato'],
            'DIA_SEMANA_INICIO_FATO': ['diafato'],
            'HORA_INICIO_FATO': ['horafato'],
            'TURNO_INICIO_FATO': ['turnofato'],
            'NOME_DELEGACIA_REGISTRO': ['dipregistro'],
            'NOME_DELEGACIA_AFETO': ['dipfato'],
            'INDICADOR_GEOGRAFICO': ['indicadorgeografico'],
            'BO_SINESP': ['boestadual']
        }

        # estado de UI / dados
        self.excel_columns = ["N/A (Não Mapear)"]
        self.agol_fields = {}
        self.mapping_vars = {}
        self.mapping_optionmenus = {}
        self.gis = None
        self.connected_username = None

        # Filtros de Período (Mês e Ano livre)
        self.selected_months = set()
        self.selected_years = set()
        self.available_years = list(range(2018, 2031))

        # controle de cancelamento upload
        self.cancel_requested = threading.Event()
        self.all_added_objectids = []

        # flag para controle de duplicata (evita acesso direto ao widget de thread)
        self._dup_check_skipped = False

        # =====================
        # APLICAR TEMA
        # =====================
        self._setup_theme()
        self._build_ui()

        # UI começa bloqueada até conectar
        self.toggle_app_sections(False)
        self.init_ok = True

    # =====================
    # TEMA MODERNO
    # =====================
    def _setup_theme(self):
        style = ttk.Style(self.master)
        style.theme_use('clam')

        # Fontes
        self.font_title = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.font_subtitle = tkfont.Font(family="Segoe UI", size=10)
        self.font_section = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.font_body = tkfont.Font(family="Segoe UI", size=9)
        self.font_mono = tkfont.Font(family="Consolas", size=9)
        self.font_small = tkfont.Font(family="Segoe UI", size=8)
        self.font_btn = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        # TFrame
        style.configure("Dark.TFrame", background=COLORS['bg_primary'])
        style.configure("Card.TFrame", background=COLORS['bg_card'])
        style.configure("CardInner.TFrame", background=COLORS['bg_card'])

        # TLabel
        style.configure("Dark.TLabel",
                         background=COLORS['bg_primary'],
                         foreground=COLORS['text'],
                         font=self.font_body)
        style.configure("Card.TLabel",
                         background=COLORS['bg_card'],
                         foreground=COLORS['text'],
                         font=self.font_body)
        style.configure("Dim.TLabel",
                         background=COLORS['bg_card'],
                         foreground=COLORS['text_dim'],
                         font=self.font_small)
        style.configure("Header.TLabel",
                         background=COLORS['bg_primary'],
                         foreground=COLORS['text'],
                         font=self.font_title)
        style.configure("Subtitle.TLabel",
                         background=COLORS['bg_primary'],
                         foreground=COLORS['text_dim'],
                         font=self.font_subtitle)
        style.configure("Section.TLabel",
                         background=COLORS['bg_card'],
                         foreground=COLORS['accent'],
                         font=self.font_section)
        style.configure("StatusOk.TLabel",
                         background=COLORS['bg_primary'],
                         foreground=COLORS['success'],
                         font=self.font_body)
        style.configure("StatusErr.TLabel",
                         background=COLORS['bg_primary'],
                         foreground=COLORS['error'],
                         font=self.font_body)
        style.configure("MapHeader.TLabel",
                         background=COLORS['bg_card'],
                         foreground=COLORS['accent'],
                         font=self.font_btn)

        # TLabelframe
        style.configure("Card.TLabelframe",
                         background=COLORS['bg_card'],
                         foreground=COLORS['accent'],
                         bordercolor=COLORS['border'],
                         relief="flat",
                         borderwidth=1)
        style.configure("Card.TLabelframe.Label",
                         background=COLORS['bg_card'],
                         foreground=COLORS['accent'],
                         font=self.font_section)

        # TButton
        style.configure("Accent.TButton",
                         background=COLORS['btn_primary'],
                         foreground="#ffffff",
                         font=self.font_btn,
                         borderwidth=0,
                         padding=(16, 8))
        style.map("Accent.TButton",
                   background=[('active', COLORS['btn_hover']),
                               ('disabled', COLORS['text_muted'])],
                   foreground=[('disabled', COLORS['border'])])

        style.configure("Secondary.TButton",
                         background=COLORS['bg_hover'],
                         foreground=COLORS['text'],
                         font=self.font_body,
                         borderwidth=1,
                         padding=(12, 6))
        style.map("Secondary.TButton",
                   background=[('active', COLORS['border']),
                               ('disabled', COLORS['text_muted'])],
                   foreground=[('disabled', COLORS['border'])])

        style.configure("Danger.TButton",
                         background=COLORS['btn_danger'],
                         foreground="#ffffff",
                         font=self.font_btn,
                         borderwidth=0,
                         padding=(16, 8))
        style.map("Danger.TButton",
                   background=[('active', COLORS['btn_danger_hv']),
                               ('disabled', COLORS['text_muted'])],
                   foreground=[('disabled', COLORS['border'])])

        style.configure("Small.TButton",
                         background=COLORS['bg_hover'],
                         foreground=COLORS['text_dim'],
                         font=self.font_small,
                         borderwidth=0,
                         padding=(6, 3))
        style.map("Small.TButton",
                   background=[('active', COLORS['border'])])

        style.configure("SmallDanger.TButton",
                         background=COLORS['btn_danger'],
                         foreground="#ffffff",
                         font=self.font_small,
                         borderwidth=0,
                         padding=(6, 3))
        style.map("SmallDanger.TButton",
                   background=[('active', COLORS['btn_danger_hv'])])

        style.configure("Save.TButton",
                         background=COLORS['success'],
                         foreground="#000000",
                         font=self.font_btn,
                         borderwidth=0,
                         padding=(20, 10))
        style.map("Save.TButton",
                   background=[('active', '#04b88a')])

        # TEntry
        style.configure("Dark.TEntry",
                         fieldbackground=COLORS['bg_input'],
                         foreground=COLORS['text'],
                         bordercolor=COLORS['border'],
                         insertcolor=COLORS['text'],
                         font=self.font_body)
        style.map("Dark.TEntry",
                   bordercolor=[('focus', COLORS['accent'])])

        # TCheckbutton
        style.configure("Dark.TCheckbutton",
                         background=COLORS['bg_card'],
                         foreground=COLORS['text'],
                         font=self.font_body)
        style.map("Dark.TCheckbutton",
                   background=[('active', COLORS['bg_card'])])

        # TNotebook (Tabs)
        style.configure("Dark.TNotebook",
                         background=COLORS['bg_primary'],
                         borderwidth=0,
                         tabmargins=[0, 0, 0, 0])
        style.configure("Dark.TNotebook.Tab",
                         background=COLORS['tab_inactive'],
                         foreground=COLORS['text_dim'],
                         font=self.font_btn,
                         padding=(20, 10),
                         borderwidth=0)
        style.map("Dark.TNotebook.Tab",
                   background=[('selected', COLORS['bg_primary']),
                               ('active', COLORS['bg_hover'])],
                   foreground=[('selected', COLORS['accent']),
                               ('active', COLORS['text'])])

        # TScrollbar
        style.configure("Dark.Vertical.TScrollbar",
                         background=COLORS['bg_secondary'],
                         troughcolor=COLORS['bg_primary'],
                         bordercolor=COLORS['bg_primary'],
                         arrowcolor=COLORS['text_dim'])

        # TSeparator
        style.configure("Dark.TSeparator",
                         background=COLORS['border'])

        # Progressbar
        style.configure("Accent.Horizontal.TProgressbar",
                         background=COLORS['accent'],
                         troughcolor=COLORS['bg_secondary'],
                         borderwidth=0)

    def toggle_theme(self):
        global COLORS, CURRENT_THEME
        CURRENT_THEME = 'light' if CURRENT_THEME == 'dark' else 'dark'
        COLORS = THEMES[CURRENT_THEME]
        
        # Update Styles
        self._setup_theme()
        
        # Update Backgrounds
        self.master.configure(bg=COLORS['bg_primary'])
        self.main_sep.configure(bg=COLORS['border'])
        
        if hasattr(self, 'main_canvas'):
            self.main_canvas.configure(bg=COLORS['bg_primary'])
        if hasattr(self, 'settings_canvas'):
            self.settings_canvas.configure(bg=COLORS['bg_primary'])
        if hasattr(self, 'settings_sep1'):
            self.settings_sep1.configure(bg=COLORS['border'])
        if hasattr(self, 'settings_sep2'):
            self.settings_sep2.configure(bg=COLORS['border'])
            
        if hasattr(self, 'log_text'):
            self.log_text.configure(
                bg=COLORS['log_bg'], fg=COLORS['log_fg'],
                insertbackground=COLORS['text'], selectbackground=COLORS['accent']
            )
        
        self._apply_menu_colors()

    def _apply_menu_colors(self):
        menus = [
            getattr(self, 'treatment_menu', None),
            getattr(self, 'sheet_menu', None),
            getattr(self, 'geo_ind_menu', None),
            getattr(self, 'geo_col_menu', None),
            getattr(self, 'month_menu', None),
            getattr(self, 'month_col_menu', None),
            getattr(self, 'year_menu', None),
            getattr(self, 'year_col_menu', None),
        ]
        for om in menus:
            if om:
                try:
                    om['menu'].configure(
                        bg=COLORS['bg_input'], fg=COLORS['text'],
                        activebackground=COLORS['bg_hover'], activeforeground=COLORS['text'],
                        bd=0, relief="flat"
                    )
                except Exception:
                    pass

    def refresh_treatment_menu(self):
        if not hasattr(self, 'treatment_menu'):
            return

        active_types = [t for t in self.TREATMENT_TYPES if self.item_ids.get(t, "").strip() != ""]
        if not active_types:
            active_types = self.TREATMENT_TYPES

        menu = self.treatment_menu['menu']
        menu.delete(0, 'end')

        for t in active_types:
            menu.add_command(label=t, command=lambda v=t: self.treatment_var.set(v))

        current = self.treatment_var.get()
        if current not in active_types:
            self.treatment_var.set(active_types[0] if active_types else "")

        self._apply_menu_colors()

    # =====================
    # BUILD UI
    # =====================
    def _build_ui(self):
        # Header
        header_frame = ttk.Frame(self.master, style="Dark.TFrame")
        header_frame.pack(fill=tk.X, padx=20, pady=(15, 5))

        ttk.Label(header_frame, text="🌐 AGOL Updater", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(header_frame, text=f"v{APP_VERSION} — Append de dados no ArcGIS Online",
                  style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))
                  
        self.theme_btn = ttk.Button(header_frame, text="🌓 Alternar Tema", style="Secondary.TButton", command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, pady=(5, 0))

        # Separator
        self.main_sep = tk.Frame(self.master, height=1, bg=COLORS['border'])
        self.main_sep.pack(fill=tk.X, padx=20, pady=(8, 0))

        # Notebook (Tabs)
        self.notebook = ttk.Notebook(self.master, style="Dark.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(8, 0))

        # Tab 1: Operação
        self.tab_operation = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_operation, text="  Operação  ")

        
        # Tab 2: Configuração
        self.tab_settings = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_settings, text="  Configuração  ")

        self._build_operation_tab()
        self._build_settings_tab()

        # Status bar
        self._build_statusbar()

        self._apply_menu_colors()

    def _make_card(self, parent, title, row=None, col=None, padx=8, pady=5, sticky="nsew"):
        """Cria um card estilizado (LabelFrame com tema escuro)."""
        card = ttk.LabelFrame(parent, text=f"  {title}  ", style="Card.TLabelframe")
        if row is not None:
            card.grid(row=row, column=col or 0, padx=padx, pady=pady, sticky=sticky)
        else:
            card.pack(fill=tk.X, padx=padx, pady=pady)
        return card

    def _make_entry(self, parent, textvariable, width=40, show=None):
        """Cria um Entry com tema escuro."""
        entry = ttk.Entry(parent, textvariable=textvariable, width=width,
                          style="Dark.TEntry", font=self.font_body)
        if show:
            entry.configure(show=show)
        return entry

    # =====================
    # ABA OPERAÇÃO
    # =====================
    def _build_operation_tab(self):
        # Scrollable frame for operation tab
        canvas = tk.Canvas(self.tab_operation, bg=COLORS['bg_primary'],
                           highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(self.tab_operation, orient="vertical",
                                  command=canvas.yview, style="Dark.Vertical.TScrollbar")
        scroll_frame = ttk.Frame(canvas, style="Dark.TFrame")

        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def _on_canvas_configure(event):
            canvas.itemconfig(win_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.main_canvas = canvas

        # Scroll com roda do mouse
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # 1. Conexão
        conn_card = self._make_card(scroll_frame, "1 › Conexão ao ArcGIS Online")

        row = 0
        ttk.Label(conn_card, text="Portal URL:", style="Card.TLabel").grid(
            row=row, column=0, padx=(12, 5), pady=(10, 5), sticky=tk.W)
        self.portal_url_var = tk.StringVar(value="https://www.arcgis.com")
        self.portal_entry = self._make_entry(conn_card, self.portal_url_var, width=45)
        self.portal_entry.grid(row=row, column=1, padx=5, pady=(10, 5), sticky=tk.W)

        row += 1
        ttk.Label(conn_card, text="Usuário:", style="Card.TLabel").grid(
            row=row, column=0, padx=(12, 5), pady=5, sticky=tk.W)
        self.username_var = tk.StringVar()
        self.user_entry = self._make_entry(conn_card, self.username_var, width=45)
        self.user_entry.grid(row=row, column=1, padx=5, pady=5, sticky=tk.W)

        self.connect_button = ttk.Button(conn_card, text="Conectar",
                                          style="Accent.TButton",
                                          command=self.start_connect_thread)
        self.connect_button.grid(row=row, column=2, padx=(10, 12), pady=5)

        row += 1
        ttk.Label(conn_card, text="Senha:", style="Card.TLabel").grid(
            row=row, column=0, padx=(12, 5), pady=(5, 10), sticky=tk.W)
        self.password_var = tk.StringVar()
        self.pass_entry = self._make_entry(conn_card, self.password_var, width=45, show="●")
        self.pass_entry.grid(row=row, column=1, padx=5, pady=(5, 10), sticky=tk.W)
        self.pass_entry.bind("<Return>", lambda evt: self.start_connect_thread())

        self.conn_status_label = ttk.Label(conn_card, text="● Desconectado",
                                            style="Card.TLabel",
                                            foreground=COLORS['error'])
        self.conn_status_label.grid(row=row, column=2, padx=(10, 12), pady=(5, 10), sticky=tk.W)

        # 2. Fonte de Dados
        source_card = self._make_card(scroll_frame, "2 › Fonte de Dados (Excel)")

        ttk.Label(source_card, text="Arquivo:", style="Card.TLabel").grid(
            row=0, column=0, padx=(12, 5), pady=(10, 5), sticky=tk.W)
        self.excel_path_var = tk.StringVar()
        self.excel_entry = self._make_entry(source_card, self.excel_path_var, width=65)
        self.excel_entry.grid(row=0, column=1, padx=5, pady=(10, 5), sticky=tk.W)
        self.browse_button = ttk.Button(source_card, text="Procurar...",
                                         style="Secondary.TButton",
                                         command=self.browse_file)
        self.browse_button.grid(row=0, column=2, padx=(5, 12), pady=(10, 5))

        # Aba da planilha
        ttk.Label(source_card, text="Aba da Planilha:", style="Card.TLabel").grid(
            row=1, column=0, padx=(12, 5), pady=5, sticky=tk.W)
        self.available_sheets = []
        self.sheet_var = tk.StringVar(value="")
        self.sheet_menu = ttk.OptionMenu(
            source_card,
            self.sheet_var,
            "",
            ""
        )
        self.sheet_menu.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        # Tratamento
        ttk.Label(source_card, text="Tratamento:", style="Card.TLabel").grid(
            row=2, column=0, padx=(12, 5), pady=5, sticky=tk.W)

        # Dropdown de tratamento — mostra apenas os que possuem ID configurado
        active_types = [t for t in self.TREATMENT_TYPES if self.item_ids.get(t, "").strip() != ""]
        if not active_types:
            active_types = self.TREATMENT_TYPES

        default_treatment = active_types[0] if active_types else ""
        self.treatment_var = tk.StringVar(value=default_treatment)
        self.treatment_menu = ttk.OptionMenu(
            source_card,
            self.treatment_var,
            default_treatment,
            *active_types,
            command=self.on_treatment_change
        )
        self.treatment_menu.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)

        # Indicador Geográfico (Capital / Interior / Todos)
        ttk.Label(source_card, text="Indicador Geog.:", style="Card.TLabel").grid(
            row=3, column=0, padx=(12, 5), pady=5, sticky=tk.W)
        self.geo_ind_var = tk.StringVar(value="Todos")
        self.geo_ind_menu = ttk.OptionMenu(
            source_card,
            self.geo_ind_var,
            "Todos",
            "Todos",
            "Capital",
            "Interior"
        )
        self.geo_ind_menu.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(source_card, text="Coluna Geog.:", style="Card.TLabel").grid(
            row=3, column=2, padx=(15, 5), pady=5, sticky=tk.W)
        self.geo_col_var = tk.StringVar(value="Detectar Automaticamente")
        self.geo_col_menu = ttk.OptionMenu(
            source_card,
            self.geo_col_var,
            "Detectar Automaticamente",
            "Detectar Automaticamente"
        )
        self.geo_col_menu.grid(row=3, column=3, padx=(0, 12), pady=5, sticky=tk.W)

        # Seletor de mês do fato
        ttk.Label(source_card, text="Mês do Fato:", style="Card.TLabel").grid(
            row=4, column=0, padx=(12, 5), pady=5, sticky=tk.W)

        self.month_var = tk.StringVar(value="Todos")
        self.month_menu = ttk.OptionMenu(
            source_card,
            self.month_var,
            "Todos",
            *MONTHS_LIST
        )
        self.month_menu.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(source_card, text="Coluna do Mês:", style="Card.TLabel").grid(
            row=4, column=2, padx=(15, 5), pady=5, sticky=tk.W)
        self.month_col_var = tk.StringVar(value="Detectar Automaticamente")
        self.month_col_menu = ttk.OptionMenu(
            source_card,
            self.month_col_var,
            "Detectar Automaticamente",
            "Detectar Automaticamente"
        )
        self.month_col_menu.grid(row=4, column=3, padx=(0, 12), pady=5, sticky=tk.W)

        # Seletor de ano do fato
        ttk.Label(source_card, text="Ano do Fato:", style="Card.TLabel").grid(
            row=5, column=0, padx=(12, 5), pady=(5, 10), sticky=tk.W)

        default_years = ["Todos"] + [str(y) for y in sorted(self.available_years, reverse=True)]
        self.year_var = tk.StringVar(value="Todos")
        self.year_menu = ttk.OptionMenu(
            source_card,
            self.year_var,
            "Todos",
            *default_years
        )
        self.year_menu.grid(row=5, column=1, padx=5, pady=(5, 10), sticky=tk.W)

        ttk.Label(source_card, text="Coluna do Ano:", style="Card.TLabel").grid(
            row=5, column=2, padx=(15, 5), pady=(5, 10), sticky=tk.W)
        self.year_col_var = tk.StringVar(value="Detectar Automaticamente")
        self.year_col_menu = ttk.OptionMenu(
            source_card,
            self.year_col_var,
            "Detectar Automaticamente",
            "Detectar Automaticamente"
        )
        self.year_col_menu.grid(row=5, column=3, padx=(0, 12), pady=(5, 10), sticky=tk.W)

        # 3. Camada Destino
        target_card = self._make_card(scroll_frame, "3 › Camada de Destino (AGOL)")

        ttk.Label(target_card, text="Item ID:", style="Card.TLabel").grid(
            row=0, column=0, padx=(12, 5), pady=10, sticky=tk.W)
        self.item_id_var = tk.StringVar()
        self.item_id_entry = self._make_entry(target_card, self.item_id_var, width=50)
        self.item_id_entry.grid(row=0, column=1, padx=5, pady=10, sticky=tk.W)
        self.fetch_button = ttk.Button(target_card, text="Buscar Campos",
                                        style="Accent.TButton",
                                        command=self.start_fetch_fields)
        self.fetch_button.grid(row=0, column=2, padx=(5, 12), pady=10)

        # 4. Mapeamento
        map_card = self._make_card(scroll_frame, "4 › Mapeamento de Campos (Origem → Destino)")

        self.map_canvas = tk.Canvas(map_card, bg=COLORS['bg_card'],
                                     highlightthickness=0, height=200)
        self.map_scrollbar = ttk.Scrollbar(map_card, orient="vertical",
                                            command=self.map_canvas.yview,
                                            style="Dark.Vertical.TScrollbar")
        self.map_inner = ttk.Frame(self.map_canvas, style="CardInner.TFrame")

        self.map_inner.bind(
            "<Configure>",
            lambda e: self.map_canvas.configure(scrollregion=self.map_canvas.bbox("all"))
        )
        self.map_canvas.create_window((0, 0), window=self.map_inner, anchor="nw")
        self.map_canvas.configure(yscrollcommand=self.map_scrollbar.set)
        self.map_canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.map_scrollbar.pack(side="right", fill="y", pady=5)

        ttk.Label(
            self.map_inner,
            text="  Conecte-se e clique em 'Buscar Campos' para popular esta seção.",
            style="Dim.TLabel"
        ).grid(row=0, column=0, padx=10, pady=15, sticky=tk.W)

        # 5. Execução
        run_card = self._make_card(scroll_frame, "5 › Execução")

        btn_frame = ttk.Frame(run_card, style="CardInner.TFrame")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.run_button = ttk.Button(btn_frame, text="▶  Executar Append",
                                      style="Accent.TButton",
                                      command=self.start_run_append)
        self.run_button.pack(side=tk.LEFT, padx=5)

        self.cancel_button = ttk.Button(btn_frame, text="✕  CANCELAR ENVIO",
                                         style="Danger.TButton",
                                         command=self.on_cancel_upload)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
        self.cancel_button.pack_forget()

        self.debug_var = tk.BooleanVar(value=False)
        self.debug_check = ttk.Checkbutton(
            btn_frame, text="Modo Debug",
            variable=self.debug_var,
            style="Dark.TCheckbutton"
        )
        self.debug_check.pack(side=tk.LEFT, padx=15)

        # 6. Log
        log_card = self._make_card(scroll_frame, "Log de Execução")

        self.log_text = scrolledtext.ScrolledText(
            log_card,
            height=10,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=COLORS['log_bg'],
            fg=COLORS['log_fg'],
            insertbackground=COLORS['text'],
            selectbackground=COLORS['accent'],
            selectforeground="#ffffff",
            font=self.font_mono,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(5, 8))

    # =====================
    # ABA CONFIGURAÇÃO
    # =====================
    def _build_settings_tab(self):
        # Header da aba
        header = ttk.Frame(self.tab_settings, style="Dark.TFrame")
        header.pack(fill=tk.X, padx=15, pady=(15, 5))
        ttk.Label(header, text="Configuração de Camadas",
                  style="Header.TLabel",
                  font=tkfont.Font(family="Segoe UI", size=14, weight="bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="Edite os Item IDs das camadas do ArcGIS Online",
                  style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(12, 0), pady=(4, 0))

        self.settings_sep1 = tk.Frame(self.tab_settings, height=1, bg=COLORS['border'])
        self.settings_sep1.pack(fill=tk.X, padx=15, pady=(5, 10))

        # Scroll frame para os IDs
        canvas_frame = ttk.Frame(self.tab_settings, style="Dark.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 5))

        self.settings_canvas = tk.Canvas(canvas_frame, bg=COLORS['bg_primary'],
                                          highlightthickness=0, bd=0)
        settings_scroll = ttk.Scrollbar(canvas_frame, orient="vertical",
                                         command=self.settings_canvas.yview,
                                         style="Dark.Vertical.TScrollbar")
        self.settings_inner = ttk.Frame(self.settings_canvas, style="Dark.TFrame")

        self.settings_inner.bind(
            "<Configure>",
            lambda e: self.settings_canvas.configure(
                scrollregion=self.settings_canvas.bbox("all"))
        )
        win_id2 = self.settings_canvas.create_window((0, 0), window=self.settings_inner, anchor="nw")
        def _on_settings_canvas_configure(event):
            self.settings_canvas.itemconfig(win_id2, width=event.width)
        self.settings_canvas.bind("<Configure>", _on_settings_canvas_configure)
        
        self.settings_canvas.configure(yscrollcommand=settings_scroll.set)

        self.settings_canvas.pack(side="left", fill="both", expand=True)
        settings_scroll.pack(side="right", fill="y")

        # Cabeçalho das colunas
        cols_header = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        cols_header.pack(fill=tk.X, padx=10, pady=(5, 8))

        ttk.Label(cols_header, text="Camada", style="Dark.TLabel",
                  foreground=COLORS['accent'], font=self.font_btn, width=20).pack(side=tk.LEFT, padx=(10, 30))
        ttk.Label(cols_header, text="Item ID (ArcGIS Online)", style="Dark.TLabel",
                  foreground=COLORS['accent'], font=self.font_btn).pack(side=tk.LEFT, padx=(0, 30))

        self.settings_sep2 = tk.Frame(self.settings_inner, height=1, bg=COLORS['border'])
        self.settings_sep2.pack(fill=tk.X, padx=10, pady=(0, 8))

        # Container para rows de IDs
        self.ids_rows_frame = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        self.ids_rows_frame.pack(fill=tk.X, padx=10)

        self.id_entries = {}  # {name: StringVar}
        self.id_row_widgets = {}  # {name: [widgets]}

        # Popular com IDs existentes
        for name, item_id in self.item_ids.items():
            self._add_id_row(name, item_id)

        # Botão Adicionar Camada
        add_layer_frame = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        add_layer_frame.pack(fill=tk.X, padx=10, pady=(10, 15))

        add_btn = ttk.Button(add_layer_frame, text="＋  Adicionar Nova Camada",
                              style="Secondary.TButton",
                              command=self._add_new_layer_dialog)
        add_btn.pack(side=tk.LEFT, padx=5)

        # --- SEÇÃO 2: ANOS PARA FILTRO DE PERÍODO ---
        sep_mid = tk.Frame(self.settings_inner, height=1, bg=COLORS['border'])
        sep_mid.pack(fill=tk.X, padx=10, pady=(10, 15))

        section2_label = ttk.Label(self.settings_inner, text="2 › Anos Disponíveis para Filtro de Período",
                                   style="Header.TLabel",
                                   font=tkfont.Font(family="Segoe UI", size=11, weight="bold"))
        section2_label.pack(anchor=tk.W, padx=10, pady=(0, 5))

        years_desc = ttk.Label(self.settings_inner,
                               text="Defina os anos que ficarão disponíveis para seleção no filtro da Seção 2 da Operação.",
                               style="Dark.TLabel", foreground=COLORS['text_dim'])
        years_desc.pack(anchor=tk.W, padx=10, pady=(0, 8))

        # Container para os Anos
        years_container = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        years_container.pack(fill=tk.X, padx=10, pady=5)

        self.years_chips_frame = ttk.Frame(years_container, style="Dark.TFrame")
        self.years_chips_frame.pack(fill=tk.X, pady=5)

        self._refresh_settings_years_ui()

        # Controles para adicionar novo ano
        add_year_ctrl = ttk.Frame(years_container, style="Dark.TFrame")
        add_year_ctrl.pack(fill=tk.X, pady=(5, 10))

        ttk.Label(add_year_ctrl, text="Novo Ano (4 dígitos):", style="Dark.TLabel").pack(side=tk.LEFT, padx=(5, 5))
        self.new_year_config_var = tk.StringVar()
        new_y_entry = self._make_entry(add_year_ctrl, self.new_year_config_var, width=12)
        new_y_entry.pack(side=tk.LEFT, padx=(0, 8))

        def on_add_config_year():
            val = self.new_year_config_var.get().strip()
            if val.isdigit() and len(val) == 4:
                y_int = int(val)
                if y_int not in self.available_years:
                    self.available_years.append(y_int)
                    self.available_years.sort()
                    self._refresh_settings_years_ui()
                    self.new_year_config_var.set("")
                else:
                    messagebox.showinfo("Aviso", f"O ano {y_int} já está na lista.")
            else:
                messagebox.showerror("Erro", "Digite um ano válido com 4 dígitos (ex: 2017).")

        ttk.Button(add_year_ctrl, text="＋  Adicionar Ano", style="Secondary.TButton",
                   command=on_add_config_year).pack(side=tk.LEFT, padx=5)

        def on_reset_years():
            if messagebox.askyesno("Restaurar Anos Padrão", "Deseja restaurar a lista padrão de anos (2018 a 2030)?"):
                self.available_years = list(range(2018, 2031))
                self._refresh_settings_years_ui()

        ttk.Button(add_year_ctrl, text="🔄 Restaurar Anos Padrão", style="Small.TButton",
                   command=on_reset_years).pack(side=tk.LEFT, padx=(15, 5))

        # --- BARRA DE BOTÃO SALVAR ---
        sep_save = tk.Frame(self.settings_inner, height=1, bg=COLORS['border'])
        sep_save.pack(fill=tk.X, padx=10, pady=(15, 10))

        save_btn_frame = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        save_btn_frame.pack(fill=tk.X, padx=10, pady=(5, 15))

        save_btn = ttk.Button(save_btn_frame, text="💾  Salvar Todas as Configurações",
                               style="Save.TButton",
                               command=self._save_ids)
        save_btn.pack(side=tk.RIGHT, padx=5)

        # Info
        info_frame = ttk.Frame(self.settings_inner, style="Dark.TFrame")
        info_frame.pack(fill=tk.X, padx=15, pady=(5, 15))
        ttk.Label(info_frame,
                  text=f"📁 Arquivo de Configuração: {IDS_FILE}",
                  style="Dark.TLabel",
                  foreground=COLORS['text_muted'],
                  font=self.font_small).pack(anchor=tk.W)

    def _add_id_row(self, name, item_id=""):
        """Adiciona uma row de camada editável na aba de configuração."""
        row_frame = ttk.Frame(self.ids_rows_frame, style="Dark.TFrame")
        row_frame.pack(fill=tk.X, pady=3)

        # Nome da camada
        name_label = ttk.Label(row_frame, text=name, style="Dark.TLabel",
                                width=20, font=self.font_body,
                                foreground=COLORS['text'])
        name_label.pack(side=tk.LEFT, padx=(10, 5))

        # Entry do ID
        id_var = tk.StringVar(value=item_id)
        id_entry = ttk.Entry(row_frame, textvariable=id_var, width=45,
                              style="Dark.TEntry", font=self.font_mono)
        id_entry.pack(side=tk.LEFT, padx=5)

        # Indicador visual de status
        status_dot = ttk.Label(row_frame, text="●", style="Dark.TLabel",
                                foreground=COLORS['success'] if item_id else COLORS['error'])
        status_dot.pack(side=tk.LEFT, padx=(5, 2))

        # Atualizar cor ao digitar
        def on_id_change(*args):
            val = id_var.get().strip()
            status_dot.configure(
                foreground=COLORS['success'] if val and len(val) > 10 else COLORS['error'])
        id_var.trace_add("write", on_id_change)

        # Botão remover
        remove_btn = ttk.Button(
            row_frame, text="✕",
            style="SmallDanger.TButton",
            command=lambda n=name: self._remove_id_row(n)
        )
        remove_btn.pack(side=tk.RIGHT, padx=(5, 10))

        self.id_entries[name] = id_var
        self.id_row_widgets[name] = row_frame

    def _remove_id_row(self, name):
        """Remove uma row de camada."""
        if name in self.id_row_widgets:
            if messagebox.askyesno("Confirmar",
                                    f"Remover camada '{name}'?\n"
                                    "A remoção só será efetivada ao Salvar."):
                self.id_row_widgets[name].destroy()
                del self.id_row_widgets[name]
                del self.id_entries[name]

    def _add_new_layer_dialog(self):
        """Dialog para adicionar nova camada."""
        dialog = tk.Toplevel(self.master)
        dialog.title("Nova Camada")
        dialog.geometry("400x180")
        dialog.configure(bg=COLORS['bg_card'])
        dialog.resizable(False, False)
        dialog.transient(self.master)
        dialog.grab_set()

        ttk.Label(dialog, text="Nome da Camada:", style="Card.TLabel").pack(
            padx=20, pady=(20, 5), anchor=tk.W)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=40,
                                style="Dark.TEntry", font=self.font_body)
        name_entry.pack(padx=20, pady=(0, 10))
        name_entry.focus_set()

        ttk.Label(dialog, text="Item ID:", style="Card.TLabel").pack(
            padx=20, pady=(5, 5), anchor=tk.W)
        id_var = tk.StringVar()
        id_entry = ttk.Entry(dialog, textvariable=id_var, width=40,
                              style="Dark.TEntry", font=self.font_mono)
        id_entry.pack(padx=20, pady=(0, 15))

        def on_add():
            name = name_var.get().strip()
            item_id = id_var.get().strip()
            if not name:
                messagebox.showerror("Erro", "Nome da camada não pode ser vazio.")
                return
            if name in self.id_entries:
                messagebox.showerror("Erro", f"Camada '{name}' já existe.")
                return
            self._add_id_row(name, item_id)
            dialog.destroy()

        ttk.Button(dialog, text="Adicionar", style="Accent.TButton",
                    command=on_add).pack(pady=(0, 10))
        name_entry.bind("<Return>", lambda e: id_entry.focus_set())
        id_entry.bind("<Return>", lambda e: on_add())

    def _refresh_settings_years_ui(self):
        """Atualiza a exibição de anos na aba de configuração."""
        if not hasattr(self, 'years_chips_frame'):
            return

        for w in self.years_chips_frame.winfo_children():
            w.destroy()

        for y in sorted(self.available_years):
            f = ttk.Frame(self.years_chips_frame, style="Card.TFrame")
            f.pack(side=tk.LEFT, padx=4, pady=4)

            ttk.Label(f, text=str(y), style="Card.TLabel", font=self.font_body).pack(side=tk.LEFT, padx=(6, 2), pady=2)

            def make_remove_cmd(year_to_remove):
                def remove_cmd():
                    if len(self.available_years) <= 1:
                        messagebox.showwarning("Aviso", "É necessário manter pelo menos um ano na configuração.")
                        return
                    self.available_years.remove(year_to_remove)
                    self._refresh_settings_years_ui()
                return remove_cmd

            rem_btn = ttk.Button(f, text="✕", style="SmallDanger.TButton", width=2,
                                 command=make_remove_cmd(y))
            rem_btn.pack(side=tk.LEFT, padx=(2, 4), pady=2)

    def _save_ids(self):
        """Salva as configurações de IDs e Anos no JSON."""
        new_config = {}
        for name, var in self.id_entries.items():
            new_config[name] = var.get().strip()

        new_config["_available_years"] = sorted(list(set(self.available_years)))

        try:
            with open(IDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            self.item_ids = {k: v for k, v in new_config.items() if k != "_available_years"}
            self.refresh_treatment_menu()
            messagebox.showinfo("Sucesso",
                                f"Configurações salvas em:\n{IDS_FILE}\n\n"
                                f"{len(self.item_ids)} camada(s) configurada(s).\n"
                                f"Anos configurados: {', '.join(map(str, self.available_years))}")
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar:\n{e}")

    # =====================
    # DIÁLOGOS DE SELEÇÃO DE PERÍODO
    # =====================
    def _scan_available_years_from_df(self, df):
        """Varre o dataframe em busca de anos nas colunas para alimentar available_years."""
        year_cols = ['ANO_INICIO_FATO', 'ANO_FATO', 'CAMPO_ANO', 'CAMPO_ANO_INICIO', 'ano', 'ANO', 'year', 'YEAR']
        found_years = set()
        for col in year_cols:
            if col in df.columns:
                nums = pd.to_numeric(df[col], errors='coerce').dropna().unique()
                for n in nums:
                    if 1900 <= n <= 2100:
                        found_years.add(int(n))

        if not found_years:
            date_cols = ['DT_INICIO_FATO', 'DATA_FATO', 'DATA', 'dt_geracao', 'DATA_OCORRENCIA']
            for col in date_cols:
                if col in df.columns:
                    try:
                        dts = pd.to_datetime(df[col], errors='coerce').dropna()
                        for n in dts.dt.year.unique():
                            if 1900 <= n <= 2100:
                                found_years.add(int(n))
                    except Exception:
                        pass

        if found_years:
            for y in found_years:
                if y not in self.available_years:
                    self.available_years.append(y)
            self.available_years.sort()

    def _update_year_menu(self, years_list):
        """Atualiza o dropdown de seleção do Ano do Fato com 'Todos' + anos detectados."""
        seen = set()
        clean_years = []
        for y in years_list:
            y_str = str(y).strip()
            if y_str and y_str not in seen and y_str != "Todos":
                seen.add(y_str)
                clean_years.append(y_str)

        opts = ["Todos"] + sorted(clean_years, reverse=True)
        curr = self.year_var.get() if hasattr(self, 'year_var') else "Todos"
        if curr not in opts:
            if hasattr(self, 'year_var'):
                self.year_var.set("Todos")

        if hasattr(self, 'year_menu'):
            try:
                m = self.year_menu["menu"]
                m.delete(0, "end")
                for opt in opts:
                    m.add_command(label=opt, command=tk._setit(self.year_var, opt))
                m.configure(
                    bg=COLORS['bg_input'], fg=COLORS['text'],
                    activebackground=COLORS['bg_hover'], activeforeground=COLORS['text'],
                    bd=0, relief="flat"
                )
            except Exception:
                pass

    def _update_period_column_menus(self, col_list):
        """Atualiza os dropdowns de seleção da coluna geográfica, de mês e de ano com as colunas disponíveis."""
        seen = set()
        clean_list = []
        for c in col_list:
            c_str = str(c).strip()
            if c_str and c_str not in seen and c_str != "Detectar Automaticamente":
                seen.add(c_str)
                clean_list.append(c_str)

        options = ["Detectar Automaticamente"] + clean_list

        for menu_widget, var_widget in [
            (getattr(self, 'geo_col_menu', None), getattr(self, 'geo_col_var', None)),
            (getattr(self, 'month_col_menu', None), getattr(self, 'month_col_var', None)),
            (getattr(self, 'year_col_menu', None), getattr(self, 'year_col_var', None))
        ]:
            if not menu_widget or not var_widget:
                continue
            curr = var_widget.get()
            if curr not in options:
                curr = "Detectar Automaticamente"
                var_widget.set("Detectar Automaticamente")

            try:
                m = menu_widget["menu"]
                m.delete(0, "end")
                for opt in options:
                    m.add_command(label=opt, command=tk._setit(var_widget, opt))
                m.configure(
                    bg=COLORS['bg_input'], fg=COLORS['text'],
                    activebackground=COLORS['bg_hover'], activeforeground=COLORS['text'],
                    bd=0, relief="flat"
                )
            except Exception:
                pass
    def _build_statusbar(self):
        statusbar = tk.Frame(self.master, bg=COLORS['bg_secondary'], height=32)
        statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        statusbar.pack_propagate(False)

        self.status_var = tk.StringVar(value="Pronto.")
        self.status_label = tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_dim'],
            font=self.font_small,
            anchor=tk.W,
            padx=15
        )
        self.status_label.pack(fill=tk.BOTH, expand=True)

    # =====================
    # CONFIG / LOAD
    # =====================
    def load_configuration(self):
        # garante pasta tratamentos
        if not os.path.exists(TREATMENTS_DIR):
            os.makedirs(TREATMENTS_DIR)

        # garante JSON de ids existe
        if not os.path.exists(IDS_FILE):
            example_ids = {
                "Natureza_A": "ID_DA_CAMADA_A",
                "Natureza_B": "ID_DA_CAMADA_B",
                "Natureza_C": "ID_DA_CAMADA_C",
                "Natureza_D": "ID_DA_CAMADA_D"
            }
            with open(IDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(example_ids, f, indent=4, ensure_ascii=False)
            raise Exception(
                f"Arquivo {IDS_FILE} não encontrado. Exemplo criado. "
                "Preencha e reinicie."
            )

        with open(IDS_FILE, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)

        if isinstance(raw_config, dict) and "_available_years" in raw_config:
            self.available_years = sorted(list(set(raw_config["_available_years"])))
            self.item_ids = {k: v for k, v in raw_config.items() if k != "_available_years"}
        else:
            self.available_years = list(range(2018, 2031))
            self.item_ids = raw_config if isinstance(raw_config, dict) else {}

        if not self.item_ids:
            raise Exception(
                f"Arquivo {IDS_FILE} está vazio. "
                "Adicione seus nomes e IDs."
            )

        # carrega scripts tratamento_*.py — com glob pattern correto
        search_path = os.path.join(TREATMENTS_DIR, f"{TREATMENT_PREFIX}*{TREATMENT_SUFFIX}")
        treatment_files = glob.glob(search_path)

        if not treatment_files:
            example_script_path = os.path.join(TREATMENTS_DIR, f"{TREATMENT_PREFIX}exemplo.py")
            with open(example_script_path, 'w', encoding='utf-8') as f:
                f.write(
                    "import pandas as pd\n\n"
                    "# Função obrigatória: process(df, log_message)\n"
                    "def process(df, log_message):\n"
                    "    log_message('Executando tratamento Exemplo...')\n"
                    "    return df\n\n"
                    "# Função obrigatória: get_duplicate_keys()\n"
                    "def get_duplicate_keys():\n"
                    "    # Retorna lista vazia se não houver verificação\n"
                    "    return []\n"
                )
            raise Exception(
                "Nenhum script de tratamento encontrado em 'tratamentos'. "
                "Criei 'tratamento_exemplo.py'."
            )

        self.treatment_functions = {}
        self.treatment_keys = {}
        self.TREATMENT_TYPES = []  # Sem string vazia — Fix #6

        for f_path in treatment_files:
            file_name = os.path.basename(f_path)

            lower_name = file_name.lower()
            prefix_lower = TREATMENT_PREFIX.lower()
            suffix_lower = TREATMENT_SUFFIX.lower()

            if lower_name.startswith(prefix_lower) and lower_name.endswith(suffix_lower):
                start = len(prefix_lower)
                end = len(file_name) - len(TREATMENT_SUFFIX)
                raw_treatment_name = file_name[start:end].strip()
            else:
                raw_treatment_name = None

            if not raw_treatment_name:
                print(
                    f"AVISO: '{file_name}' ignorado. "
                    f"Não segue padrão '{TREATMENT_PREFIX}*.py'."
                )
                continue

            try:
                spec = importlib.util.spec_from_file_location(raw_treatment_name, f_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, 'process') and hasattr(module, 'get_duplicate_keys'):
                    treatment_name = raw_treatment_name
                    self.treatment_functions[treatment_name] = module.process
                    self.treatment_keys[treatment_name] = module.get_duplicate_keys
                    self.TREATMENT_TYPES.append(treatment_name)
                else:
                    print(
                        f"AVISO: '{file_name}' ignorado. "
                        "Sem função 'process' e/ou 'get_duplicate_keys'."
                    )
            except Exception as e:
                print(f"ERRO ao carregar o módulo '{file_name}': {e}")

        if not self.treatment_functions:
            raise Exception(
                "Nenhum script de tratamento válido carregado."
            )

        # se faltar algum ID no dicionário, apenas adiciona com valor vazio
        # para que o app inicie normalmente e o usuário possa configurar na aba de Configuração
        should_save = False
        lower_ids_map = {k.lower(): k for k in self.item_ids.keys()}

        for t_name in self.treatment_functions.keys():
            t_name_lower = t_name.lower()
            if t_name_lower not in lower_ids_map:
                self.item_ids[t_name] = ""
                should_save = True

        if should_save:
            try:
                with open(IDS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.item_ids, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Aviso ao salvar auto-ids: {e}")

    # =====================
    # HELPERS UI
    # =====================
    def log_message(self, message):
        def append_log():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.master.after(0, append_log)

    def gui_messagebox_error(self, title, text):
        self.master.after(0, lambda: messagebox.showerror(title, text))

    def gui_messagebox_info(self, title, text):
        self.master.after(0, lambda: messagebox.showinfo(title, text))

    def set_status(self, message):
        self.master.after(0, lambda: self.status_var.set(message))

    def set_processing_state(self, is_processing, upload_in_progress=False):
        """Liga/desliga botões / campos."""
        connect_state = tk.DISABLED if is_processing else tk.NORMAL
        app_state = tk.DISABLED if is_processing or not self.gis else tk.NORMAL

        def apply_states():
            self.connect_button.config(state=connect_state)
            self.portal_entry.config(state=connect_state)
            self.user_entry.config(state=connect_state)
            self.pass_entry.config(state=connect_state)

            self.browse_button.config(state=app_state)
            if hasattr(self, 'sheet_menu'): self.sheet_menu.config(state=app_state)
            self.treatment_menu.config(state=app_state)
            if hasattr(self, 'geo_ind_menu'): self.geo_ind_menu.config(state=app_state)
            if hasattr(self, 'geo_col_menu'): self.geo_col_menu.config(state=app_state)
            if hasattr(self, 'month_menu'): self.month_menu.config(state=app_state)
            if hasattr(self, 'month_col_menu'): self.month_col_menu.config(state=app_state)
            if hasattr(self, 'year_menu'): self.year_menu.config(state=app_state)
            if hasattr(self, 'year_col_menu'): self.year_col_menu.config(state=app_state)
            self.item_id_entry.config(state=app_state)
            self.fetch_button.config(state=app_state)
            self.debug_check.config(state=app_state)

            if upload_in_progress:
                self.run_button.pack_forget()
                self.cancel_button.pack(side=tk.LEFT, padx=5)
                self.cancel_button.config(state=tk.NORMAL)
            else:
                self.cancel_button.pack_forget()
                self.run_button.pack(side=tk.LEFT, padx=5)
                self.run_button.config(state=app_state)

        self.master.after(0, apply_states)

    def toggle_app_sections(self, enabled):
        """Habilita/desabilita seções 2-5 após login."""
        state = tk.NORMAL if enabled else tk.DISABLED
        widgets_to_toggle = [
            self.excel_entry,
            self.browse_button,
            getattr(self, 'sheet_menu', None),
            self.treatment_menu,
            getattr(self, 'geo_ind_menu', None),
            getattr(self, 'geo_col_menu', None),
            getattr(self, 'month_menu', None),
            getattr(self, 'month_col_menu', None),
            getattr(self, 'year_menu', None),
            getattr(self, 'year_col_menu', None),
            self.item_id_entry,
            self.fetch_button,
            self.run_button,
            self.debug_check,
            self.log_text
        ]
        widgets_to_toggle = [w for w in widgets_to_toggle if w is not None]

        for w in widgets_to_toggle:
            try:
                w.config(state=state)
            except tk.TclError:
                pass

        for child in self.map_inner.winfo_children():
            try:
                child.config(state=state)
            except tk.TclError:
                pass

        connect_state = tk.DISABLED if enabled else tk.NORMAL
        self.portal_entry.config(state=connect_state)
        self.user_entry.config(state=connect_state)
        self.pass_entry.config(state=connect_state)
        self.connect_button.config(state=connect_state)

        self.cancel_button.pack_forget()

    # =====================
    # CONEXÃO
    # =====================
    def start_connect_thread(self):
        portal_url = self.portal_url_var.get()
        username = self.username_var.get()
        password = self.password_var.get()

        if not all([portal_url, username, password]):
            messagebox.showerror("Erro", "Por favor, preencha URL, Usuário e Senha.")
            return

        self.set_processing_state(True)
        self.set_status("Conectando...")
        self.log_message(f"Conectando ao {portal_url} como {username}...")

        thread = threading.Thread(
            target=self.connect_thread,
            args=(portal_url, username, password),
            daemon=True
        )
        thread.start()

    def connect_thread(self, portal_url, username, password):
        try:
            self.gis = GIS(portal_url, username, password, verify_cert=False)
            if self.gis.users.me is None:
                self.gis = None
                self.connected_username = None
                raise Exception("Falha na autenticação. Verifique usuário e senha.")

            self.connected_username = self.gis.users.me.username
            self.log_message(f"Conexão como '{self.connected_username}' bem-sucedida.")
            self.set_status(f"Conectado como: {self.connected_username}")

            def on_success():
                self.conn_status_label.config(
                    text=f"● {self.connected_username}",
                    foreground=COLORS['success']
                )
                self.toggle_app_sections(True)
                try:
                    self.on_treatment_change()
                except Exception:
                    pass

            self.master.after(0, on_success)

        except Exception as e:
            self.log_message(f"ERRO de Conexão: {e}")
            self.set_status("Falha na conexão.")
            self.gis = None
            self.connected_username = None

            self.gui_messagebox_error(
                "Erro na Conexão",
                f"Não foi possível conectar.\n\nDetalhe: {e}"
            )

            def fail_ui():
                self.conn_status_label.config(
                    text="● Desconectado",
                    foreground=COLORS['error']
                )
            self.master.after(0, fail_ui)

        finally:
            if not self.gis:
                self.set_processing_state(False)
                self.master.after(0, lambda: self.toggle_app_sections(False))

    # =====================
    # CARREGAR CAMPOS E ESTRUTURA DO EXCEL
    # =====================
    def on_treatment_change(self, *args):
        """Atualiza o Item ID ao trocar o tipo de tratamento e reavalia colunas."""
        selected_raw = self.treatment_var.get().strip()

        item_id = self.item_ids.get(selected_raw)
        if item_id is None:
            lower_lookup = selected_raw.lower()
            for k, v in self.item_ids.items():
                if k.lower() == lower_lookup:
                    item_id = v
                    break
        if item_id is None:
            item_id = ""

        self.item_id_var.set(item_id)

        # Sugestão inteligente de indicador geográfico padrão
        treatment_lower = selected_raw.lower()
        if hasattr(self, 'geo_ind_var'):
            if "furto" in treatment_lower or "roubo" in treatment_lower:
                self.geo_ind_var.set("Capital")
            elif "interior" in treatment_lower:
                self.geo_ind_var.set("Interior")

        filepath = self.excel_path_var.get().strip() if hasattr(self, 'excel_path_var') else ""
        if filepath and os.path.exists(filepath):
            current_sheet = self.sheet_var.get().strip() if hasattr(self, 'sheet_var') else None
            threading.Thread(
                target=self._async_load_sheets_and_columns,
                args=(filepath, current_sheet),
                daemon=True
            ).start()

    def browse_file(self):
        filepath = filedialog.askopenfilename(
            title="Selecione o arquivo Excel",
            filetypes=(("Arquivos Excel", "*.xlsx *.xls *.xlsm *.xlsb"), ("Todos os arquivos", "*.*"))
        )
        if filepath:
            self.excel_path_var.set(filepath)
            self.set_status(f"Lendo estrutura do arquivo: {os.path.basename(filepath)}...")
            self.log_message(f"Arquivo selecionado: {filepath}. Lendo abas e colunas em segundo plano...")
            threading.Thread(
                target=self._async_load_sheets_and_columns,
                args=(filepath, None),
                daemon=True
            ).start()

    def on_sheet_selected(self, sheet_name):
        """Ao escolher uma aba no dropdown, atualiza as colunas e anos daquela aba."""
        self.sheet_var.set(sheet_name)
        filepath = self.excel_path_var.get().strip() if hasattr(self, 'excel_path_var') else ""
        if filepath and os.path.exists(filepath):
            self.set_status(f"Lendo colunas da aba '{sheet_name}'...")
            self.log_message(f"Aba alterada para '{sheet_name}'. Recarregando colunas...")
            threading.Thread(
                target=self._async_load_sheets_and_columns,
                args=(filepath, sheet_name),
                daemon=True
            ).start()

    def _async_load_sheets_and_columns(self, filepath, target_sheet=None):
        """Lê as abas, as colunas e os anos presentes na planilha em segundo plano sem travar a interface."""
        try:
            if not filepath or not os.path.exists(filepath):
                return

            sheets = []
            # 1. Leitura rápida das abas
            ext = os.path.splitext(filepath)[1].lower()
            if ext in ['.xlsx', '.xlsm']:
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(filepath, read_only=True, keep_links=False, data_only=True)
                    sheets = list(wb.sheetnames)
                    wb.close()
                except Exception:
                    pass

            if not sheets:
                try:
                    xl = pd.ExcelFile(filepath)
                    sheets = list(xl.sheet_names)
                except Exception:
                    pass

            if not sheets:
                sheets = ["Plan1"]

            # 2. Determinar aba selecionada
            if target_sheet and target_sheet in sheets:
                chosen_sheet = target_sheet
            else:
                curr = self.sheet_var.get().strip() if hasattr(self, 'sheet_var') else ""
                if curr and curr in sheets:
                    chosen_sheet = curr
                else:
                    preferred = None
                    for cand in ['INDICADORES', 'Indicadores', 'Base', 'BASE', 'Dados', 'Plan1', 'Planilha1']:
                        if cand in sheets:
                            preferred = cand
                            break
                    chosen_sheet = preferred if preferred else sheets[0]

            # 3. Ler amostra da aba (1000 linhas) para extrair colunas e anos reais
            clean_cols = []
            detected_years = set()
            try:
                df_sample = pd.read_excel(filepath, sheet_name=chosen_sheet, nrows=1000)
                raw_cols = [str(c).strip() for c in df_sample.columns]
                clean_cols = [c for c in raw_cols if c and not c.startswith('Unnamed:')]
                if not clean_cols:
                    clean_cols = raw_cols

                # Detectar anos na amostra
                for col in df_sample.columns:
                    col_u = str(col).upper()
                    if any(k in col_u for k in ['ANO', 'YEAR', 'DATA', 'DATE', 'GERACAO', 'FATO']):
                        series = df_sample[col].dropna()
                        num_vals = pd.to_numeric(series, errors='coerce').dropna()
                        for v in num_vals:
                            if 2000 <= v <= 2050:
                                detected_years.add(int(v))
                        if not detected_years or len(detected_years) < 2:
                            dt_vals = pd.to_datetime(series, dayfirst=True, errors='coerce').dropna()
                            for d in dt_vals:
                                if 2000 <= d.year <= 2050:
                                    detected_years.add(int(d.year))
            except Exception as e:
                self.log_message(f"Aviso ao analisar aba '{chosen_sheet}': {e}")
                try:
                    df_h = pd.read_excel(filepath, sheet_name=chosen_sheet, nrows=0)
                    clean_cols = [str(c).strip() for c in df_h.columns if str(c).strip() and not str(c).startswith('Unnamed:')]
                except Exception:
                    clean_cols = []

            # Anos padrão recentes se nada detectado
            if not detected_years:
                current_year = datetime.now().year
                detected_years = {current_year - 2, current_year - 1, current_year, current_year + 1}

            sorted_years = sorted(list(detected_years), reverse=True)

            # 4. Simular colunas geradas pelo tratamento
            treatment_type = self.treatment_var.get().strip() if hasattr(self, 'treatment_var') else ""
            all_cols = list(clean_cols)
            if treatment_type:
                process_func = self.treatment_functions.get(treatment_type)
                if process_func and clean_cols:
                    try:
                        dummy_df = pd.DataFrame(columns=clean_cols)
                        p_df = process_func(dummy_df, lambda m: None)
                        for c in p_df.columns:
                            c_str = str(c).strip()
                            if c_str and c_str not in all_cols:
                                all_cols.append(c_str)
                    except Exception:
                        pass

            # 5. Despachar para a UI na thread principal
            def apply_loaded_info(s_list, sel_sheet, cols, years_list):
                self.available_sheets = s_list
                if hasattr(self, 'sheet_var'):
                    self.sheet_var.set(sel_sheet)
                if hasattr(self, 'sheet_menu'):
                    try:
                        m = self.sheet_menu["menu"]
                        m.delete(0, "end")
                        for s in s_list:
                            m.add_command(label=s, command=lambda val=s: self.on_sheet_selected(val))
                    except Exception:
                        pass

                self._update_period_column_menus(cols)
                self._update_year_menu(years_list)
                self._apply_menu_colors()

                years_str = ", ".join(map(str, years_list))
                self.log_message(
                    f"Planilha pronta: {len(s_list)} aba(s) detectada(s). Aba ativa: '{sel_sheet}'. "
                    f"{len(cols)} colunas disponíveis. Anos identificados: [{years_str}]."
                )
                self.set_status("Pronto.")

            self.master.after(0, lambda: apply_loaded_info(sheets, chosen_sheet, all_cols, sorted_years))

        except Exception as err:
            self.log_message(f"Erro ao carregar estrutura do Excel: {err}")
            self.set_status("Erro ao ler Excel.")

    def start_fetch_fields(self):
        excel_path = self.excel_path_var.get()
        item_id = self.item_id_var.get()
        treatment_type = self.treatment_var.get().strip()

        if not treatment_type:
            messagebox.showerror("Erro", "Selecione um 'Tipo de Tratamento' primeiro.")
            return

        if not all([excel_path, item_id]):
            messagebox.showerror(
                "Erro",
                "Por favor, selecione um Arquivo Excel e verifique o Item ID."
            )
            return

        if not self.gis:
            messagebox.showerror(
                "Erro",
                "Você não está conectado. Conecte-se na Seção 1 primeiro."
            )
            return

        self.set_processing_state(True)
        self.log_message("Iniciando busca de campos...")

        thread = threading.Thread(
            target=self.fetch_fields_thread,
            args=(excel_path, item_id, treatment_type),
            daemon=True
        )
        thread.start()

    def _normalize_string(self, text):
        """Coloca minúsculas, remove acentos, tira espaços e underscores."""
        if not isinstance(text, str):
            return ""
        try:
            nfkd_form = unicodedata.normalize('NFD', text)
            text = "".join(c for c in nfkd_form if not unicodedata.combining(c))
        except Exception:
            pass
        try:
            text = (
                text.lower()
                .strip()
                .replace(" ", "")
                .replace("_", "")
            )
        except Exception:
            return ""
        return text

    def _translate_esri_type(self, esri_type):
        """Torna o tipo da Esri amigável."""
        type_map = {
            "esriFieldTypeString": "Texto",
            "esriFieldTypeInteger": "Inteiro",
            "esriFieldTypeSmallInteger": "Inteiro (Pequeno)",
            "esriFieldTypeDouble": "Decimal (Double)",
            "esriFieldTypeSingle": "Decimal (Single)",
            "esriFieldTypeDate": "Data",
            "esriFieldTypeGUID": "GUID",
        }
        return type_map.get(esri_type, esri_type)

    def fetch_fields_thread(self, excel_path, item_id, treatment_type):
        try:
            selected_sheet = self.sheet_var.get().strip() if hasattr(self, 'sheet_var') else ""
            sheet_arg = selected_sheet if selected_sheet else 0
            self.log_message(f"Lendo cabeçalho do arquivo Excel (Aba: '{selected_sheet or 'Padrão'}'): {excel_path}")
            df_header = pd.read_excel(excel_path, sheet_name=sheet_arg, nrows=0)
            df_header.columns = [str(col).strip() for col in df_header.columns]
            original_cols = list(df_header.columns)
            self.log_message(
                "Colunas originais do Excel (limpas): " + ", ".join(original_cols)
            )

            dummy_df = pd.DataFrame(columns=original_cols)
            self.log_message(
                f"Aplicando tratamento '{treatment_type}' (simulado) para descobrir novas colunas..."
            )

            process_func = self.treatment_functions.get(treatment_type)
            if not process_func:
                raise Exception(
                    f"Função de tratamento para '{treatment_type}' não encontrada/carregada."
                )

            processed_df = process_func(dummy_df, self.log_message)

            new_cols = list(processed_df.columns)
            self.excel_columns = ["N/A (Não Mapear)"] + new_cols
            self.log_message("Colunas pós-tratamento: " + ", ".join(new_cols))
            self.master.after(0, lambda cols=new_cols: self._update_period_column_menus(cols))

            self.log_message(f"Buscando Item ID: {item_id}")
            item = self.gis.content.get(item_id)
            if not item:
                raise Exception(
                    f"Item ID {item_id} não encontrado. Verifique ID/permissões."
                )

            if not hasattr(item, "layers") or not item.layers:
                raise Exception(
                    f"Item {item_id} não parece ser uma camada de feição (sem layers)."
                )

            layer = item.layers[0]
            self.log_message(f"Camada encontrada: {layer.properties.name}")

            self.agol_fields = {}
            self.log_message("Campos da camada de destino (AGOL):")
            for f in layer.properties.fields:
                if f.name.lower() in (
                    'objectid', 'shape', 'shape_length', 'shape_area',
                    'globalid', 'created_date', 'created_user',
                    'edited_date', 'edited_user'
                ):
                    continue
                field_type = self._translate_esri_type(f.type)
                self.agol_fields[f.name] = field_type
                self.log_message(f"  - {f.name} ({field_type})")

            self.master.after(0, self.populate_field_mapping)
            self.set_status("Pronto para mapeamento. Verifique a Seção 4.")

        except Exception as e:
            self.log_message(f"ERRO ao buscar campos: {e}")
            self.set_status(f"Erro: {e}")
            self.gui_messagebox_error(
                "Erro ao Buscar Campos",
                (
                    "Não foi possível buscar os campos.\n"
                    "Verifique o Item ID e o arquivo Excel.\n\n"
                    f"Detalhe: {e}"
                )
            )
        finally:
            self.set_processing_state(False)

    # =====================
    # UI MAPEAMENTO
    # =====================
    def _on_mapping_changed(self, *args):
        """
        Quando um dropdown muda:
        - Atualiza as opções dos menus dropdown para exibir apenas colunas não mapeadas (ou a coluna atual)
        - Pinta fonte verde se != N/A, vermelha se N/A
        """
        if getattr(self, '_updating_mapping_ui', False):
            return

        self._updating_mapping_ui = True
        try:
            used_attr_cols = set()
            for agol_field, var in self.mapping_vars.items():
                if agol_field in ['X-Coordinate (Longitude)', 'Y-Coordinate (Latitude)']:
                    continue
                col = var.get()
                if col and col != "N/A (Não Mapear)":
                    used_attr_cols.add(col)

            for agol_field, var in self.mapping_vars.items():
                om_widget = self.mapping_optionmenus.get(agol_field)
                if not om_widget:
                    continue

                current_val = var.get()

                try:
                    if current_val == "N/A (Não Mapear)":
                        om_widget.config(fg=COLORS['error'], font=self.font_body)
                    else:
                        om_widget.config(fg=COLORS['success'], font=self.font_body)
                except tk.TclError:
                    pass

                # Atualiza opções permitidas no dropdown
                is_geom = agol_field in ['X-Coordinate (Longitude)', 'Y-Coordinate (Latitude)']
                allowed_vals = ["N/A (Não Mapear)"]
                for c in self.excel_columns:
                    if c == "N/A (Não Mapear)":
                        continue
                    if is_geom or c not in used_attr_cols or c == current_val:
                        allowed_vals.append(c)

                try:
                    menu = om_widget["menu"]
                    menu.delete(0, "end")
                    for val in allowed_vals:
                        menu.add_command(
                            label=val,
                            command=tk._setit(var, val)
                        )
                except tk.TclError:
                    pass
        finally:
            self._updating_mapping_ui = False

    def _add_mapping_row(self, parent_row, base_col, agol_field_name, agol_field_type):
        """Cria uma linha de mapeamento."""
        var = tk.StringVar(value="N/A (Não Mapear)")
        var.trace("w", self._on_mapping_changed)
        self.mapping_vars[agol_field_name] = var

        # auto match
        norm_agol = self._normalize_string(agol_field_name)
        search_keys = self.FIELD_SYNONYMS.get(agol_field_name, []) + [norm_agol]

        if self.debug_var.get():
            self.log_message(f"[Debug] Procurando por {agol_field_name} (chaves: {search_keys})")

        used_so_far = {
            v.get() for k, v in self.mapping_vars.items()
            if k not in ['X-Coordinate (Longitude)', 'Y-Coordinate (Latitude)']
            and v.get() != "N/A (Não Mapear)"
        }

        found_match = False
        for excel_col in self.excel_columns:
            if excel_col == "N/A (Não Mapear)":
                continue
            if agol_field_name not in ['X-Coordinate (Longitude)', 'Y-Coordinate (Latitude)'] and excel_col in used_so_far:
                continue

            norm_excel = self._normalize_string(excel_col)
            if self.debug_var.get():
                self.log_message(f"  > Comparando com '{excel_col}' (normalizado: '{norm_excel}')")

            if norm_excel in search_keys:
                var.set(excel_col)
                found_match = True
                if self.debug_var.get():
                    self.log_message(f"    -> SUCESSO! Mapeado '{agol_field_name}' -> '{excel_col}'")
                break

        if not found_match and self.debug_var.get():
            self.log_message(f"  -> FALHA. Nenhuma correspondência para {agol_field_name}.")

        om = tk.OptionMenu(self.map_inner, var, *self.excel_columns)
        om.config(
            bg=COLORS['bg_input'],
            fg=COLORS['text'],
            activebackground=COLORS['bg_hover'],
            activeforeground=COLORS['text'],
            highlightthickness=0,
            relief="flat",
            font=self.font_body
        )
        om["menu"].config(
            bg=COLORS['bg_secondary'],
            fg=COLORS['text'],
            activebackground=COLORS['accent'],
            activeforeground="#ffffff",
            font=self.font_body
        )
        om.grid(row=parent_row, column=base_col + 0, padx=10, pady=3, sticky=tk.W + tk.E)
        self.mapping_optionmenus[agol_field_name] = om

        lbl_txt = f"{agol_field_name} ({agol_field_type})"
        ttk.Label(self.map_inner, text=lbl_txt, style="Card.TLabel").grid(
            row=parent_row, column=base_col + 1, padx=10, pady=3, sticky=tk.W
        )

    def populate_field_mapping(self):
        """Layout de mapeamento."""
        for w in self.map_inner.winfo_children():
            w.destroy()

        self.mapping_vars = {}
        self.mapping_optionmenus = {}

        # GEOMETRIA HEADER
        ttk.Label(self.map_inner, text="― GEOMETRIA ―",
                  style="MapHeader.TLabel").grid(row=0, column=0, padx=10, pady=(5, 5), sticky=tk.W)

        ttk.Label(self.map_inner, text="Coluna Excel (Origem)",
                  style="MapHeader.TLabel").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Label(self.map_inner, text="Campo AGOL (Destino)",
                  style="MapHeader.TLabel").grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)

        row_idx = 2
        self._add_mapping_row(row_idx, 0, 'X-Coordinate (Longitude)', 'Decimal (Double)')
        row_idx += 1
        self._add_mapping_row(row_idx, 0, 'Y-Coordinate (Latitude)', 'Decimal (Double)')
        row_idx += 1

        # separador ATRIBUTOS
        row_idx += 1
        ttk.Label(self.map_inner, text="― ATRIBUTOS ―",
                  style="MapHeader.TLabel").grid(row=row_idx, column=0, padx=10, pady=(10, 5), sticky=tk.W)
        row_idx += 1

        # cabeçalhos pares
        ttk.Label(self.map_inner, text="Coluna Excel (Origem)",
                  style="MapHeader.TLabel").grid(row=row_idx, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Label(self.map_inner, text="Campo AGOL (Destino)",
                  style="MapHeader.TLabel").grid(row=row_idx, column=1, padx=10, pady=5, sticky=tk.W)

        ttk.Label(self.map_inner, text="", style="Card.TLabel").grid(
            row=row_idx, column=2, padx=40, pady=5)

        ttk.Label(self.map_inner, text="Coluna Excel (Origem)",
                  style="MapHeader.TLabel").grid(row=row_idx, column=3, padx=10, pady=5, sticky=tk.W)
        ttk.Label(self.map_inner, text="Campo AGOL (Destino)",
                  style="MapHeader.TLabel").grid(row=row_idx, column=4, padx=10, pady=5, sticky=tk.W)

        row_idx += 1

        agol_field_list = list(self.agol_fields.items())

        total = len(agol_field_list)
        half = (total + 1) // 2
        left_fields = agol_field_list[:half]
        right_fields = agol_field_list[half:]

        max_rows = max(len(left_fields), len(right_fields))

        for i in range(max_rows):
            if i < len(left_fields):
                name_l, type_l = left_fields[i]
                self._add_mapping_row(row_idx, 0, name_l, type_l)

            if i < len(right_fields):
                name_r, type_r = right_fields[i]
                self._add_mapping_row(row_idx, 3, name_r, type_r)

            row_idx += 1

        self._on_mapping_changed()

    # =====================
    # EXECUTAR APPEND
    # =====================
    def on_cancel_upload(self):
        self.log_message(
            "CANCELAMENTO SOLICITADO... O processo será interrompido e revertido após o lote atual."
        )
        self.set_status("Cancelando...")
        self.cancel_requested.set()
        self.cancel_button.config(state=tk.DISABLED)

    def start_run_append(self):
        if not self.gis:
            messagebox.showerror("Erro", "Você não está conectado. Conecte-se na Seção 1 primeiro.")
            return

        if not self.mapping_vars:
            messagebox.showerror(
                "Erro",
                "Execute 'Buscar Campos' na Seção 3 para montar o mapeamento."
            )
            return

        if (
            'X-Coordinate (Longitude)' not in self.mapping_vars
            or 'Y-Coordinate (Latitude)' not in self.mapping_vars
            or self.mapping_vars['X-Coordinate (Longitude)'].get() == "N/A (Não Mapear)"
            or self.mapping_vars['Y-Coordinate (Latitude)'].get() == "N/A (Não Mapear)"
        ):
            messagebox.showerror(
                "Erro",
                "Mapeamento de Longitude e Latitude é obrigatório."
            )
            return

        # verificação duplicação entre atributos
        used_cols = {}
        for agol_field, var in self.mapping_vars.items():
            if agol_field in ['X-Coordinate (Longitude)', 'Y-Coordinate (Latitude)']:
                continue
            col = var.get()
            if col != "N/A (Não Mapear)":
                if col in used_cols:
                    prev_field = used_cols[col]
                    messagebox.showerror(
                        "Erro de Mapeamento",
                        (
                            "Mapeamento duplicado detectado!\n\n"
                            f"A coluna do Excel '{col}' está mapeada "
                            "para mais de um campo do AGOL:\n"
                            f"- {prev_field}\n- {agol_field}\n\n"
                            "Cada coluna do Excel só pode alimentar um campo "
                            "(exceto as coordenadas)."
                        )
                    )
                    return
                used_cols[col] = agol_field

        if messagebox.askyesno(
            "Confirmar",
            (
                "Você tem certeza que deseja iniciar o processo de append?\n"
                "Isso verificará os dados e pedirá confirmação final antes de enviar."
            )
        ):
            self.cancel_requested.clear()
            self.all_added_objectids = []

            self.set_processing_state(True, upload_in_progress=True)
            self.log_message("--- Iniciando processo de Append ---")

            t = threading.Thread(target=self.run_append_thread, daemon=True)
            t.start()

    def _query_layer_as_dataframe(self, layer, out_fields_list, where_clause="1=1"):
        """Executa query no layer e devolve sempre um DataFrame pandas."""
        out_fields = ",".join(out_fields_list)

        try:
            result = layer.query(
                where=where_clause,
                out_fields=out_fields,
                return_geometry=False,
                return_as_df=True,
                return_all_records=True
            )
        except Exception as query_err:
            self.log_message(f"ERRO: A consulta ao AGOL falhou. {query_err}")
            self.log_message(f"Query: {where_clause}")
            return pd.DataFrame(columns=out_fields_list)

        if isinstance(result, pd.DataFrame):
            return result.copy()

        try:
            sdf = result.sdf
            if isinstance(sdf, pd.DataFrame):
                cols_to_keep = [col for col in out_fields_list if col in sdf.columns]
                return sdf[cols_to_keep].copy()
        except Exception:
            pass

        rows = []
        for feat in getattr(result, "features", []):
            attrs = getattr(feat, "attributes", {})
            row = {f: attrs.get(f) for f in out_fields_list}
            rows.append(row)
        return pd.DataFrame(rows, columns=out_fields_list)

    def run_append_thread(self):
        excel_path = self.excel_path_var.get()
        item_id = self.item_id_var.get()
        treatment_type_raw = self.treatment_var.get().strip()
        treatment_type_lower = treatment_type_raw.lower()

        features_to_add = []
        layer = None

        try:
            # 1) Lê Excel completo da aba selecionada
            selected_sheet = self.sheet_var.get().strip() if hasattr(self, 'sheet_var') else ""
            sheet_arg = selected_sheet if selected_sheet else 0
            self.log_message(f"Lendo arquivo Excel completo (Aba: '{selected_sheet or 'Padrão'}'): {excel_path}")
            df = pd.read_excel(excel_path, sheet_name=sheet_arg, dtype=str)
            self.log_message(f"Arquivo lido. {len(df)} linhas encontradas.")

            # limpeza global
            self.log_message(
                "Limpando dados: removendo espaços extras de todas as colunas de texto..."
            )
            for col in df.select_dtypes(include=['object']):
                df[col] = df[col].str.strip()

            if self.cancel_requested.is_set():
                raise Exception("Processo cancelado pelo usuário.")

            # 2) Aplica tratamento específico
            self.log_message(f"Aplicando tratamento: {treatment_type_raw}")
            process_func = self.treatment_functions.get(treatment_type_raw)
            if not process_func:
                raise Exception(
                    f"Função de tratamento '{treatment_type_raw}' não encontrada/carregada."
                )
            df = process_func(df, self.log_message)

            if df.empty:
                self.log_message(
                    "AVISO: Após o tratamento/filtro, 0 registros restaram. "
                    "Nenhum dado será enviado."
                )
                self.set_status("Concluído (0 registros).")
                self.master.after(
                    0,
                    lambda: self.set_processing_state(False, upload_in_progress=False)
                )
                return

            self.log_message(f"Tratamento aplicado. {len(df)} registros restantes.")

            # 2.5) Filtro de Indicador Geográfico, Mês e Ano (aplicados após tratamento)
            self._scan_available_years_from_df(df)

            # --- FILTRO DE INDICADOR GEOGRÁFICO ---
            selected_geo = self.geo_ind_var.get().strip() if hasattr(self, 'geo_ind_var') else "Todos"
            if selected_geo in ["Capital", "Interior"]:
                count_before_geo = len(df)
                selected_g_col = self.geo_col_var.get().strip() if hasattr(self, 'geo_col_var') else "Detectar Automaticamente"
                geo_col = None

                if selected_g_col != "Detectar Automaticamente" and selected_g_col in df.columns:
                    geo_col = selected_g_col
                else:
                    for candidate in [
                        'INDICADOR GEOGRAFICO', 'INDICADOR_GEOGRAFICO', 'INDICADOR GEOGRÁFICO',
                        'INDICADOR_GEOGRÁFICO', 'INDICADOR_GEO', 'REGIAO', 'REGIAO_FATO',
                        'MUNICIPIO_FATO', 'MUNICIPIO'
                    ]:
                        if candidate in df.columns:
                            geo_col = candidate
                            break

                if geo_col:
                    sample_vals = df[geo_col].dropna().astype(str).str.upper().str.strip()
                    is_capital_interior_col = any(v in ('CAPITAL', 'INTERIOR') for v in sample_vals.head(50))

                    if is_capital_interior_col or 'INDICADOR' in geo_col.upper() or 'REGIAO' in geo_col.upper():
                        if selected_geo == "Capital":
                            df = df[df[geo_col].astype(str).str.upper().str.strip() == 'CAPITAL'].copy()
                        else:
                            df = df[df[geo_col].astype(str).str.upper().str.strip() == 'INTERIOR'].copy()
                    else:
                        # Coluna de município (ex: MANAUS)
                        if selected_geo == "Capital":
                            df = df[df[geo_col].astype(str).str.upper().str.strip() == 'MANAUS'].copy()
                        else:
                            df = df[df[geo_col].astype(str).str.upper().str.strip() != 'MANAUS'].copy()

                    self.log_message(
                        f"Filtrado por Indicador Geográfico '{selected_geo}' na coluna '{geo_col}'. "
                        f"Registros: {count_before_geo} -> {len(df)}"
                    )
                else:
                    self.log_message(
                        f"AVISO: Indicador Geográfico '{selected_geo}' selecionado mas nenhuma coluna geográfica "
                        f"encontrada ou válida. Coluna especificada: '{selected_g_col}'. Filtro geográfico não aplicado."
                    )

            # --- FILTRO DE MÊS ---
            selected_month = self.month_var.get().strip() if hasattr(self, 'month_var') else "Todos"
            if selected_month and selected_month != "Todos":
                count_before_month = len(df)
                selected_m_col = self.month_col_var.get().strip() if hasattr(self, 'month_col_var') else "Detectar Automaticamente"

                month_num = MONTH_NAME_TO_NUM.get(selected_month.upper())
                if month_num is None:
                    try:
                        month_num = MONTHS_LIST.index(selected_month)
                    except Exception:
                        month_num = None

                month_col = None
                month_type = None  # 'num' ou 'name'

                if selected_m_col != "Detectar Automaticamente" and selected_m_col in df.columns:
                    month_col = selected_m_col
                    sample_vals = df[month_col].dropna().astype(str).str.strip().str.upper()
                    if any(v in MONTH_NAME_TO_NUM for v in sample_vals.head(30)):
                        month_type = 'name'
                    else:
                        month_type = 'num'
                else:
                    for candidate in ['MES_ORDEM', 'MES_FATO', 'CAMPO_MES_NUM', 'mes', 'MES', 'month', 'MONTH']:
                        if candidate in df.columns:
                            month_col = candidate
                            month_type = 'num'
                            break

                    if not month_col:
                        for candidate in ['CAMPO_MES', 'NOME_MES']:
                            if candidate in df.columns:
                                month_col = candidate
                                month_type = 'name'
                                break

                if month_col and month_type == 'num' and month_num is not None:
                    numeric_series = pd.to_numeric(df[month_col], errors='coerce')
                    df = df[numeric_series == month_num].copy()
                    self.log_message(
                        f"Filtrado por mês '{selected_month}' (#{month_num}) na coluna '{month_col}'. "
                        f"Registros: {count_before_month} -> {len(df)}"
                    )
                elif month_col and month_type == 'name':
                    m_up = selected_month.upper()
                    m_norm = m_up.replace('Ç', 'C').replace('ç', 'c')
                    allowed_names = {m_up, m_norm}
                    df = df[
                        df[month_col].astype(str).str.upper().str.strip().isin(allowed_names)
                    ].copy()
                    self.log_message(
                        f"Filtrado por mês '{selected_month}' na coluna '{month_col}'. "
                        f"Registros: {count_before_month} -> {len(df)}"
                    )
                else:
                    date_col = None
                    for candidate in ['DT_INICIO_FATO', 'DATA_FATO', 'DATA', 'geracao', 'dt_geracao', 'DATA_OCORRENCIA']:
                        if candidate in df.columns:
                            date_col = candidate
                            break
                    if date_col and month_num is not None:
                        try:
                            temp_dates = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
                            df = df[temp_dates.dt.month == month_num].copy()
                            self.log_message(
                                f"Filtrado por mês '{selected_month}' extraído da coluna '{date_col}'. "
                                f"Registros: {count_before_month} -> {len(df)}"
                            )
                        except Exception as me_err:
                            self.log_message(f"AVISO: Falha ao extrair mês de '{date_col}': {me_err}")
                    else:
                        self.log_message(
                            f"AVISO: Mês '{selected_month}' selecionado mas nenhuma coluna de mês "
                            f"encontrada ou válida. Coluna especificada: '{selected_m_col}'. Filtro de mês não aplicado."
                        )

            # --- FILTRO DE ANO ---
            selected_year = self.year_var.get().strip() if hasattr(self, 'year_var') else "Todos"
            if selected_year and selected_year != "Todos" and selected_year.isdigit():
                target_year = int(selected_year)
                count_before_year = len(df)

                selected_y_col = self.year_col_var.get().strip() if hasattr(self, 'year_col_var') else "Detectar Automaticamente"
                year_col = None

                if selected_y_col != "Detectar Automaticamente" and selected_y_col in df.columns:
                    year_col = selected_y_col
                else:
                    for candidate in ['ANO_INICIO_FATO', 'ANO_FATO', 'CAMPO_ANO', 'CAMPO_ANO_INICIO', 'ano', 'ANO', 'year', 'YEAR']:
                        if candidate in df.columns:
                            year_col = candidate
                            break

                if year_col:
                    parsed_years = pd.to_numeric(df[year_col], errors='coerce')
                    if parsed_years.dropna().empty:
                        try:
                            parsed_dts = pd.to_datetime(df[year_col], dayfirst=True, errors='coerce')
                            parsed_years = parsed_dts.dt.year
                        except Exception:
                            pass

                    df = df[parsed_years == target_year].copy()
                    self.log_message(
                        f"Filtrado por ano '{target_year}' na coluna '{year_col}'. "
                        f"Registros: {count_before_year} -> {len(df)}"
                    )
                else:
                    date_col = None
                    for candidate in ['DT_INICIO_FATO', 'DATA_FATO', 'DATA', 'geracao', 'dt_geracao', 'DATA_OCORRENCIA']:
                        if candidate in df.columns:
                            date_col = candidate
                            break
                    if date_col:
                        try:
                            temp_dates = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
                            df = df[temp_dates.dt.year == target_year].copy()
                            self.log_message(
                                f"Filtrado por ano '{target_year}' extraído da coluna '{date_col}'. "
                                f"Registros: {count_before_year} -> {len(df)}"
                            )
                        except Exception as ye_err:
                            self.log_message(f"AVISO: Falha ao extrair ano de '{date_col}': {ye_err}")
                    else:
                        self.log_message(
                            f"AVISO: Ano '{target_year}' selecionado mas nenhuma coluna de ano "
                            f"encontrada ou válida. Coluna especificada: '{selected_y_col}'. Filtro de ano não aplicado."
                        )

            if df.empty:
                self.log_message(
                    "AVISO: Após aplicação dos filtros (Geográfico/Mês/Ano), 0 registros restaram."
                )
                self.set_status("Concluído (0 registros).")
                self.master.after(
                    0,
                    lambda: self.set_processing_state(False, upload_in_progress=False)
                )
                return

            # 3) Monta dict final_mapping: {agol_field: excel_col}
            final_mapping = {}
            for agol_field, var in self.mapping_vars.items():
                excel_col = var.get()
                if excel_col != "N/A (Não Mapear)":
                    final_mapping[agol_field] = excel_col

            if not final_mapping:
                raise Exception("Nenhum campo foi mapeado. Processo abortado.")

            if self.cancel_requested.is_set():
                raise Exception("Processo cancelado pelo usuário.")

            # 4) verificação duplicatas externa (AGOL)
            self.log_message("Validando duplicatas (contra dados existentes) no AGOL...")
            item = self.gis.content.get(item_id)
            layer = item.layers[0]

            key_func = self.treatment_keys.get(treatment_type_raw)
            if not key_func:
                for k_name, func in self.treatment_keys.items():
                    if k_name.lower() == treatment_type_lower:
                        key_func = func
                        break

            if key_func:
                key_pairs = key_func()
                self.log_message(f"Usando chaves de duplicata do módulo: {[k[0] for k in key_pairs]}")
            else:
                key_pairs = []
                self.log_message(
                    "AVISO: Módulo de tratamento não forneceu 'get_duplicate_keys'. "
                    "Verificação de duplicatas será ignorada."
                )

            required_ok = True
            if not key_pairs:
                required_ok = False

            mapping_lower = {k.lower(): (k, v) for k, v in final_mapping.items()}

            for agol_field, excel_col_fallback, _tipo in key_pairs:
                ag_lower = agol_field.lower()
                mapped_info = mapping_lower.get(ag_lower)
                if not mapped_info and excel_col_fallback not in df.columns:
                    required_ok = False
                    self.log_message(
                        f"AVISO: verificação de duplicatas ignorada porque '{agol_field}' não está mapeado."
                    )
                    break

            # Fix #2: usar flag booleana em vez de acessar widget de thread
            self._dup_check_skipped = not required_ok

            if required_ok:
                agol_fields_to_query = []
                for ag, _ex, _t in key_pairs:
                    mapped_tuple = mapping_lower.get(ag.lower())
                    agol_fields_to_query.append(mapped_tuple[0] if mapped_tuple else ag)

                where_parts = []
                try:
                    for agol_field, excel_col_fallback, f_type in key_pairs:
                        mapped_tuple = mapping_lower.get(agol_field.lower())
                        agol_real_field = mapped_tuple[0] if mapped_tuple else agol_field
                        excel_col = mapped_tuple[1] if mapped_tuple else excel_col_fallback

                        if excel_col not in df.columns:
                            self.log_message(f"Aviso: Coluna chave '{excel_col}' não no DF. Usando '1=1'.")
                            where_parts = []
                            break

                        unique_vals = df[excel_col].dropna().unique()

                        if f_type == "num":
                            num_list = [
                                int(float(v)) for v in unique_vals
                                if str(v).strip() != "" and pd.notna(v) and str(v).strip().replace('.', '', 1).isdigit()
                            ]
                            if len(num_list) > 200:
                                min_v, max_v = min(num_list), max(num_list)
                                where_parts.append(f"({agol_real_field} >= {min_v} AND {agol_real_field} <= {max_v})")
                            elif num_list:
                                vals_sql = ", ".join(map(str, num_list))
                                where_parts.append(f"{agol_real_field} IN ({vals_sql})")
                        else:
                            sql_vals_list = []
                            for v in unique_vals:
                                val_str = str(v).strip()
                                if val_str != "" and pd.notna(v):
                                    sql_safe_val = val_str.replace("'", "''")
                                    sql_vals_list.append(f"'{sql_safe_val}'")

                            if len(sql_vals_list) <= 300 and sql_vals_list:
                                vals_sql = ", ".join(sql_vals_list)
                                where_parts.append(f"{agol_real_field} IN ({vals_sql})")

                except Exception as e:
                    self.log_message(f"AVISO: Falha ao construir filtro SQL otimizado ({e}). Usando '1=1'.")
                    where_parts = []

                if where_parts:
                    where_clause = " AND ".join(where_parts)
                    self.log_message(f"Usando query otimizada: {where_clause}")
                else:
                    where_clause = "1=1"
                    self.log_message("Usando query '1=1' (pode ser lento para camadas grandes).")

                df_agol = self._query_layer_as_dataframe(layer, agol_fields_to_query, where_clause)
                self.log_message(
                    f"{len(df_agol)} registros existentes baixados do AGOL para verificação."
                )

                if df_agol.empty:
                    self.log_message("Nenhum registro conflitante encontrado no AGOL (camada vazia ou filtro não bateu).")

                else:
                    def norm_num(series):
                        return (
                            pd.to_numeric(series, errors="coerce")
                            .fillna(0)
                            .astype(int)
                            .astype(str)
                        )

                    def norm_str(series):
                        return (
                            series.astype(str)
                            .str.strip()
                            .str.upper()
                        )

                    df_agol_cols_lower = {c.lower(): c for c in df_agol.columns}
                    agol_key_parts = []
                    for agol_field, _ex_col, tipo in key_pairs:
                        matched_col = df_agol_cols_lower.get(agol_field.lower())
                        if not matched_col:
                            agol_key_parts = []
                            break
                        if tipo == "num":
                            agol_key_parts.append(norm_num(df_agol[matched_col]))
                        else:
                            agol_key_parts.append(norm_str(df_agol[matched_col]))

                    if agol_key_parts:
                        df_agol["__COMPOSITE_KEY"] = pd.concat(agol_key_parts, axis=1)\
                            .apply(lambda r: "_".join(r), axis=1)
                        existing_keys = set(df_agol["__COMPOSITE_KEY"])
                    else:
                        existing_keys = set()

                    excel_key_parts = []
                    for agol_field, excel_col_fallback, tipo in key_pairs:
                        mapped_tuple = mapping_lower.get(agol_field.lower())
                        src_col = mapped_tuple[1] if mapped_tuple else excel_col_fallback
                        if src_col not in df.columns:
                            excel_key_parts = []
                            break
                        if tipo == "num":
                            excel_key_parts.append(norm_num(df[src_col]))
                        else:
                            excel_key_parts.append(norm_str(df[src_col]))

                    if excel_key_parts:
                        df["__COMPOSITE_KEY"] = pd.concat(excel_key_parts, axis=1)\
                            .apply(lambda r: "_".join(r), axis=1)

                        is_dup_mask = df["__COMPOSITE_KEY"].isin(existing_keys)
                        duplicates_found_external = is_dup_mask.sum()

                        if duplicates_found_external > 0:
                            first_dup_row = df[is_dup_mask].iloc[0]
                            exemplo = {}
                            for agol_field, excel_col_fallback, _tipo in key_pairs:
                                src_col = final_mapping.get(agol_field, excel_col_fallback)
                                if src_col in first_dup_row:
                                    exemplo[src_col] = first_dup_row[src_col]

                            raise Exception(
                                "DUPLICATA ENCONTRADA. O processo foi abortado. "
                                f"Exemplo: {exemplo}"
                            )

                        if "__COMPOSITE_KEY" in df.columns:
                            df.drop(columns=["__COMPOSITE_KEY"], inplace=True)

                    self.log_message(
                        "Nenhuma duplicata externa encontrada para esta chave composta."
                    )

            else:
                self.log_message("Verificação de duplicatas pulada (campos-chave não mapeados).")

            if self.cancel_requested.is_set():
                raise Exception("Processo cancelado pelo usuário.")

            # 5) Criar features com geometria + atributos
            if df.empty:
                self.log_message(
                    "AVISO: Após todas as filtragens, 0 registros restaram. "
                    "Nenhum dado será enviado."
                )
                self.set_status("Concluído (0 registros).")
                self.master.after(
                    0,
                    lambda: self.set_processing_state(False, upload_in_progress=False)
                )
                return

            self.log_message("Mapeando colunas e convertendo tipos...")

            if 'X-Coordinate (Longitude)' not in final_mapping \
                or 'Y-Coordinate (Latitude)' not in final_mapping:
                raise Exception("Longitude/Latitude não mapeados corretamente.")

            x_col = final_mapping.pop('X-Coordinate (Longitude)')
            y_col = final_mapping.pop('Y-Coordinate (Latitude)')

            agol_field_types = self.agol_fields
            features_to_add = []

            records = df.to_dict(orient='records')
            mapping_items = list(final_mapping.items())

            for idx, row in enumerate(records):
                attributes = {}
                for agol_field, excel_col in mapping_items:
                    if excel_col in row:
                        agol_type = agol_field_types.get(agol_field)
                        original_value = row[excel_col]
                        converted_value = self._convert_value(original_value, agol_type)
                        attributes[agol_field] = converted_value

                try:
                    raw_x = str(row.get(x_col, '')).replace(',', '.')
                    raw_y = str(row.get(y_col, '')).replace(',', '.')
                    x_val = float(raw_x)
                    y_val = float(raw_y)
                    if not (-180 <= x_val <= 180 and -90 <= y_val <= 90):
                        raise ValueError(f"Coordenadas inválidas (X={x_val}, Y={y_val})")

                    geometry = {
                        'x': x_val,
                        'y': y_val,
                        'spatialReference': {'wkid': 4326}
                    }
                    features_to_add.append(
                        Feature(geometry=geometry, attributes=attributes)
                    )
                except (ValueError, TypeError) as geo_err:
                    self.log_message(
                        f"AVISO: Ignorando linha Excel {idx+2} por erro de geometria: {geo_err}"
                    )

            if not features_to_add:
                raise Exception(
                    "Nenhuma feature válida foi criada. "
                    "Verifique dados de geometria e mapeamento."
                )

            # 6) Confirmação final
            self.log_message(
                f"VERIFICAÇÃO CONCLUÍDA. {len(features_to_add)} novos registros prontos para envio."
            )
            self.master.after(
                0,
                self.ask_for_upload_confirmation,
                features_to_add,
                layer
            )

        except Exception as e:
            msg = str(e)
            if "cancelado pelo usuário" in msg.lower():
                self.log_message("Processo de verificação cancelado.")
                self.set_status("Cancelado.")
            elif "DUPLICATA ENCONTRADA" in msg:
                self.log_message(f"ERRO: {e}")
                self.set_status("Cancelado (Duplicata).")
                self.gui_messagebox_error("Duplicata Encontrada", msg)
            else:
                self.log_message(f"ERRO FATAL no processo: {e}")
                self.set_status(f"Erro: {e}")
                self.gui_messagebox_error(
                    "Erro no Append",
                    (
                        "Ocorreu um erro durante o processo.\n"
                        "Verifique o log para detalhes.\n\n"
                        f"Detalhe: {e}"
                    )
                )

            self.master.after(
                0,
                lambda: self.set_processing_state(False, upload_in_progress=False)
            )

    def ask_for_upload_confirmation(self, features_to_add, layer):
        total = len(features_to_add)

        if self.cancel_requested.is_set():
            self.log_message("Envio cancelado pelo usuário antes da confirmação final.")
            self.set_status("Cancelado.")
            self.set_processing_state(False, upload_in_progress=False)
            return

        # Fix #2: usa flag booleana em vez de acessar widget
        if self._dup_check_skipped:
            msg_duplicata = "A verificação de duplicatas foi PULADA (campos-chave não mapeados).\n\n"
        else:
            msg_duplicata = "A verificação de duplicatas foi concluída.\nNENHUMA duplicata existente foi encontrada.\n\n"

        msg = (
            f"{msg_duplicata}"
            f"{total} novos registros estão prontos para serem enviados.\n\n"
            "Deseja continuar com o envio?"
        )

        if messagebox.askyesno("Confirmar Envio", msg):
            self.log_message(f"Iniciando envio de {total} registros...")
            self.set_status(f"Enviando 0/{total}...")

            upload_thread = threading.Thread(
                target=self.upload_thread,
                args=(features_to_add, layer),
                daemon=True
            )
            upload_thread.start()
        else:
            self.log_message("Envio cancelado pelo usuário.")
            self.set_status("Cancelado.")
            self.set_processing_state(False, upload_in_progress=False)

    def upload_thread(self, features_to_add, layer):
        try:
            total_to_add = len(features_to_add)
            self.all_added_objectids = []

            chunk_size = 1000
            chunks = [features_to_add[i:i+chunk_size] for i in range(0, total_to_add, chunk_size)]
            total_batches = len(chunks)

            completed_batches = 0
            lock = threading.Lock()

            def process_batch(batch_tuple):
                batch_idx, chunk, offset = batch_tuple
                if self.cancel_requested.is_set():
                    return None

                self.log_message(
                    f"Enviando lote {batch_idx}/{total_batches} ({len(chunk)} feições em paralelo)..."
                )

                try:
                    result = layer.edit_features(adds=chunk, use_global_ids=False)
                except Exception as batch_e:
                    result = {}
                    self.log_message(f"Aviso no envio do lote {batch_idx}: {batch_e}")

                added_oids = [
                    r['objectId']
                    for r in result.get('addResults', [])
                    if r.get('success')
                ]

                with lock:
                    self.all_added_objectids.extend(added_oids)
                    nonlocal completed_batches
                    completed_batches += 1
                    sent_count = min(completed_batches * chunk_size, total_to_add)
                    self.set_status(f"Enviando {sent_count}/{total_to_add}...")

                add_errors = [
                    r['error']
                    for r in result.get('addResults', [])
                    if not r.get('success')
                ]

                if add_errors or not result.get('addResults'):
                    error_details = str(add_errors[0]) if add_errors else "Lote rejeitado pela API"
                    self.log_message(
                        f"AVISO: Lote {batch_idx} retornou erro ({error_details}). Inspecionando registros individualmente..."
                    )
                    failed_count = 0
                    for single_idx, single_feat in enumerate(chunk):
                        excel_line = offset + single_idx + 2
                        try:
                            s_res = layer.edit_features(adds=[single_feat], use_global_ids=False)
                            s_adds = s_res.get('addResults', [])
                            if s_adds and s_adds[0].get('success'):
                                with lock:
                                    self.all_added_objectids.append(s_adds[0]['objectId'])
                            else:
                                failed_count += 1
                                s_err = s_adds[0].get('error', {}) if s_adds else "Erro não especificado"
                                self.log_message(f"ERRO no registro da Linha ~{excel_line} do Excel: {s_err}")
                                self.log_message(f"Atributos da linha {excel_line}: {single_feat.attributes}")
                        except Exception as s_e:
                            failed_count += 1
                            self.log_message(f"ERRO no registro da Linha ~{excel_line} do Excel: {s_e}")
                            self.log_message(f"Atributos da linha {excel_line}: {single_feat.attributes}")

                    if failed_count > 0:
                        raise Exception(
                            f"{failed_count} registro(s) no lote {batch_idx} falharam durante o envio. "
                            "Verifique o log de execução acima para identificar as linhas do Excel e o detalhe do erro."
                        )

            batch_tasks = [(idx + 1, chunk, idx * chunk_size) for idx, chunk in enumerate(chunks)]

            # Executa envio paralelo em 3 conexões simultâneas
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(process_batch, task) for task in batch_tasks]
                for future in concurrent.futures.as_completed(futures):
                    if self.cancel_requested.is_set():
                        raise Exception("Processo cancelado pelo usuário.")
                    future.result()  # Propaga exceções de lote se houver

            # sucesso
            self.log_message(
                f"--- SUCESSO! {len(self.all_added_objectids)} feições adicionadas à camada. ---"
            )
            self.set_status("Append concluído com sucesso!")
            self.gui_messagebox_info(
                "Sucesso",
                (
                    f"{len(self.all_added_objectids)} registros foram adicionados "
                    "com sucesso à camada."
                )
            )

        except Exception as e:
            msg = str(e)
            if "cancelado pelo usuário" in msg.lower():
                self.log_message("Cancelamento recebido!")
                if self.all_added_objectids:
                    self.log_message(
                        f"Revertendo {len(self.all_added_objectids)} registros já enviados..."
                    )
                    self.set_status("Revertendo...")
                    try:
                        delete_result = layer.edit_features(
                            deletes=self.all_added_objectids
                        )
                        self.log_message(f"Reversão concluída: {delete_result}")
                    except Exception as del_e:
                        self.log_message(
                            f"ERRO CRÍTICO: Falha ao reverter registros. {del_e}"
                        )
                        self.gui_messagebox_error(
                            "Erro no Cancelamento",
                            (
                                "Falha ao reverter registros.\n\n"
                                f"Detalhe: {del_e}"
                            )
                        )
                else:
                    self.log_message("Nenhum registro precisou ser revertido.")
                self.set_status("Cancelado.")
            else:
                self.log_message(f"ERRO FATAL no processo: {e}")
                self.set_status(f"Erro: {e}")
                self.gui_messagebox_error(
                    "Erro no Append",
                    (
                        "Ocorreu um erro durante o envio.\n"
                        "Verifique o log para detalhes.\n\n"
                        f"Detalhe: {e}"
                    )
                )

        finally:
            self.master.after(
                0,
                lambda: self.set_processing_state(False, upload_in_progress=False)
            )

    def _convert_value(self, value, agol_type_str):
        """Converte string lida do Excel pro tipo esperado no AGOL."""
        if (
            value is None
            or pd.isna(value)
            or str(value).strip().upper() in ('', 'N.I', 'NONE', '<NULL>', 'NAN', 'NAT')
        ):
            return None

        val_str = str(value).strip()

        try:
            if agol_type_str in ("Inteiro", "Inteiro (Pequeno)"):
                if ":" in val_str:
                    val_str = val_str.split(":")[0]
                return int(float(val_str.replace(',', '.')))

            if agol_type_str in ("Decimal (Double)", "Decimal (Single)"):
                if ":" in val_str:
                    val_str = val_str.split(":")[0]
                return float(val_str.replace(',', '.'))

            if agol_type_str == "Data":
                dt = None
                if isinstance(value, (pd.Timestamp, datetime, date)):
                    dt = pd.to_datetime(value)
                else:
                    try:
                        dt = pd.to_datetime(val_str, dayfirst=True)
                    except Exception:
                        try:
                            dt = pd.to_datetime(val_str)
                        except Exception:
                            pass

                if dt is not None and pd.notna(dt):
                    # O ArcGIS Online REST API para campos esriFieldTypeDate exige um timestamp inteiro em milissegundos UTC (epoch ms)
                    try:
                        return int(dt.value // 10**6)
                    except Exception:
                        return int(dt.timestamp() * 1000)
            # Remove/substitui caracteres HTML não seguros (< e >) que o AGOL bloqueia por segurança (Erro Esri 1006)
            return val_str.replace('<', '[').replace('>', ']')

        except (ValueError, TypeError) as e:
            self.log_message(
                f"Aviso: Não foi possível converter valor '{value}' "
                f"para o tipo '{agol_type_str}'. "
                f"Enviando None. Erro: {e}"
            )
            return None


# =====================
# MAIN
# =====================
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ArcGISUpdaterApp(root)

        if getattr(app, "init_ok", False):
            root.mainloop()

    except Exception as e:
        print(f"Erro fatal ao iniciar a aplicação: {e}")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Erro Fatal",
                f"Ocorreu um erro crítico ao iniciar:\n{e}"
            )
        except Exception:
            pass
        sys.exit(1)