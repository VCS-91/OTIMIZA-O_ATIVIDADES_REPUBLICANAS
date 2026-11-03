# Interface principal do sistema da republica e controle do pingometro
import argparse
import csv
import datetime as dt
import os
import random
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import dados
import persistencia
from busca_classica import planejar_semana
from busca_local import PESOS, ProblemaEscala, gerar_escala
from busca_online import AgenteOnline, Imprevisto
from dados import DIAS, TURNOS

COR = {
    "bg_janela": "#f4f6f9",
    "bg_card": "#ffffff",
    "borda": "#e2e8f0",
    "cabecalho": "#1e293b",
    "cabecalho_hoje": "#3b82f6",
    "coluna_hoje": "#eff6ff",
    "celula": "#ffffff",
    "celula_alt": "#f8fafc",
    "livre": "#f1f5f9",
    "livre_texto": "#64748b",
    "conflito": "#fee2e2",
    "alterada": "#fef3c7",
    "concluida": "#dcfce7",
    "concluida_texto": "#15803d",
    "texto": "#0f172a",
    "texto_sec": "#64748b",
    "passado": "#94a3b8",
    "primaria": "#2563eb",
    "primaria_hover": "#1d4ed8",
    "perigo": "#dc2626",
    "perigo_hover": "#b91c1c",
    "sucesso": "#16a34a",
    "aviso": "#d97706",
    "pinga": "#b45309",
}

FONTE_TITULO = ("Segoe UI", 15, "bold")
FONTE_SUBTITULO = ("Segoe UI", 9)
FONTE_CARD_VALOR = ("Segoe UI", 13, "bold")
FONTE_CARD_ROTULO = ("Segoe UI", 8, "bold")
FONTE = ("Segoe UI", 9)
FONTE_NEGRITO = ("Segoe UI", 9, "bold")
FONTE_PEQUENA = ("Segoe UI", 8)

TIPOS_HUMANOS = {
    "indisponivel": "Morador deu baixa (Ficou ocupado / Imprevisto)",
    "extra": "Problema / Tarefa Extra Urgente",
    "nao_realizada": "Migué / Tarefa não foi feita (+1 Dose de Pinga 🥃)",
}

NOMES_PENALIDADES_HUMANOS = {
    "indisponivel": "Tarefa jogada em horário de aula/trabalho ou folga",
    "dia_repetido": "Mesma tarefa repetida no mesmo dia",
    "choque": "Morador com 2 tarefas ao mesmo tempo (mesmo turno)",
    "dependencia": "Ordem errada (ex: passar pano antes de varrer)",
    "dias_seguidos": "Mesma tarefa pesada em dias colados",
    "carga": "Divisão injusta de esforço entre a galera",
    "preferencia": "Tarefa fora do dia que o morador prefere",
    "mudanca": "Trocas de última hora na escala",
}


class MultaPinga:
    def __init__(self, id_multa, integrante, dia, motivo, doses=1, paga=False):
        self.id_multa = id_multa
        self.integrante = integrante
        self.dia = dia
        self.motivo = motivo
        self.doses = doses
        self.paga = paga


MAX_LINHAS_LOG_SALVAS = 500


class App(tk.Tk):
    def __init__(self, integrantes, tarefas, fonte, origem=None, estado_salvo=None,
                 arquivo_estado=persistencia.ARQUIVO_PADRAO):
        super().__init__()
        self.title("Painel da República — Escala e Organização")
        self.geometry("1460x880")
        self.minsize(1200, 700)
        self.configure(bg=COR["bg_janela"])

        self.integrantes = integrantes
        self.tarefas = tarefas
        self.fonte = fonte
        # de onde vieram os horários, para reler o Forms quando a semana virar:
        # {"tipo": "simulado"} | {"tipo": "csv", "ref": caminho} | {"tipo": "sheets", "ref": link}
        self.origem = origem or {"tipo": "simulado"}
        self.arquivo_estado = arquivo_estado
        self.rng = random.Random()
        self.data_real = dt.date.today()
        self.plano = None
        self.resultado = None
        self.agente = None

        self.concluidas = set()
        self.multas = []
        self._seq_multa = 1
        self._entradas_log = []
        self._erro_ao_salvar = False

        self._configurar_estilo()
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        recuperado = False
        if estado_salvo:
            try:
                self._restaurar(estado_salvo)
                recuperado = True
            except Exception as erro:
                self.integrantes, self.multas, self.concluidas = integrantes, [], set()
                self._log(f"⚠ Não deu para recuperar a escala salva ({erro}). Montando uma nova.", "erro")
        if recuperado:
            self._sincronizar_data()
        else:
            self.nova_escala(self.data_real.weekday())
        self.after(60000, self._verificar_data)

    def _configurar_estilo(self):
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")

        estilo.configure(".", background=COR["bg_janela"], foreground=COR["texto"], font=FONTE)
        estilo.configure("TFrame", background=COR["bg_janela"])

        estilo.configure("TNotebook", background=COR["bg_janela"], borderwidth=0)
        estilo.configure(
            "TNotebook.Tab",
            font=FONTE_NEGRITO,
            padding=(16, 9),
            background="#e2e8f0",
            foreground=COR["texto_sec"],
            borderwidth=0,
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", COR["bg_card"]), ("active", "#cbd5e1")],
            foreground=[("selected", COR["primaria"]), ("active", COR["texto"])],
        )

        estilo.configure(
            "TButton",
            font=FONTE,
            padding=(10, 6),
            background=COR["bg_card"],
            foreground=COR["texto"],
            bordercolor=COR["borda"],
        )
        estilo.map("TButton", background=[("active", "#e2e8f0")])

        estilo.configure(
            "Primario.TButton",
            font=FONTE_NEGRITO,
            padding=(12, 6),
            background=COR["primaria"],
            foreground="white",
            bordercolor=COR["primaria"],
        )
        estilo.map("Primario.TButton", background=[("active", COR["primaria_hover"])])

        estilo.configure(
            "Sucesso.TButton",
            font=FONTE_NEGRITO,
            padding=(12, 6),
            background=COR["sucesso"],
            foreground="white",
            bordercolor=COR["sucesso"],
        )
        estilo.map("Sucesso.TButton", background=[("active", "#15803d")])

        estilo.configure(
            "Alerta.TButton",
            font=FONTE_NEGRITO,
            padding=(12, 6),
            background="#fff7ed",
            foreground=COR["aviso"],
            bordercolor="#fed7aa",
        )
        estilo.map("Alerta.TButton", background=[("active", "#ffedd5")])

        estilo.configure(
            "Treeview",
            font=FONTE,
            rowheight=32,
            background=COR["bg_card"],
            fieldbackground=COR["bg_card"],
            foreground=COR["texto"],
            borderwidth=0,
        )
        estilo.configure(
            "Treeview.Heading",
            font=FONTE_NEGRITO,
            background="#f1f5f9",
            foreground=COR["texto"],
            padding=(10, 8),
            relief="flat",
        )
        estilo.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", COR["primaria"])])

        estilo.configure("TLabelframe", background=COR["bg_card"], bordercolor=COR["borda"])
        estilo.configure("TLabelframe.Label", background=COR["bg_card"], foreground=COR["texto"], font=FONTE_NEGRITO)

    def _montar(self):
        topo = tk.Frame(self, bg=COR["cabecalho"], padx=18, pady=12)
        topo.pack(fill="x")

        esq_topo = tk.Frame(topo, bg=COR["cabecalho"])
        esq_topo.pack(side="left")
        tk.Label(
            esq_topo,
            text="🏠 Painel da República — Gestão, Escala & Pingômetro",
            font=FONTE_TITULO,
            bg=COR["cabecalho"],
            fg="white",
        ).pack(anchor="w")
        tk.Label(
            esq_topo,
            text="Organização automática da limpeza respeitando aulas na UFOP, hierarquia, folgas e controle de multas em doses de pinga",
            font=FONTE_SUBTITULO,
            bg=COR["cabecalho"],
            fg="#94a3b8",
        ).pack(anchor="w")

        painel_controle = ttk.Frame(self, padding=(14, 10))
        painel_controle.pack(fill="x")

        barra_botoes = ttk.Frame(painel_controle)
        barra_botoes.pack(side="left", fill="y")

        grupo_dados = ttk.LabelFrame(barra_botoes, text=" Horários da Galera ", padding=(8, 4))
        grupo_dados.pack(side="left", padx=(0, 8))
        ttk.Button(grupo_dados, text="Usar Exemplo", command=self.usar_simulados).pack(side="left", padx=2)
        ttk.Button(grupo_dados, text="Abrir CSV...", command=self.importar_csv).pack(side="left", padx=2)
        ttk.Button(grupo_dados, text="Planilha Online...", command=self.importar_sheets).pack(side="left", padx=2)

        grupo_acoes = ttk.LabelFrame(barra_botoes, text=" Dia a Dia da Casa ", padding=(8, 4))
        grupo_acoes.pack(side="left")
        ttk.Button(grupo_acoes, text="↻ Sortear Nova Escala", style="Primario.TButton", command=self.regerar).pack(
            side="left", padx=3
        )
        ttk.Button(
            grupo_acoes,
            text="⚡ Deu Ruim / Imprevisto...",
            style="Alerta.TButton",
            command=lambda: DialogoImprevisto(self),
        ).pack(side="left", padx=3)
        ttk.Button(grupo_acoes, text="🎲 Simular B.O.", command=self.imprevisto_aleatorio).pack(side="left", padx=3)
        ttk.Button(grupo_acoes, text="Passar Dia ▶", command=self.avancar_dia).pack(side="left", padx=3)

        kpis = ttk.Frame(painel_controle)
        kpis.pack(side="right")
        self.kpi_dia = self._criar_card_kpi(kpis, "HOJE É", "—")
        self.kpi_clima = self._criar_card_kpi(kpis, "CLIMA DA CASA", "—")
        self.kpi_tarefas = self._criar_card_kpi(kpis, "TAREFAS DO DIA", "0/0")
        self.kpi_pinga = self._criar_card_kpi(kpis, "🥃 PINGÔMETRO", "0 doses")

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._montar_aba_escala()
        self._montar_aba_moradores()
        self._montar_aba_pingometro()
        self._montar_aba_mural()
        self._montar_aba_professor()

    def _criar_card_kpi(self, pai, titulo, valor_inicial):
        card = tk.Frame(
            pai,
            bg=COR["bg_card"],
            highlightbackground=COR["borda"],
            highlightthickness=1,
            padx=12,
            pady=6,
        )
        card.pack(side="left", padx=4)
        tk.Label(card, text=titulo, font=FONTE_CARD_ROTULO, bg=COR["bg_card"], fg=COR["texto_sec"]).pack(anchor="w")
        lbl_valor = tk.Label(card, text=valor_inicial, font=FONTE_CARD_VALOR, bg=COR["bg_card"], fg=COR["texto"])
        lbl_valor.pack(anchor="w")
        return lbl_valor

    def _montar_aba_escala(self):
        aba = tk.Frame(self.abas, bg=COR["bg_card"], padx=12, pady=10)
        self.abas.add(aba, text=" 📅 Quadro da Semana & Check-in ")

        quadro_hoje = tk.Frame(
            aba, bg="#f8fafc", highlightbackground=COR["borda"], highlightthickness=1, padx=12, pady=8
        )
        quadro_hoje.pack(fill="x", pady=(0, 10))

        topo_hoje = tk.Frame(quadro_hoje, bg="#f8fafc")
        topo_hoje.pack(fill="x", pady=(0, 6))
        self.lbl_titulo_hoje = tk.Label(
            topo_hoje,
            text="📌 Tarefas de Hoje — Confirme o que foi feito ou clique em 'Não fez' para realocar e aplicar +1 dose de pinga:",
            font=FONTE_NEGRITO,
            bg="#f8fafc",
            fg=COR["primaria"],
        )
        self.lbl_titulo_hoje.pack(side="left")

        self.container_checkin = tk.Frame(quadro_hoje, bg="#f8fafc")
        self.container_checkin.pack(fill="x")

        quadro = tk.Frame(aba, bg=COR["borda"], bd=1, relief="solid")
        quadro.pack(fill="both", expand=True)

        canvas = tk.Canvas(quadro, highlightthickness=0, bg=COR["borda"])
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=canvas.yview)
        self.grade = tk.Frame(canvas, bg=COR["borda"])
        janela = canvas.create_window((0, 0), window=self.grade, anchor="nw")

        self.grade.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(janela, width=e.width))
        canvas.configure(yscrollcommand=rolagem.set)

        canvas.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

        legenda = tk.Frame(aba, bg=COR["bg_card"], pady=8)
        legenda.pack(fill="x")
        tk.Label(legenda, text="Cores do Quadro:", font=FONTE_NEGRITO, bg=COR["bg_card"], fg=COR["texto"]).pack(
            side="left", padx=(0, 8)
        )
        itens_legenda = [
            (COR["coluna_hoje"], "#93c5fd", "Dia de Hoje"),
            (COR["concluida"], "#86efac", "✓ Tarefa Concluída"),
            (COR["livre"], "#cbd5e1", "🏖 Dia Livre (Folga)"),
            (COR["alterada"], "#fcd34d", "🔄 Realocada por Imprevisto"),
            (COR["conflito"], "#fca5a5", "⚠ Choque com Aula/Trabalho"),
        ]
        for cor, borda, texto in itens_legenda:
            pilula = tk.Frame(legenda, bg=cor, highlightbackground=borda, highlightthickness=1, padx=8, pady=2)
            pilula.pack(side="left", padx=4)
            tk.Label(pilula, text=texto, font=FONTE_PEQUENA, bg=cor, fg=COR["texto"]).pack()

        tk.Label(
            legenda,
            text="Dica: Clique em qualquer quadrado da tabela para lançar um imprevisto ou migué direto para aquela pessoa.",
            font=FONTE_PEQUENA,
            bg=COR["bg_card"],
            fg=COR["texto_sec"],
        ).pack(side="right")

    def _montar_aba_moradores(self):
        aba = tk.Frame(self.abas, bg=COR["bg_card"], padx=14, pady=12)
        self.abas.add(aba, text=" 👥 Moradores & Divisão de Esforço ")

        topo_m = tk.Frame(aba, bg=COR["bg_card"])
        topo_m.pack(fill="x", pady=(0, 8))
        self.info_fonte = tk.StringVar()
        tk.Label(topo_m, textvariable=self.info_fonte, font=FONTE_NEGRITO, bg=COR["bg_card"], fg=COR["texto"]).pack(
            side="left"
        )
        tk.Label(
            topo_m,
            text="Veja abaixo se o peso das tarefas está justo para todo mundo e quantas doses de pinga cada um deve:",
            font=FONTE,
            bg=COR["bg_card"],
            fg=COR["texto_sec"],
        ).pack(side="right")

        colunas = {
            "nome": 120,
            "cargo": 95,
            "livres": 120,
            "preferidos": 120,
            "tarefas": 115,
            "esforco": 170,
            "pinga": 110,
            "situacao": 240,
        }
        titulos = [
            "Morador",
            "Hierarquia",
            "Dias de Folga",
            "Dias que Prefere",
            "Tarefas (Feitas)",
            "Termômetro de Esforço",
            "🥃 Dívida Pinga",
            "Situação na Semana (Penalidades)",
        ]
        quadro_tab = tk.Frame(aba, bg=COR["borda"], bd=1, relief="solid")
        quadro_tab.pack(fill="x", pady=(0, 14))

        self.tabela_integrantes = ttk.Treeview(quadro_tab, columns=list(colunas.keys()), show="headings", height=8)
        for (coluna, largura), titulo in zip(colunas.items(), titulos):
            self.tabela_integrantes.heading(coluna, text=titulo)
            self.tabela_integrantes.column(coluna, width=largura, anchor="w")
        self.tabela_integrantes.pack(fill="x")

        quadro_justica = ttk.LabelFrame(
            aba, text=" 📊 Balanço da Casa — Por que a escala ficou assim? ", padding=12
        )
        quadro_justica.pack(fill="both", expand=True)
        self.info_justica_humana = tk.StringVar()
        tk.Label(
            quadro_justica,
            textvariable=self.info_justica_humana,
            justify="left",
            font=("Segoe UI", 10),
            bg=COR["bg_card"],
            fg=COR["texto"],
        ).pack(anchor="w")

    def _montar_aba_pingometro(self):
        aba = tk.Frame(self.abas, bg=COR["bg_card"], padx=14, pady=12)
        self.abas.add(aba, text=" 🥃 Punições (Pingômetro) ")

        topo_p = tk.Frame(aba, bg="#fffbeb", highlightbackground="#fde68a", highlightthickness=1, padx=14, pady=10)
        topo_p.pack(fill="x", pady=(0, 12))

        esq_p = tk.Frame(topo_p, bg="#fffbeb")
        esq_p.pack(side="left")
        tk.Label(
            esq_p,
            text="🥃 Regra da República: Deu migué na tarefa = +1 Dose de Pinga!",
            font=FONTE_NEGRITO,
            bg="#fffbeb",
            fg=COR["pinga"],
        ).pack(anchor="w")
        tk.Label(
            esq_p,
            text="As tarefas não realizadas são realocadas automaticamente pela Busca Online e geram 1 dose de multa para o responsável original.",
            font=FONTE,
            bg="#fffbeb",
            fg=COR["texto_sec"],
        ).pack(anchor="w")

        dir_p = tk.Frame(topo_p, bg="#fffbeb")
        dir_p.pack(side="right")
        ttk.Button(
            dir_p,
            text="🥃 Virar 1 Dose (Pagar Selecionado)",
            style="Sucesso.TButton",
            command=self.pagar_dose_selecionada,
        ).pack(side="left", padx=4)
        ttk.Button(
            dir_p,
            text="➕ Multa Avulsa (+1 Dose)",
            style="Alerta.TButton",
            command=self.adicionar_multa_avulsa,
        ).pack(side="left", padx=4)
        ttk.Button(
            dir_p,
            text="📤 Exportar Pingômetro (CSV)",
            command=self.exportar_pingometro_csv,
        ).pack(side="left", padx=4)

        corpo_p = tk.Frame(aba, bg=COR["bg_card"])
        corpo_p.pack(fill="both", expand=True)

        quadro_rank = ttk.LabelFrame(
            corpo_p, text=" 🏆 Ranking do Pingômetro (Selecione um morador para pagar dose) ", padding=8
        )
        quadro_rank.pack(side="left", fill="both", expand=True, padx=(0, 6))

        col_rank = {"morador": 130, "cargo": 95, "pendentes": 130, "pagas": 110, "barometro": 160}
        tit_rank = ["Morador", "Hierarquia", "Doses a Pagar", "Doses Viradas", "Status"]
        self.tabela_ranking_pinga = ttk.Treeview(quadro_rank, columns=list(col_rank.keys()), show="headings", height=10)
        for (c, larg), tit in zip(col_rank.items(), tit_rank):
            self.tabela_ranking_pinga.heading(c, text=tit)
            self.tabela_ranking_pinga.column(c, width=larg, anchor="w")
        self.tabela_ranking_pinga.pack(fill="both", expand=True)

        self.lbl_resumo_pinga = tk.StringVar()
        tk.Label(
            quadro_rank,
            textvariable=self.lbl_resumo_pinga,
            font=FONTE_NEGRITO,
            bg=COR["bg_card"],
            fg=COR["pinga"],
            pady=6,
        ).pack(anchor="w")

        quadro_hist = ttk.LabelFrame(
            corpo_p, text=" 📜 Livro Negro da Cachaça (Histórico de Migués e Infrações) ", padding=8
        )
        quadro_hist.pack(side="right", fill="both", expand=True, padx=(6, 0))

        col_hist = {"id": 45, "dia": 80, "morador": 110, "motivo": 230, "status": 110}
        tit_hist = ["#", "Dia", "Infrator", "Motivo da Punição", "Status"]
        self.tabela_hist_pinga = ttk.Treeview(quadro_hist, columns=list(col_hist.keys()), show="headings", height=10)
        for (c, larg), tit in zip(col_hist.items(), tit_hist):
            self.tabela_hist_pinga.heading(c, text=tit)
            self.tabela_hist_pinga.column(c, width=larg, anchor="w")
        self.tabela_hist_pinga.pack(fill="both", expand=True)

    def _montar_aba_mural(self):
        aba = tk.Frame(self.abas, bg=COR["bg_card"], padx=14, pady=12)
        self.abas.add(aba, text=" 💬 Mural de Avisos & Trocas ")

        topo_log = tk.Frame(aba, bg=COR["bg_card"])
        topo_log.pack(fill="x", pady=(0, 8))
        tk.Label(
            topo_log,
            text="Tudo o que rolou na semana (quem deu baixa, tarefas extras pós-rock, multas de pinga e quem assumiu o quê):",
            font=FONTE,
            bg=COR["bg_card"],
            fg=COR["texto_sec"],
        ).pack(side="left")

        quadro_log = tk.Frame(aba, bg="#0f172a", bd=1, relief="solid")
        quadro_log.pack(fill="both", expand=True)

        self.log = tk.Text(
            quadro_log,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#e2e8f0",
            padx=14,
            pady=14,
            borderwidth=0,
            state="disabled",
        )
        self.log.tag_configure("destaque", foreground="#38bdf8", font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("imprevisto", foreground="#fbbf24", font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("mudanca", foreground="#4ade80")
        self.log.tag_configure("erro", foreground="#f87171", font=("Segoe UI", 10, "bold"))

        rolagem = ttk.Scrollbar(quadro_log, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=rolagem.set)
        self.log.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

    def _montar_aba_professor(self):
        aba = tk.Frame(self.abas, bg=COR["bg_card"], padx=14, pady=12)
        self.abas.add(aba, text=" ⚙️ Bastidores (Métricas de IA) ")

        tk.Label(
            aba,
            text="Painel Técnico para Avaliação Acadêmica (UFOP — Inteligência Artificial): Busca Clássica (A* vs UCS), Busca Local (SA) e Função de Custo.",
            font=FONTE_NEGRITO,
            bg=COR["bg_card"],
            fg=COR["primaria"],
        ).pack(anchor="w", pady=(0, 8))

        quadro_grade = tk.Frame(aba, bg=COR["borda"], bd=1, relief="solid")
        quadro_grade.pack(fill="x", pady=(0, 10))
        self.grade_plano = tk.Frame(quadro_grade, bg=COR["borda"])
        self.grade_plano.pack(fill="x")

        div_inf = tk.Frame(aba, bg=COR["bg_card"])
        div_inf.pack(fill="both", expand=True)

        esq = ttk.LabelFrame(div_inf, text=" 1. Busca Clássica: A* com Heurística Admissível vs UCS ", padding=8)
        esq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        colunas = {"tarefa": 180, "vezes": 55, "horarios": 230, "custo": 65, "astar": 90, "ucs": 90}
        titulos = ["Tarefa", "Vezes", "Horários (A*)", "Custo", "Nós A*", "Nós UCS"]
        self.tabela_plano = ttk.Treeview(esq, columns=list(colunas.keys()), show="headings", height=7)
        for (coluna, largura), titulo in zip(colunas.items(), titulos):
            self.tabela_plano.heading(coluna, text=titulo)
            self.tabela_plano.column(coluna, width=largura, anchor="w")
        self.tabela_plano.pack(fill="both", expand=True)

        self.info_plano = tk.StringVar()
        tk.Label(esq, textvariable=self.info_plano, font=FONTE_PEQUENA, bg=COR["bg_card"], fg=COR["texto_sec"]).pack(
            anchor="w", pady=(4, 0)
        )

        dir_sa = ttk.LabelFrame(
            div_inf, text=" 2. Busca Local (Guloso + Simulated Annealing) & Pesos ", padding=8
        )
        dir_sa.pack(side="right", fill="both", expand=True, padx=(6, 0))
        self.info_local = tk.StringVar()
        tk.Label(
            dir_sa,
            textvariable=self.info_local,
            justify="left",
            font=("Consolas", 9),
            bg=COR["bg_card"],
            fg=COR["texto"],
        ).pack(anchor="w")

    # ------------------------------------------------------------ acoes e eventos

    def nova_escala(self, dia):
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            self.plano = planejar_semana(self.integrantes, self.tarefas)
            self.resultado = gerar_escala(self.integrantes, self.tarefas, self.plano.horarios)
        finally:
            self.configure(cursor="")

        self.agente = AgenteOnline(self.integrantes, self.tarefas, self.resultado.estado, dia)
        self.concluidas.clear()

        for k, a in enumerate(self.agente.estado):
            if a is not None and a[2] < dia:
                self.concluidas.add(k)

        self._log(
            f"📅 [{DIAS[dia]}] Nova escala da semana montada e organizada para {len(self.integrantes)} moradores!",
            "destaque",
        )
        self.atualizar()

    def _aplicar_multa_pinga(self, integrante_idx, dia, motivo):
        nova = MultaPinga(self._seq_multa, integrante_idx, dia, motivo, 1, False)
        self._seq_multa += 1
        self.multas.append(nova)
        nome_p = self.agente.integrantes[integrante_idx].nome
        self._log(
            f"🥃 [PINGÔMETRO] {nome_p} tomou +1 dose de pinga de multa! Motivo: {motivo}.",
            "erro",
        )

    def pagar_dose_selecionada(self):
        selecao_hist = self.tabela_hist_pinga.selection()
        if selecao_hist:
            valores = self.tabela_hist_pinga.item(selecao_hist[0], "values")
            id_alvo = int(valores[0])
            for m in self.multas:
                if m.id_multa == id_alvo and not m.paga:
                    m.paga = True
                    nome_p = self.agente.integrantes[m.integrante].nome
                    self._log(
                        f"🥃🎉 [{DIAS[self.agente.dia_atual]}] {nome_p} virou 1 dose de pinga e quitou: \"{m.motivo}\"!",
                        "mudanca",
                    )
                    self.atualizar()
                    return

        selecao_rank = self.tabela_ranking_pinga.selection()
        if not selecao_rank:
            messagebox.showinfo(
                "Virar Dose de Pinga",
                "Selecione um morador na tabela do Ranking (ou uma multa específica no Histórico ao lado) para confirmar que ele virou a dose!",
            )
            return

        nome_sel = self.tabela_ranking_pinga.item(selecao_rank[0], "values")[0]
        for m in self.multas:
            if self.agente.integrantes[m.integrante].nome == nome_sel and not m.paga:
                m.paga = True
                self._log(
                    f"🥃🎉 [{DIAS[self.agente.dia_atual]}] {nome_sel} virou 1 dose de pinga na frente da galera! (Quitou: {m.motivo})",
                    "mudanca",
                )
                self.atualizar()
                return

        messagebox.showinfo("Tudo Quitado!", f"{nome_sel} não está devendo nenhuma dose de pinga no momento!")

    def adicionar_multa_avulsa(self):
        DialogoMultaAvulsa(self)

    def exportar_pingometro_csv(self):
        if not self.multas:
            messagebox.showinfo("Exportar Pingômetro", "Ainda não há nenhuma multa registrada nesta semana!")
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar Planilha do Pingômetro",
            defaultextension=".csv",
            initialfile="pingometro_republica.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not caminho:
            return
        with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
            esc = csv.writer(f)
            esc.writerow(["ID", "Morador", "Hierarquia", "Dia", "Motivo", "Doses", "Status"])
            for m in self.multas:
                p = self.agente.integrantes[m.integrante]
                status_txt = "Paga (Virou)" if m.paga else "Pendente"
                esc.writerow([m.id_multa, p.nome, p.cargo, DIAS[m.dia], m.motivo, m.doses, status_txt])
        messagebox.showinfo("Exportado com Sucesso", f"Relatório do Pingômetro salvo em:\n{caminho}")

    def marcar_feita(self, k):
        if k in self.agente.nao_realizadas:
            return
        t, i, d, _ = self.agente.estado[k]
        nome_t = self.agente.tarefas[t].nome
        nome_p = self.agente.integrantes[i].nome
        if k in self.concluidas:
            self.concluidas.remove(k)
            self._log(f"↩ [{DIAS[d]}] {nome_p} desmarcou \"{nome_t}\" como concluída.")
        else:
            self.concluidas.add(k)
            self._log(f"✅ [{DIAS[d]}] Boa! {nome_p} concluiu a tarefa \"{nome_t}\".", "mudanca")
        self.atualizar()

    def reportar_migue_direto(self, k):
        if k in self.agente.nao_realizadas:
            return
        t, i, d, _ = self.agente.estado[k]
        nome_t = self.agente.tarefas[t].nome
        nome_p = self.agente.integrantes[i].nome
        confirmou = messagebox.askyesno(
            "Confirmar Migué (+1 Dose de Pinga 🥃)",
            f"{nome_p} realmente não fez \"{nome_t}\" hoje?\n\n"
            f"• O sistema vai realocar essa tarefa automaticamente (Busca Online).\n"
            f"• {nome_p} vai receber +1 DOSE DE PINGA de multa no Pingômetro!",
        )
        if not confirmou:
            return
        if k in self.concluidas:
            self.concluidas.remove(k)
        imp = Imprevisto("nao_realizada", d, ocorrencia=k)
        self.registrar_imprevisto(imp)

    def regerar(self):
        if self.agente.historico:
            confirmou = messagebox.askyesno(
                "Sortear nova escala", "As trocas desta semana serão zeradas. Quer gerar outra escala do zero?"
            )
            if not confirmou:
                return
        self.nova_escala(self.agente.dia_atual)

    def avancar_dia(self):
        if self.agente.dia_atual == 6:
            self._log("─── Domingou! Virando a folha para uma nova semana ───", "destaque")
            self._nova_semana(0)
            return
        for k, a in enumerate(self.agente.estado):
            if a is not None and a[2] == self.agente.dia_atual and k not in self.agente.nao_realizadas:
                self.concluidas.add(k)
        self.agente.dia_atual += 1
        self._log(f"☀️ [{DIAS[self.agente.dia_atual]}] Bom dia! Começando as tarefas de {DIAS[self.agente.dia_atual]}.")
        self.atualizar()

    def _verificar_data(self):
        self._sincronizar_data()
        self.after(60000, self._verificar_data)

    def _sincronizar_data(self):
        """Avança a escala pelos dias que passaram desde a última vez (inclusive com
        o programa fechado). Se a semana virou nesse meio-tempo, monta a semana nova
        já no dia da semana de hoje."""
        hoje = dt.date.today()
        dias_passados = (hoje - self.data_real).days
        if dias_passados <= 0:
            return
        self.data_real = hoje
        if self.agente.dia_atual + dias_passados > 6:
            self._log(
                f"─── A semana virou ({dias_passados} dia(s) desde o último acesso). Montando a semana nova ───",
                "destaque",
            )
            self._nova_semana(hoje.weekday())
            return
        for _ in range(dias_passados):
            self.avancar_dia()

    def _nova_semana(self, dia):
        """Relê o Forms (se os horários vieram de lá) e monta a escala da nova semana."""
        self._reler_forms()
        self.nova_escala(dia)

    def _reler_forms(self):
        tipo, ref = self.origem.get("tipo"), self.origem.get("ref")
        if tipo not in ("csv", "sheets") or not ref:
            return
        try:
            if tipo == "csv":
                integrantes, avisos = dados.carregar_forms_arquivo(ref)
            else:
                integrantes, avisos = dados.carregar_forms_google_sheets(ref)
        except Exception as erro:
            self._log(
                f"⚠ Não deu para reler o Forms na virada da semana ({erro}). Mantendo os horários anteriores.",
                "erro",
            )
            return
        self._remapear_multas(integrantes)
        self.integrantes = integrantes
        self._log(f"📥 Respostas do Forms relidas para a nova semana ({len(integrantes)} moradores).", "destaque")
        for aviso in avisos:
            self._log(f"  ⚠ Atenção na regra da casa: {aviso}", "imprevisto")

    def _remapear_multas(self, novos):
        """As multas guardam a posição do morador na lista; ao reler o Forms a
        ordem pode mudar, então elas são reassociadas pelo nome."""
        posicao = {p.nome.strip().casefold(): i for i, p in enumerate(novos)}
        mantidas, saiu = [], set()
        for m in self.multas:
            nome = self.integrantes[m.integrante].nome
            j = posicao.get(nome.strip().casefold())
            if j is None:
                saiu.add(nome)
                continue
            m.integrante = j
            mantidas.append(m)
        self.multas = mantidas
        for nome in sorted(saiu):
            self._log(f"  🚪 {nome} não está mais nas respostas do Forms; as multas dele foram retiradas.")

    def usar_simulados(self):
        self.multas.clear()
        self._usar_integrantes(dados.integrantes_simulados(), [], "Dados de Exemplo", {"tipo": "simulado"})

    def importar_csv(self):
        caminho = filedialog.askopenfilename(
            title="Respostas do Google Forms (CSV)", filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")]
        )
        if not caminho:
            return
        try:
            integrantes, avisos = dados.carregar_forms_arquivo(caminho)
        except Exception as erro:
            messagebox.showerror("Erro ao ler o CSV", str(erro))
            return
        self.multas.clear()
        nome_arq = caminho.split("/")[-1]
        self._usar_integrantes(
            integrantes, avisos, f"Forms ({nome_arq})", {"tipo": "csv", "ref": os.path.abspath(caminho)}
        )

    def importar_sheets(self):
        url = simpledialog.askstring(
            "Conectar Planilha Google",
            "Cole o link da planilha de respostas do Forms da República\n"
            "(deve estar como \"Qualquer pessoa com o link pode ver\"):",
            parent=self,
        )
        if not url:
            return
        try:
            integrantes, avisos = dados.carregar_forms_google_sheets(url.strip())
        except Exception as erro:
            messagebox.showerror("Erro ao ler a planilha", str(erro))
            return
        self.multas.clear()
        self._usar_integrantes(
            integrantes, avisos, "Planilha Online da República", {"tipo": "sheets", "ref": url.strip()}
        )

    def _usar_integrantes(self, integrantes, avisos, fonte, origem):
        self.integrantes = integrantes
        self.fonte = fonte
        self.origem = origem
        self._log(f"📥 Horários atualizados via {fonte} ({len(integrantes)} moradores).", "destaque")
        for aviso in avisos:
            self._log(f"  ⚠ Atenção na regra da casa: {aviso}", "imprevisto")
        if avisos:
            messagebox.showwarning("Regra de Hierarquia", "\n".join(avisos))
        self.nova_escala(self.agente.dia_atual)

    def registrar_imprevisto(self, imp):
        ag = self.agente
        descricao = imp.descricao(ag)

        # Se a tarefa nao foi feita, anota 1 dose de pinga pro responsavel antes de replanejar
        if imp.tipo == "nao_realizada" and imp.ocorrencia is not None:
            # Vale para qualquer origem (botão "Não fez", janela de imprevisto ou
            # "Simular B.O."): se a tarefa estava marcada como feita, deixa de estar.
            self.concluidas.discard(imp.ocorrencia)
            t_orig, i_orig, d_orig, _ = ag.estado[imp.ocorrencia]
            nome_tarefa = ag.tarefas[t_orig].nome
            self._aplicar_multa_pinga(i_orig, d_orig, f"Deu migué em: {nome_tarefa}")

        mudancas = ag.registrar(imp, self.rng)
        self._log(f"⚡ [{DIAS[ag.dia_atual]}] Imprevisto na casa: {descricao}", "imprevisto")
        if not mudancas:
            self._log("   ✓ Tudo certo! Ninguém precisou trocar de tarefa.")
        for m in mudancas:
            self._log("   🔄 " + self._descrever_mudanca(m), "mudanca")

        sem_responsavel = 0
        for a in ag.estado:
            if a is None:
                sem_responsavel += 1
        if sem_responsavel > 0:
            self._log(f"   🚨 {sem_responsavel} tarefa(s) ficaram sem ninguém livre!", "erro")
        self.atualizar()

    def imprevisto_aleatorio(self):
        imp = self.agente.imprevisto_aleatorio(self.rng)
        self.registrar_imprevisto(imp)

    # ------------------------------------------------------------ atualizacao da tela

    def atualizar(self):
        self._desenhar_checkin_hoje()
        self._desenhar_escala()
        self._atualizar_integrantes()
        self._atualizar_pingometro()
        self._atualizar_aba_professor()

        ag = self.agente
        comp = ProblemaEscala(ag.integrantes, ag.tarefas).componentes(ag.estado)

        custo = 0
        for k, v in comp.items():
            custo += PESOS[k] * v

        rigidas = int(comp["indisponivel"] + comp["dia_repetido"])

        tarefas_hoje = []
        feitas_hoje = []
        for k, a in enumerate(ag.estado):
            if a is not None and a[2] == ag.dia_atual:
                tarefas_hoje.append(k)
                if k in self.concluidas:
                    feitas_hoje.append(k)

        doses_pendentes = 0
        for m in self.multas:
            if not m.paga:
                doses_pendentes += m.doses

        if rigidas > 0:
            clima_txt = "⚠ Sobrecarga"
            clima_cor = COR["perigo"]
        elif custo <= 35:
            clima_txt = "✨ Paz na Casa"
            clima_cor = COR["sucesso"]
        elif custo <= 90:
            clima_txt = "👍 Bem Dividido"
            clima_cor = COR["primaria"]
        else:
            clima_txt = "🔥 Semana Puxada"
            clima_cor = COR["aviso"]

        self.kpi_dia.configure(text=DIAS[ag.dia_atual], fg=COR["primaria"])
        self.kpi_clima.configure(text=clima_txt, fg=clima_cor)

        cor_tar = COR["sucesso"] if (len(feitas_hoje) == len(tarefas_hoje) and len(tarefas_hoje) > 0) else COR["texto"]
        self.kpi_tarefas.configure(text=f"{len(feitas_hoje)}/{len(tarefas_hoje)} feitas", fg=cor_tar)

        cor_pin = COR["pinga"] if doses_pendentes > 0 else COR["sucesso"]
        self.kpi_pinga.configure(text=f"{doses_pendentes} dose(s)", fg=cor_pin)

        # Toda ação passa por aqui, então salvar aqui mantém o arquivo sempre em dia.
        self._salvar()

    # ------------------------------------------------------------ salvar / recuperar

    def _estado_para_salvar(self):
        return {
            "data_real": self.data_real.isoformat(),
            "fonte": self.fonte,
            "origem": self.origem,
            "integrantes": [persistencia.integrante_para_dict(p) for p in self.integrantes],
            "tarefas": [persistencia.tarefa_para_dict(t) for t in self.tarefas],
            "plano": persistencia.plano_para_dict(self.plano),
            "resultado": persistencia.resultado_para_dict(self.resultado),
            "agente": persistencia.agente_para_dict(self.agente),
            "concluidas": sorted(self.concluidas),
            "multas": [vars(m) for m in self.multas],
            "seq_multa": self._seq_multa,
            "log": self._entradas_log[-MAX_LINHAS_LOG_SALVAS:],
        }

    def _salvar(self):
        if self.arquivo_estado is None or self.agente is None:
            return
        try:
            persistencia.salvar(self._estado_para_salvar(), self.arquivo_estado)
            self._erro_ao_salvar = False
        except Exception as erro:
            if not self._erro_ao_salvar:  # avisa uma vez só, não a cada clique
                self._erro_ao_salvar = True
                self._log(f"⚠ Não deu para salvar a escala em {self.arquivo_estado}: {erro}", "erro")

    def _restaurar(self, e):
        # Converte tudo primeiro; só mexe no painel se nada deu erro.
        integrantes = [persistencia.integrante_de_dict(x) for x in e["integrantes"]]
        tarefas = [persistencia.tarefa_de_dict(x) for x in e["tarefas"]]
        plano = persistencia.plano_de_dict(e["plano"])
        resultado = persistencia.resultado_de_dict(e["resultado"])
        agente = persistencia.agente_de_dict(e["agente"])
        multas = [MultaPinga(**m) for m in e["multas"]]
        data_real = dt.date.fromisoformat(e["data_real"])

        self.integrantes, self.tarefas = integrantes, tarefas
        self.plano, self.resultado, self.agente = plano, resultado, agente
        self.multas, self._seq_multa = multas, e["seq_multa"]
        self.concluidas = set(e["concluidas"])
        self.fonte, self.origem = e["fonte"], e["origem"]
        self.data_real = data_real
        for texto, tag in e.get("log", []):
            self._log(texto, tag)
        self._log(f"💾 Escala recuperada do arquivo salvo (último acesso em {data_real:%d/%m/%Y}).", "destaque")
        self.atualizar()

    def _fechar(self):
        self._salvar()
        self.destroy()

    def _desenhar_checkin_hoje(self):
        for w in self.container_checkin.winfo_children():
            w.destroy()

        ag = self.agente
        hoje = ag.dia_atual
        self.lbl_titulo_hoje.configure(
            text=f"📌 Tarefas de Hoje ({DIAS[hoje]}) — Confirme o que foi feito ou marque 'Não fez' (+1 dose de pinga 🥃):"
        )

        do_dia = []
        for k, a in enumerate(ag.estado):
            if a is not None and a[2] == hoje:
                do_dia.append((a[3], k, a[0], a[1]))
        do_dia.sort()

        if not do_dia:
            tk.Label(
                self.container_checkin,
                text="🎉 Nenhuma tarefa agendada para hoje! Dia tranquilo na república.",
                font=FONTE,
                bg="#f8fafc",
                fg=COR["texto_sec"],
            ).pack(anchor="w")
            return

        for s, k, t, i in do_dia:
            tarefa = ag.tarefas[t]
            pessoa = ag.integrantes[i]
            feita = k in self.concluidas
            nao_feita = k in ag.nao_realizadas

            if feita:
                bg_card = COR["concluida"]
                borda_card = "#86efac"
            elif nao_feita:
                bg_card = COR["conflito"]
                borda_card = "#fca5a5"
            else:
                bg_card = "white"
                borda_card = COR["borda"]

            card = tk.Frame(
                self.container_checkin,
                bg=bg_card,
                highlightbackground=borda_card,
                highlightthickness=1,
                padx=10,
                pady=6,
            )
            card.pack(side="left", padx=(0, 8), pady=2)

            icone_extra = "★ " if tarefa.extra else ""
            tk.Label(
                card,
                text=f"{TURNOS[s].upper()}  •  {pessoa.nome}",
                font=FONTE_PEQUENA,
                bg=bg_card,
                fg=COR["texto_sec"],
            ).pack(anchor="w")

            tk.Label(
                card,
                text=f"{icone_extra}{tarefa.nome}",
                font=FONTE_NEGRITO,
                bg=bg_card,
                fg=COR["texto"],
            ).pack(anchor="w", pady=(0, 4))

            barra_btn = tk.Frame(card, bg=bg_card)
            barra_btn.pack(anchor="w")

            if nao_feita:
                tk.Label(
                    barra_btn,
                    text="🥃 Migué (+1 dose aplicada)",
                    font=FONTE_PEQUENA,
                    bg=bg_card,
                    fg=COR["perigo"],
                ).pack(side="left")
            else:
                txt_feito = "✓ Concluída (Desfazer)" if feita else "✓ Feito"
                cor_btn_f = COR["sucesso"] if not feita else "#64748b"
                btn_ok = tk.Button(
                    barra_btn,
                    text=txt_feito,
                    font=FONTE_PEQUENA,
                    bg=cor_btn_f,
                    fg="white",
                    activebackground="#15803d",
                    activeforeground="white",
                    relief="flat",
                    padx=6,
                    pady=1,
                    cursor="hand2",
                    command=lambda occ=k: self.marcar_feita(occ),
                )
                btn_ok.pack(side="left", padx=(0, 4))

                if not feita:
                    btn_migue = tk.Button(
                        barra_btn,
                        text="✗ Não fez (🥃)",
                        font=FONTE_PEQUENA,
                        bg="#fee2e2",
                        fg=COR["perigo"],
                        activebackground="#fecaca",
                        activeforeground=COR["perigo"],
                        relief="flat",
                        padx=6,
                        pady=1,
                        cursor="hand2",
                        command=lambda occ=k: self.reportar_migue_direto(occ),
                    )
                    btn_migue.pack(side="left")

    def _desenhar_escala(self):
        for w in self.grade.winfo_children():
            w.destroy()
        ag = self.agente
        hoje = ag.dia_atual

        hdr_morador = tk.Label(
            self.grade,
            text="MORADOR",
            bg=COR["cabecalho"],
            fg="white",
            font=FONTE_NEGRITO,
            anchor="w",
            padx=12,
            pady=10,
        )
        hdr_morador.grid(row=0, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))

        for d in range(7):
            eh_hoje = d == hoje
            texto_dia = f"{DIAS[d].upper()}  •  HOJE" if eh_hoje else DIAS[d].upper()
            bg_hdr = COR["cabecalho_hoje"] if eh_hoje else COR["cabecalho"]
            tk.Label(
                self.grade,
                text=texto_dia,
                bg=bg_hdr,
                fg="white",
                font=FONTE_NEGRITO,
                anchor="w",
                padx=10,
                pady=10,
            ).grid(row=0, column=d + 1, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.grade.columnconfigure(d + 1, weight=1, uniform="dia")

        por_celula = {}
        for k, a in enumerate(ag.estado):
            if a is not None:
                t, i, d, s = a
                chave = (i, d)
                if chave not in por_celula:
                    por_celula[chave] = []
                por_celula[chave].append((s, k, t))

        for i, pessoa in enumerate(ag.integrantes):
            bg_linha = COR["celula"] if i % 2 == 0 else COR["celula_alt"]

            doses_p = 0
            for m in self.multas:
                if m.integrante == i and not m.paga:
                    doses_p += m.doses

            quadro_pessoa = tk.Frame(self.grade, bg=bg_linha, padx=12, pady=8)
            quadro_pessoa.grid(row=i + 1, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            tk.Label(quadro_pessoa, text=pessoa.nome, font=FONTE_NEGRITO, bg=bg_linha, fg=COR["texto"]).pack(anchor="w")
            tk.Label(quadro_pessoa, text=pessoa.cargo, font=FONTE_PEQUENA, bg=bg_linha, fg=COR["texto_sec"]).pack(
                anchor="w"
            )
            if doses_p > 0:
                tk.Label(
                    quadro_pessoa,
                    text=f"🥃 Deve {doses_p} dose(s)",
                    font=FONTE_PEQUENA,
                    bg=bg_linha,
                    fg=COR["pinga"],
                ).pack(anchor="w", pady=(2, 0))

            for d in range(7):
                tarefas_celula = sorted(por_celula.get((i, d), []))

                conflito = False
                alterada = False
                todas_feitas = len(tarefas_celula) > 0
                for s, k, _ in tarefas_celula:
                    if not pessoa.disponivel(d, s):
                        conflito = True
                    if k in ag.alteradas:
                        alterada = True
                    if k not in self.concluidas:
                        todas_feitas = False

                if conflito:
                    bg = COR["conflito"]
                elif todas_feitas and d == hoje:
                    bg = COR["concluida"]
                elif alterada:
                    bg = COR["alterada"]
                elif d in pessoa.dias_livres:
                    bg = COR["livre"]
                elif d == hoje:
                    bg = COR["coluna_hoje"]
                else:
                    bg = bg_linha

                fg_principal = COR["passado"] if d < hoje else COR["texto"]

                cel = tk.Frame(self.grade, bg=bg, padx=8, pady=6, cursor="hand2")
                cel.grid(row=i + 1, column=d + 1, sticky="nsew", padx=(0, 1), pady=(0, 1))

                acao_clique = lambda _e, dia_c=d, int_c=i: DialogoImprevisto(
                    self, dia_inicial=dia_c, integrante_inicial=int_c
                )
                cel.bind("<Button-1>", acao_clique)

                if d in pessoa.dias_livres:
                    lbl_livre = tk.Label(
                        cel, text="🏖 Dia Livre", font=FONTE_PEQUENA, bg=bg, fg=COR["livre_texto"], anchor="w"
                    )
                    lbl_livre.pack(anchor="w", pady=(0, 2))
                    lbl_livre.bind("<Button-1>", acao_clique)

                for s, k, t in tarefas_celula:
                    tarefa = ag.tarefas[t]
                    feita = k in self.concluidas
                    nao_feita = k in ag.nao_realizadas

                    if nao_feita:
                        marca = "🥃✗ "
                        cor_item = COR["perigo"]
                    elif feita:
                        marca = "✓ "
                        cor_item = COR["concluida_texto"] if d >= hoje else fg_principal
                    elif tarefa.extra:
                        marca = "★ "
                        cor_item = fg_principal
                    else:
                        marca = ""
                        cor_item = fg_principal

                    if tarefa.extra or k in ag.alteradas or d == hoje:
                        fonte_item = FONTE_NEGRITO
                    else:
                        fonte_item = FONTE

                    lbl_t = tk.Label(
                        cel,
                        text=f"[{TURNOS[s][0]}] {marca}{tarefa.nome}",
                        font=fonte_item,
                        bg=bg,
                        fg=cor_item,
                        justify="left",
                        anchor="w",
                        wraplength=165,
                    )
                    lbl_t.pack(anchor="w", pady=1)
                    if d == hoje and not nao_feita:
                        lbl_t.bind("<Button-1>", lambda _e, occ=k: self.marcar_feita(occ))
                    else:
                        lbl_t.bind("<Button-1>", acao_clique)

                ocupados = []
                for s in range(3):
                    if (d, s) in pessoa.ocupados:
                        ocupados.append(TURNOS[s][0])
                if ocupados and d not in pessoa.dias_livres:
                    lbl_oc = tk.Label(
                        cel,
                        text=f"Aula/Trab: {', '.join(ocupados)}",
                        font=FONTE_PEQUENA,
                        bg=bg,
                        fg=COR["passado"] if d < hoje else COR["texto_sec"],
                        anchor="w",
                    )
                    lbl_oc.pack(anchor="w", pady=(3, 0))
                    lbl_oc.bind("<Button-1>", acao_clique)

    def _atualizar_integrantes(self):
        ag = self.agente
        self.info_fonte.set(f"Horários ativos: {self.fonte} ({len(ag.integrantes)} moradores na casa)")
        self.tabela_integrantes.delete(*self.tabela_integrantes.get_children())

        esforcos = []
        for idx in range(len(ag.integrantes)):
            pts = 0
            for a in ag.estado:
                if a is not None and a[1] == idx:
                    pts += ag.tarefas[a[0]].esforco
            esforcos.append(pts)

        media_esforco = sum(esforcos) / len(esforcos) if esforcos else 1.0
        max_esforco = max(esforcos + [10])

        pares = list(enumerate(ag.integrantes))
        pares.sort(key=lambda par: -par[1].hierarquia)

        for i, p in pares:
            minhas_idx = []
            minhas = []
            for k, a in enumerate(ag.estado):
                if a is not None and a[1] == i:
                    minhas_idx.append(k)
                    minhas.append(a)

            feitas_p = 0
            for k in minhas_idx:
                if k in self.concluidas:
                    feitas_p += 1

            doses_pendentes = 0
            for m in self.multas:
                if m.integrante == i and not m.paga:
                    doses_pendentes += m.doses

            pts = esforcos[i]
            blocos = round((pts / max_esforco) * 10)
            barra = "█" * blocos + "░" * (10 - blocos)

            choques_aula = 0
            fora_pref = 0
            for a in minhas:
                if not p.disponivel(a[2], a[3]):
                    choques_aula += 1
                if p.dias_preferidos and a[2] not in p.dias_preferidos:
                    fora_pref += 1

            avisos_pessoa = []
            if choques_aula > 0:
                avisos_pessoa.append(f"⚠ {choques_aula}x em horário ocupado")
            if doses_pendentes > 0:
                avisos_pessoa.append(f"🥃 Deve {doses_pendentes} dose(s)")
            if pts > media_esforco + 2.5:
                avisos_pessoa.append("🔥 Carga acima da média")
            elif pts < media_esforco - 2.5:
                avisos_pessoa.append("🍃 Carga leve")
            if fora_pref > 0:
                avisos_pessoa.append(f"{fora_pref}x fora do dia preferido")

            situacao_txt = "  •  ".join(avisos_pessoa) if avisos_pessoa else "✅ Sem conflitos"
            txt_pinga = f"🥃 {doses_pendentes} dose(s)" if doses_pendentes > 0 else "Zero"

            dias_livres_txt = ", ".join(DIAS[d] for d in sorted(p.dias_livres)) or "—"
            dias_pref_txt = ", ".join(DIAS[d] for d in sorted(p.dias_preferidos)) or "Qualquer dia"

            self.tabela_integrantes.insert(
                "",
                "end",
                values=(
                    p.nome,
                    p.cargo,
                    dias_livres_txt,
                    dias_pref_txt,
                    f"{feitas_p}/{len(minhas)} feitas",
                    f"{barra}  {pts} pts",
                    txt_pinga,
                    situacao_txt,
                ),
            )

        comp = ProblemaEscala(ag.integrantes, ag.tarefas).componentes(ag.estado)
        frases = [
            f"• Média de peso por morador nesta semana: {media_esforco:.1f} pontos de esforço.",
        ]
        for chave, descricao in NOMES_PENALIDADES_HUMANOS.items():
            val = comp[chave]
            if val > 0:
                frases.append(
                    f"• Atenção: {descricao} (impacto: {val:.1f} × peso {PESOS[chave]} = {val * PESOS[chave]:.0f} pts)"
                )
        if len(frases) == 1:
            frases.append("• ✨ Escala perfeita! Todas as preferências, dependências e horários foram 100% respeitados.")

        self.info_justica_humana.set("\n".join(frases))

    def _atualizar_pingometro(self):
        ag = self.agente
        self.tabela_ranking_pinga.delete(*self.tabela_ranking_pinga.get_children())
        self.tabela_hist_pinga.delete(*self.tabela_hist_pinga.get_children())

        dados_rank = []
        for i, p in enumerate(ag.integrantes):
            pend = 0
            pagas = 0
            for m in self.multas:
                if m.integrante == i:
                    if m.paga:
                        pagas += m.doses
                    else:
                        pend += m.doses
            dados_rank.append((pend, pagas, p))

        dados_rank.sort(key=lambda x: (-x[0], -x[1], -x[2].hierarquia))

        for pend, pagas, p in dados_rank:
            copos = "🥃" * min(pend, 8) + ("+" if pend > 8 else "")
            if pend == 0 and pagas == 0:
                status_etilico = "😇 Cumpre tudo"
            elif pend == 0:
                status_etilico = "✅ Quitou!"
            elif pend == 1:
                status_etilico = f"{copos} Médio"
            elif pend <= 3:
                status_etilico = f"{copos} Ruim"
            else:
                status_etilico = f"{copos} Péssimo!!"

            self.tabela_ranking_pinga.insert(
                "",
                "end",
                values=(
                    p.nome,
                    p.cargo,
                    f"{pend} dose(s)" if pend else "0",
                    f"{pagas} virada(s)" if pagas else "0",
                    status_etilico,
                ),
            )

        for m in reversed(self.multas):
            p = ag.integrantes[m.integrante]
            status_m = "✅ Paga / Virada" if m.paga else "🔥 Pendente (1 dose)"
            self.tabela_hist_pinga.insert(
                "",
                "end",
                values=(m.id_multa, DIAS[m.dia], p.nome, m.motivo, status_m),
            )

        tot_pend = 0
        tot_pagas = 0
        for m in self.multas:
            if m.paga:
                tot_pagas += m.doses
            else:
                tot_pend += m.doses

        self.lbl_resumo_pinga.set(
            f"Total na Semana:   {tot_pend} dose(s) na fila pra virar   •   {tot_pagas} dose(s) já pagas pela galera"
        )

    def _atualizar_aba_professor(self):
        ag = self.agente
        for w in self.grade_plano.winfo_children():
            w.destroy()

        def celula(linha, coluna, texto, bg, fg="white", fonte=FONTE_NEGRITO):
            tk.Label(
                self.grade_plano,
                text=texto,
                bg=bg,
                fg=fg,
                font=fonte,
                justify="left",
                anchor="nw",
                padx=8,
                pady=5,
                wraplength=165,
            ).grid(row=linha, column=coluna, sticky="nsew", padx=(0, 1), pady=(0, 1))

        celula(0, 0, "TURNO", COR["cabecalho"])
        for d in range(7):
            eh_hoje = d == ag.dia_atual
            celula(
                0,
                d + 1,
                f"{DIAS[d].upper()} (HOJE)" if eh_hoje else DIAS[d].upper(),
                COR["cabecalho_hoje"] if eh_hoje else COR["cabecalho"],
            )
            self.grade_plano.columnconfigure(d + 1, weight=1, uniform="dia")

        por_horario = {}
        for k, a in enumerate(ag.estado):
            if a is not None:
                tarefa = ag.tarefas[a[0]]
                if k in ag.nao_realizadas:
                    marca = "✗ "
                elif tarefa.extra:
                    marca = "★ "
                else:
                    marca = "• "
                chave = (a[2], a[3])
                if chave not in por_horario:
                    por_horario[chave] = []
                por_horario[chave].append(marca + tarefa.nome)

        for s in range(3):
            celula(s + 1, 0, TURNOS[s], COR["celula"], COR["texto"])
            for d in range(7):
                livres = 0
                for p in ag.integrantes:
                    if p.disponivel(d, s):
                        livres += 1
                lista_t = sorted(por_horario.get((d, s), []))
                texto = "\n".join(lista_t) + f"\n({livres} livres)"
                bg = COR["coluna_hoje"] if d == ag.dia_atual else COR["celula"]
                fg_c = COR["passado"] if d < ag.dia_atual else COR["texto"]
                celula(s + 1, d + 1, texto.strip(), bg, fg_c, FONTE_PEQUENA)

        self.tabela_plano.delete(*self.tabela_plano.get_children())
        for p in self.plano.por_tarefa:
            tarefa = self.tarefas[p.tarefa]
            horarios = ", ".join(f"{DIAS[d][:3]}-{TURNOS[s][0]}" for d, s in p.horarios)
            self.tabela_plano.insert(
                "",
                "end",
                values=(
                    tarefa.nome,
                    f"{tarefa.vezes_por_semana}x",
                    horarios,
                    f"{p.custo:.1f}",
                    p.nos_expandidos,
                    p.nos_sem_heuristica,
                ),
            )
        self.info_plano.set(
            f"Custo global da semana: {self.plano.custo_inicial:.1f} (1ª passada) → {self.plano.custo:.1f} "
            f"após {self.plano.rodadas} rodada(s) de refino\n"
            f"Nós A* (com h(n)) = {self.plano.nos_expandidos}  |  "
            f"Nós UCS (sem h(n)) = {self.plano.nos_sem_heuristica}  |  "
            f"Tempo = {self.plano.tempo * 1000:.1f} ms"
        )

        r = self.resultado
        comp_atual = ProblemaEscala(ag.integrantes, ag.tarefas).componentes(ag.estado)
        custo_atual = sum(PESOS[k] * v for k, v in comp_atual.items())
        linhas = [
            f"Custo Guloso Inicial: {r.custo_inicial:>7.0f}  |  Pós-Simulated Annealing: {r.custo:>7.0f}",
            f"Custo Atual (pós-imprevistos): {custo_atual:>7.0f}  ({r.iteracoes} iter, {r.tempo:.2f}s)",
            "─" * 62,
            f"{'Componente (Função Objetivo)':<42}{'Violação':>10}{'Peso':>10}",
            "─" * 62,
        ]
        for chave, desc in NOMES_PENALIDADES_HUMANOS.items():
            linhas.append(f"{desc[:40]:<42}{comp_atual[chave]:>10.1f}{PESOS[chave]:>10}")
        self.info_local.set("\n".join(linhas))

    def _descrever_mudanca(self, m):
        ag = self.agente

        def formatar(a):
            if a is None:
                return "ninguém"
            return f"{ag.integrantes[a[1]].nome} na {DIAS[a[2]]} ({TURNOS[a[3]].lower()})"

        aloc_base = m.depois if m.depois is not None else m.antes
        tarefa = ag.tarefas[aloc_base[0]]
        nome = ("★ " if tarefa.extra else "") + tarefa.nome
        if m.antes is None:
            return f"Nova tarefa \"{nome}\" ficou para {formatar(m.depois)}"
        return f"\"{nome}\" passou de {formatar(m.antes)} para {formatar(m.depois)}"

    def _log(self, texto, tag=None):
        self._entradas_log.append((texto, tag))
        if len(self._entradas_log) > 2 * MAX_LINHAS_LOG_SALVAS:
            del self._entradas_log[:-MAX_LINHAS_LOG_SALVAS]
        self.log.configure(state="normal")
        if tag:
            self.log.insert("end", texto + "\n", tag)
        else:
            self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


class DialogoMultaAvulsa(tk.Toplevel):
    MOTIVOS_SUGERIDOS = [
        "Deixou louça suja na pia",
        "Esqueceu a chave / Trancou alguém pra fora",
        "Gastou água quente toda no banho",
        "Não repôs o papel higiênico",
        "Sujou o fogão depois que limparam",
    ]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Aplicar Multa Avulsa (+1 Dose 🥃)")
        self.resizable(False, False)
        self.configure(bg=COR["bg_card"])
        self.transient(app)

        corpo = tk.Frame(self, bg=COR["bg_card"], padx=18, pady=16)
        corpo.pack(fill="both")

        tk.Label(
            corpo,
            text="🥃 Aplicar +1 Dose de Pinga no Pingômetro",
            font=FONTE_NEGRITO,
            bg=COR["bg_card"],
            fg=COR["pinga"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.var_morador = tk.StringVar(value=app.agente.integrantes[0].nome)
        self.var_motivo = tk.StringVar(value=self.MOTIVOS_SUGERIDOS[0])

        tk.Label(corpo, text="Morador Infrator:", font=FONTE, bg=COR["bg_card"]).grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=5
        )
        cb_m = ttk.Combobox(
            corpo,
            textvariable=self.var_morador,
            values=[p.nome for p in app.agente.integrantes],
            state="readonly",
            width=38,
        )
        cb_m.grid(row=1, column=1, sticky="w", pady=5)

        tk.Label(corpo, text="Motivo da Multa:", font=FONTE, bg=COR["bg_card"]).grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=5
        )
        cb_mot = ttk.Combobox(
            corpo,
            textvariable=self.var_motivo,
            values=self.MOTIVOS_SUGERIDOS,
            width=38,
        )
        cb_mot.grid(row=2, column=1, sticky="w", pady=5)

        botoes = tk.Frame(corpo, bg=COR["bg_card"])
        botoes.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botoes, text="Cravar +1 Dose 🥃", style="Primario.TButton", command=self._confirmar).pack(
            side="right", padx=8
        )
        self.grab_set()

    def _confirmar(self):
        nomes = [p.nome for p in self.app.agente.integrantes]
        motivo = self.var_motivo.get().strip()
        if not motivo:
            messagebox.showerror("Erro", "Informe o motivo da multa.", parent=self)
            return
        idx = nomes.index(self.var_morador.get())
        self.app._aplicar_multa_pinga(idx, self.app.agente.dia_atual, motivo)
        self.app.atualizar()
        self.destroy()


class DialogoImprevisto(tk.Toplevel):
    CAMPOS = {
        "indisponivel": ("dia", "integrante", "turno"),
        "extra": ("dia", "turno", "nome", "esforco"),
        "nao_realizada": ("dia", "ocorrencia"),
    }

    def __init__(self, app, dia_inicial=None, integrante_inicial=None):
        super().__init__(app)
        self.app = app
        self.title("Lançar Imprevisto na Casa")
        self.resizable(False, False)
        self.configure(bg=COR["bg_card"])
        self.transient(app)

        corpo = tk.Frame(self, bg=COR["bg_card"], padx=18, pady=16)
        corpo.pack(fill="both")

        tk.Label(
            corpo,
            text="⚡ O que aconteceu na república?",
            font=FONTE_NEGRITO,
            bg=COR["bg_card"],
            fg=COR["primaria"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        chaves = ("tipo", "dia", "integrante", "turno", "ocorrencia", "nome", "esforco")
        self.var = {}
        for chave in chaves:
            self.var[chave] = tk.StringVar()

        self.linhas = {}

        def linha(chave, rotulo, widget):
            r = len(self.linhas) + 1
            texto = tk.Label(corpo, text=rotulo, font=FONTE, bg=COR["bg_card"], fg=COR["texto"])
            texto.grid(row=r, column=0, sticky="w", padx=(0, 12), pady=5)
            widget.grid(row=r, column=1, sticky="w", pady=5)
            self.linhas[chave] = (texto, widget)
            return widget

        def combo(chave, valores=()):
            return ttk.Combobox(
                corpo, textvariable=self.var[chave], values=list(valores), state="readonly", width=46
            )

        self.cb_tipo = linha("tipo", "Situação:", combo("tipo", TIPOS_HUMANOS.values()))
        self.cb_dia = linha("dia", "Dia da Semana:", combo("dia"))
        linha("integrante", "Qual Morador?", combo("integrante", [p.nome for p in app.agente.integrantes]))
        self.cb_turno = linha("turno", "Qual Turno?", combo("turno"))
        self.cb_ocorrencia = linha("ocorrencia", "Qual Tarefa?", combo("ocorrencia"))
        linha("nome", "Qual é a Tarefa Extra?", ttk.Entry(corpo, textvariable=self.var["nome"], width=49))
        linha(
            "esforco",
            "Peso / Trabalho (1 a 5):",
            ttk.Spinbox(corpo, from_=1, to=5, textvariable=self.var["esforco"], width=8),
        )

        botoes = tk.Frame(corpo, bg=COR["bg_card"])
        botoes.grid(row=99, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botoes, text="Reorganizar Escala", style="Primario.TButton", command=self._confirmar).pack(
            side="right", padx=8
        )

        self.cb_tipo.bind("<<ComboboxSelected>>", lambda _e: self._ao_mudar_tipo())
        self.cb_dia.bind("<<ComboboxSelected>>", lambda _e: self._ao_mudar_dia())

        self.var["esforco"].set("2")
        self.var["tipo"].set(TIPOS_HUMANOS["indisponivel"])
        self._ao_mudar_tipo()

        if integrante_inicial is not None:
            self.var["integrante"].set(app.agente.integrantes[integrante_inicial].nome)
        if dia_inicial is not None and dia_inicial >= app.agente.dia_atual:
            self.var["dia"].set(DIAS[dia_inicial])
            self._ao_mudar_dia()

        self.grab_set()

    def _tipo(self):
        texto_escolhido = self.var["tipo"].get()
        for chave, nome in TIPOS_HUMANOS.items():
            if nome == texto_escolhido:
                return chave
        return "indisponivel"

    def _ao_mudar_tipo(self):
        tipo = self._tipo()
        for chave, (texto, widget) in self.linhas.items():
            if chave == "tipo" or chave in self.CAMPOS[tipo]:
                texto.grid()
                widget.grid()
            else:
                texto.grid_remove()
                widget.grid_remove()

        hoje = self.app.agente.dia_atual
        if tipo == "nao_realizada":
            self.dias = list(range(0, hoje + 1))
        else:
            self.dias = list(range(hoje, 7))

        self.cb_dia["values"] = [DIAS[d] for d in self.dias]
        prefixo_turno = ["Dia inteiro"] if tipo == "indisponivel" else ["Qualquer turno"]
        self.turnos = prefixo_turno + TURNOS
        self.cb_turno["values"] = self.turnos
        self.var["turno"].set(self.turnos[0])
        self.var["dia"].set(DIAS[hoje])
        self._ao_mudar_dia()

    def _ao_mudar_dia(self):
        ag = self.app.agente
        if not self.var["dia"].get():
            return
        dia = DIAS.index(self.var["dia"].get())
        self.ocorrencias = []
        opcoes_texto = []
        for k, a in enumerate(ag.estado):
            if a is not None and a[2] == dia and k not in ag.nao_realizadas:
                self.ocorrencias.append(k)
                nome_t = ag.tarefas[a[0]].nome
                nome_p = ag.integrantes[a[1]].nome
                turno_txt = TURNOS[a[3]].lower()
                opcoes_texto.append(f"{nome_t} — {nome_p} ({turno_txt})")

        self.cb_ocorrencia["values"] = opcoes_texto
        self.var["ocorrencia"].set(opcoes_texto[0] if opcoes_texto else "")

    def _confirmar(self):
        tipo = self._tipo()
        dia = DIAS.index(self.var["dia"].get())
        turno_str = self.var["turno"].get()
        turno = TURNOS.index(turno_str) if turno_str in TURNOS else None

        if tipo == "indisponivel":
            nomes = [p.nome for p in self.app.agente.integrantes]
            if self.var["integrante"].get() not in nomes:
                messagebox.showerror("Imprevisto", "Escolha qual morador ficou ocupado.", parent=self)
                return
            imp = Imprevisto(tipo, dia, turno, integrante=nomes.index(self.var["integrante"].get()))
        elif tipo == "extra":
            nome = self.var["nome"].get().strip()
            if not nome:
                messagebox.showerror("Imprevisto", "Digite qual é a tarefa extra.", parent=self)
                return
            try:
                esforco = int(self.var["esforco"].get())
                if esforco < 1:
                    esforco = 1
                elif esforco > 5:
                    esforco = 5
            except ValueError:
                esforco = 2
            turnos_perm = (turno,) if turno is not None else (0, 1, 2)
            tarefa = dados.Tarefa(nome, 1, esforco, turnos_permitidos=turnos_perm, dias_permitidos=(dia,), extra=True)
            imp = Imprevisto(tipo, dia, turno, nova_tarefa=tarefa)
        else:
            indice = self.cb_ocorrencia.current()
            if indice < 0:
                messagebox.showerror("Imprevisto", "Não há tarefa registrada para esse dia.", parent=self)
                return
            imp = Imprevisto(tipo, dia, ocorrencia=self.ocorrencias[indice])

        self.destroy()
        self.app.registrar_imprevisto(imp)


def imprimir_escala(integrantes, tarefas):
    plano = planejar_semana(integrantes, tarefas)
    print(
        f"Busca clássica: plano com custo {plano.custo:.1f}, {plano.nos_expandidos} nós expandidos pelo A* "
        f"({plano.nos_sem_heuristica} sem heurística)"
    )
    for p in plano.por_tarefa:
        horarios = ", ".join(f"{DIAS[d][:3]}-{TURNOS[s][0]}" for d, s in p.horarios)
        print(f"  {tarefas[p.tarefa].nome:<24} {horarios}")

    r = gerar_escala(integrantes, tarefas, plano.horarios)
    print(f"\nBusca local: custo {r.custo_inicial:.0f} (guloso) -> {r.custo:.0f} (SA) em {r.tempo:.1f}s")
    violacoes = {}
    for k, v in r.componentes.items():
        if v:
            violacoes[k] = v
    print("Violações:", violacoes)

    for i, p in enumerate(integrantes):
        print(f"\n{p.nome} ({p.cargo})")
        minhas = []
        for a in r.estado:
            if a and a[1] == i:
                minhas.append(a)
        minhas.sort(key=lambda a: (a[2], a[3]))
        for t, _, d, s in minhas:
            print(f"  {DIAS[d]:<8} {TURNOS[s]:<6} {tarefas[t].nome}")


def main():
    parser = argparse.ArgumentParser(description="Gestão e logística doméstica para república")
    parser.add_argument("--forms", metavar="CSV", help="CSV exportado das respostas do Google Forms")
    parser.add_argument("--sheets", metavar="LINK", help="link da planilha de respostas do Google Forms")
    parser.add_argument("--texto", action="store_true", help="imprime a escala no terminal, sem interface")
    parser.add_argument("--exemplo-csv", metavar="ARQUIVO", help="gera um CSV de exemplo no formato do Forms")
    parser.add_argument("--novo", action="store_true", help="ignora a escala salva e começa do zero")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.exemplo_csv:
        dados.gerar_csv_exemplo(dados.integrantes_simulados(), args.exemplo_csv)
        print(f"CSV de exemplo salvo em {args.exemplo_csv}")
        return

    avisos = []
    if args.forms:
        integrantes, avisos = dados.carregar_forms_arquivo(args.forms)
        fonte = f"Google Forms ({args.forms})"
        origem = {"tipo": "csv", "ref": os.path.abspath(args.forms)}
    elif args.sheets:
        integrantes, avisos = dados.carregar_forms_google_sheets(args.sheets)
        fonte = "Google Forms (planilha online)"
        origem = {"tipo": "sheets", "ref": args.sheets}
    else:
        integrantes = dados.integrantes_simulados()
        fonte = "Dados simulados"
        origem = None

    for aviso in avisos:
        print("Aviso:", aviso)

    if args.texto:
        imprimir_escala(integrantes, dados.tarefas_padrao())
        return

    # Retoma a escala salva, a não ser que se peça --novo ou que se aponte
    # outra fonte de horários (--forms/--sheets diferente da salva).
    estado_salvo = None
    if not args.novo:
        try:
            estado_salvo = persistencia.carregar()
        except Exception as erro:
            print("Aviso: não deu para ler a escala salva, começando do zero:", erro)
        if estado_salvo and origem is not None and estado_salvo.get("origem") != origem:
            print("Aviso: fonte de horários diferente da escala salva; começando uma escala nova.")
            estado_salvo = None
    App(integrantes, dados.tarefas_padrao(), fonte, origem, estado_salvo).mainloop()


if __name__ == "__main__":
    main()