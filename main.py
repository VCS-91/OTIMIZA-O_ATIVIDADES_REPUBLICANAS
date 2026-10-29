"""Sistema Inteligente de Gestão e Logística Doméstica para República.

Uso:
    python main.py                           # interface com dados simulados
    python main.py --forms respostas.csv     # interface com as respostas do Google Forms
    python main.py --sheets <link>           # idem, lendo direto da planilha de respostas
    python main.py --texto                   # imprime a escala no terminal, sem interface
    python main.py --exemplo-csv saida.csv   # gera um CSV no formato do Forms e sai
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import dados
from busca_classica import planejar_semana
from busca_local import PESOS, ProblemaEscala, gerar_escala
from busca_online import TIPOS, AgenteOnline, Imprevisto, Mudanca
from dados import DIAS, TURNOS, Integrante, Tarefa

COR = {
    "cabecalho": "#2f3e5c",
    "hoje": "#2f6fd6",
    "coluna_hoje": "#eef4ff",
    "celula": "#ffffff",
    "livre": "#e4e4e4",
    "conflito": "#f8c9c4",
    "alterada": "#fff1b8",
    "texto": "#1f1f1f",
    "passado": "#9a9a9a",
}
FONTE = ("Segoe UI", 9)
FONTE_NEGRITO = ("Segoe UI", 9, "bold")

NOMES_COMPONENTES = {
    "indisponivel": "Tarefas em horário ocupado ou dia livre",
    "dia_repetido": "Mesma tarefa duas vezes no dia",
    "choque": "Duas tarefas no mesmo turno",
    "dependencia": "Dependências fora de ordem",
    "dias_seguidos": "Tarefa em dias seguidos",
    "carga": "Desequilíbrio de carga (soma dos desvios²)",
    "preferencia": "Fora dos dias preferidos (× hierarquia)",
    "mudanca": "Alterações feitas pela busca online",
}


class App(tk.Tk):
    def __init__(self, integrantes: list[Integrante], tarefas: list[Tarefa], fonte: str):
        super().__init__()
        self.title("Sistema Inteligente de Gestão e Logística Doméstica — República")
        self.geometry("1400x800")
        self.minsize(1100, 600)
        self.integrantes = integrantes
        self.tarefas = tarefas
        self.fonte = fonte
        self.rng = random.Random()
        self.data_real = dt.date.today()
        self.plano = None
        self.resultado = None
        self.agente: AgenteOnline | None = None

        self._montar()
        self.nova_escala(self.data_real.weekday())
        self.after(60_000, self._verificar_data)

    # ------------------------------------------------------------ montagem

    def _montar(self) -> None:
        barra = ttk.Frame(self, padding=(8, 6))
        barra.pack(fill="x")
        ttk.Button(barra, text="Dados simulados", command=self.usar_simulados).pack(side="left")
        ttk.Button(barra, text="Importar CSV do Forms...", command=self.importar_csv).pack(side="left", padx=4)
        ttk.Button(barra, text="Importar do Google Planilhas...", command=self.importar_sheets).pack(side="left")
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(barra, text="Gerar nova escala", command=self.regerar).pack(side="left")
        ttk.Button(barra, text="Registrar imprevisto...", command=lambda: DialogoImprevisto(self)).pack(
            side="left", padx=4)
        ttk.Button(barra, text="Imprevisto aleatório", command=self.imprevisto_aleatorio).pack(side="left")
        ttk.Button(barra, text="Avançar dia ▶", command=self.avancar_dia).pack(side="left", padx=4)

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=8)
        self._montar_aba_escala()
        self._montar_aba_plano()
        self._montar_aba_integrantes()
        self._montar_aba_log()

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(8, 4), relief="sunken").pack(fill="x")

    def _montar_aba_escala(self) -> None:
        aba = ttk.Frame(self.abas, padding=6)
        self.abas.add(aba, text="Escala semanal")
        quadro = ttk.Frame(aba)
        quadro.pack(fill="both", expand=True)
        canvas = tk.Canvas(quadro, highlightthickness=0, bg="white")
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=canvas.yview)
        self.grade = tk.Frame(canvas, bg="white")
        janela = canvas.create_window((0, 0), window=self.grade, anchor="nw")
        self.grade.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(janela, width=e.width))
        canvas.configure(yscrollcommand=rolagem.set)
        canvas.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

        legenda = ttk.Frame(aba, padding=(0, 6, 0, 0))
        legenda.pack(fill="x")
        for cor, texto in [(COR["livre"], "dia livre"), (COR["conflito"], "conflito com horário"),
                           (COR["alterada"], "alterada pela busca online"), (COR["coluna_hoje"], "hoje")]:
            tk.Label(legenda, bg=cor, width=2, relief="solid", bd=1).pack(side="left", padx=(8, 3))
            ttk.Label(legenda, text=texto).pack(side="left")
        ttk.Label(legenda, text="   M/T/N = manhã/tarde/noite   ★ = tarefa extra   ✗ = não realizada   "
                                "dias anteriores a hoje em cinza").pack(side="left")

    def _montar_aba_plano(self) -> None:
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="Plano da semana (Busca Clássica)")
        ttk.Label(aba, text="Quando cada tarefa acontece (turno × dia). Entre parênteses, quantos integrantes "
                            "estão disponíveis no turno. Inclui os ajustes feitos pela busca online.").pack(anchor="w")
        self.grade_plano = tk.Frame(aba, bg="white")
        self.grade_plano.pack(fill="x", pady=6)

        colunas = {"tarefa": 220, "vezes": 60, "horarios": 380, "custo": 80, "astar": 110, "ucs": 150}
        titulos = ["Tarefa (ordem de planejamento)", "Vezes", "Horários escolhidos", "Custo",
                   "Nós expandidos A*", "Nós sem heurística (UCS)"]
        self.tabela_plano = ttk.Treeview(aba, columns=list(colunas), show="headings", height=10)
        for (coluna, largura), titulo in zip(colunas.items(), titulos):
            self.tabela_plano.heading(coluna, text=titulo)
            self.tabela_plano.column(coluna, width=largura, anchor="w")
        self.tabela_plano.pack(fill="both", expand=True, pady=6)
        self.info_plano = tk.StringVar()
        ttk.Label(aba, textvariable=self.info_plano, justify="left").pack(fill="x")

    def _montar_aba_integrantes(self) -> None:
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="Integrantes e Busca Local")
        self.info_fonte = tk.StringVar()
        ttk.Label(aba, textvariable=self.info_fonte, font=FONTE_NEGRITO).pack(anchor="w")

        colunas = {"nome": 140, "cargo": 90, "livres": 150, "preferidos": 150, "ocupados": 120,
                   "tarefas": 80, "carga": 80}
        titulos = ["Nome", "Hierarquia", "Dias livres", "Dias preferidos", "Turnos ocupados",
                   "Tarefas", "Esforço"]
        self.tabela_integrantes = ttk.Treeview(aba, columns=list(colunas), show="headings", height=10)
        for (coluna, largura), titulo in zip(colunas.items(), titulos):
            self.tabela_integrantes.heading(coluna, text=titulo)
            self.tabela_integrantes.column(coluna, width=largura, anchor="w")
        self.tabela_integrantes.pack(fill="x", pady=8)

        quadro = ttk.LabelFrame(aba, text="Busca Local (guloso + Simulated Annealing)", padding=8)
        quadro.pack(fill="both", expand=True)
        self.info_local = tk.StringVar()
        ttk.Label(quadro, textvariable=self.info_local, justify="left", font=("Consolas", 10)).pack(anchor="w")

    def _montar_aba_log(self) -> None:
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="Imprevistos (Busca Online)")
        self.log = tk.Text(aba, wrap="word", font=("Consolas", 10), state="disabled")
        rolagem = ttk.Scrollbar(aba, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=rolagem.set)
        self.log.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

    # ------------------------------------------------------------ ações

    def nova_escala(self, dia: int) -> None:
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            self.plano = planejar_semana(self.integrantes, self.tarefas)
            self.resultado = gerar_escala(self.integrantes, self.tarefas, self.plano.horarios)
        finally:
            self.configure(cursor="")
        self.agente = AgenteOnline(self.integrantes, self.tarefas, self.resultado.estado, dia)
        r = self.resultado
        self._log(f"[{DIAS[dia]}] Busca clássica: plano da semana com custo {self.plano.custo:.1f} "
                  f"({self.plano.nos_expandidos} nós expandidos pelo A*)")
        self._log(f"[{DIAS[dia]}] Busca local: responsáveis escolhidos, custo {r.custo_inicial:.0f} (guloso) "
                  f"-> {r.custo:.0f} (Simulated Annealing) em {r.tempo:.1f}s")
        self.atualizar()

    def regerar(self) -> None:
        if self.agente.historico and not messagebox.askyesno(
                "Gerar nova escala", "Os imprevistos registrados nesta semana serão descartados. Continuar?"):
            return
        self.nova_escala(self.agente.dia_atual)

    def avancar_dia(self) -> None:
        if self.agente.dia_atual == 6:
            self._log("--- Nova semana ---")
            self.nova_escala(0)
            return
        self.agente.dia_atual += 1
        self._log(f"[{DIAS[self.agente.dia_atual]}] Novo dia.")
        self.atualizar()

    def _verificar_data(self) -> None:
        """Acompanha a data real: se o dia virou com o programa aberto, a escala avança sozinha."""
        hoje = dt.date.today()
        for _ in range(min((hoje - self.data_real).days, 7)):
            self.avancar_dia()
        self.data_real = hoje
        self.after(60_000, self._verificar_data)

    def usar_simulados(self) -> None:
        self._usar_integrantes(dados.integrantes_simulados(), [], "Dados simulados")

    def importar_csv(self) -> None:
        caminho = filedialog.askopenfilename(title="Respostas do Google Forms (CSV)",
                                             filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        try:
            integrantes, avisos = dados.carregar_forms_arquivo(caminho)
        except Exception as erro:
            messagebox.showerror("Erro ao ler o CSV", str(erro))
            return
        self._usar_integrantes(integrantes, avisos, f"Google Forms ({caminho.split('/')[-1]})")

    def importar_sheets(self) -> None:
        url = simpledialog.askstring(
            "Google Planilhas",
            "Link da planilha de respostas do Forms\n"
            "(compartilhada como \"qualquer pessoa com o link pode ver\"):", parent=self)
        if not url:
            return
        try:
            integrantes, avisos = dados.carregar_forms_google_sheets(url.strip())
        except Exception as erro:
            messagebox.showerror("Erro ao ler a planilha", str(erro))
            return
        self._usar_integrantes(integrantes, avisos, "Google Forms (planilha online)")

    def _usar_integrantes(self, integrantes: list[Integrante], avisos: list[str], fonte: str) -> None:
        self.integrantes, self.fonte = integrantes, fonte
        self._log(f"Dados carregados: {fonte}, {len(integrantes)} integrantes.")
        for aviso in avisos:
            self._log(f"   aviso: {aviso}")
        if avisos:
            messagebox.showwarning("Avisos da importação", "\n".join(avisos))
        self.nova_escala(self.agente.dia_atual)

    def registrar_imprevisto(self, imp: Imprevisto) -> None:
        ag = self.agente
        descricao = imp.descricao(ag)  # antes de registrar: a ocorrência ainda tem o responsável original
        mudancas = ag.registrar(imp, self.rng)
        self._log(f"[{DIAS[ag.dia_atual]}] Imprevisto: {descricao}")
        if not mudancas:
            self._log("   nenhuma alteração necessária na escala")
        for m in mudancas:
            self._log("   " + self._descrever_mudanca(m))
        sem_responsavel = sum(1 for a in ag.estado if a is None)
        if sem_responsavel:
            self._log(f"   atenção: {sem_responsavel} tarefa(s) sem nenhuma opção válida de responsável")
        self.atualizar()

    def imprevisto_aleatorio(self) -> None:
        self.registrar_imprevisto(self.agente.imprevisto_aleatorio(self.rng))

    # ------------------------------------------------------------ desenho

    def atualizar(self) -> None:
        self._desenhar_escala()
        self._atualizar_plano()
        self._atualizar_integrantes()
        ag = self.agente
        comp = ProblemaEscala(ag.integrantes, ag.tarefas).componentes(ag.estado)
        custo = sum(PESOS[k] * v for k, v in comp.items())
        rigidas = int(comp["indisponivel"] + comp["dia_repetido"])
        self.status.set(f"Hoje: {DIAS[ag.dia_atual]}   |   Fonte: {self.fonte}   |   "
                        f"{len(ag.integrantes)} integrantes, {len(ag.estado)} tarefas na semana   |   "
                        f"Custo da escala: {custo:.0f}   |   Restrições rígidas violadas: {rigidas}   |   "
                        f"Imprevistos na semana: {len(ag.historico)}")

    def _desenhar_escala(self) -> None:
        for w in self.grade.winfo_children():
            w.destroy()
        ag = self.agente
        hoje = ag.dia_atual

        def celula(linha, coluna, texto, bg, fg="white", fonte=FONTE_NEGRITO):
            tk.Label(self.grade, text=texto, bg=bg, fg=fg, font=fonte, justify="left", anchor="nw",
                     relief="solid", bd=1, padx=6, pady=4, wraplength=170).grid(
                row=linha, column=coluna, sticky="nsew")

        celula(0, 0, "Integrante", COR["cabecalho"])
        for d in range(7):
            celula(0, d + 1, DIAS[d] + ("  (hoje)" if d == hoje else ""),
                   COR["hoje"] if d == hoje else COR["cabecalho"])
            self.grade.columnconfigure(d + 1, weight=1, uniform="dia")

        por_celula: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
        for k, a in enumerate(ag.estado):
            if a is not None:
                t, i, d, s = a
                por_celula.setdefault((i, d), []).append((s, k, t))

        for i, pessoa in enumerate(ag.integrantes):
            celula(i + 1, 0, f"{pessoa.nome}\n{pessoa.cargo}", COR["celula"], COR["texto"])
            for d in range(7):
                linhas, conflito, alterada = [], False, False
                if d in pessoa.dias_livres:
                    linhas.append("dia livre")
                for s, k, t in sorted(por_celula.get((i, d), [])):
                    tarefa = ag.tarefas[t]
                    marca = "✗ " if k in ag.nao_realizadas else "★ " if tarefa.extra else ""
                    linhas.append(f"{TURNOS[s][0]} · {marca}{tarefa.nome}")
                    conflito |= not pessoa.disponivel(d, s)
                    alterada |= k in ag.alteradas
                ocupados = [TURNOS[s][0] for s in range(3) if (d, s) in pessoa.ocupados]
                if ocupados and d not in pessoa.dias_livres:
                    linhas.append(f"(ocupado: {' '.join(ocupados)})")
                bg = (COR["conflito"] if conflito else COR["alterada"] if alterada
                      else COR["livre"] if d in pessoa.dias_livres
                      else COR["coluna_hoje"] if d == hoje else COR["celula"])
                fg = COR["passado"] if d < hoje else COR["texto"]
                celula(i + 1, d + 1, "\n".join(linhas), bg, fg, FONTE)

    def _atualizar_plano(self) -> None:
        ag = self.agente
        for w in self.grade_plano.winfo_children():
            w.destroy()

        def celula(linha, coluna, texto, bg, fg="white", fonte=FONTE_NEGRITO):
            tk.Label(self.grade_plano, text=texto, bg=bg, fg=fg, font=fonte, justify="left", anchor="nw",
                     relief="solid", bd=1, padx=6, pady=4, wraplength=170).grid(
                row=linha, column=coluna, sticky="nsew")

        celula(0, 0, "Turno", COR["cabecalho"])
        for d in range(7):
            celula(0, d + 1, DIAS[d] + ("  (hoje)" if d == ag.dia_atual else ""),
                   COR["hoje"] if d == ag.dia_atual else COR["cabecalho"])
            self.grade_plano.columnconfigure(d + 1, weight=1, uniform="dia")
        por_horario: dict[tuple[int, int], list[str]] = {}
        for k, a in enumerate(ag.estado):
            if a is not None:
                tarefa = ag.tarefas[a[0]]
                marca = "✗ " if k in ag.nao_realizadas else "★ " if tarefa.extra else ""
                por_horario.setdefault((a[2], a[3]), []).append(marca + tarefa.nome)
        for s in range(3):
            celula(s + 1, 0, TURNOS[s], COR["celula"], COR["texto"])
            for d in range(7):
                livres = sum(p.disponivel(d, s) for p in ag.integrantes)
                texto = "\n".join(sorted(por_horario.get((d, s), []))) + f"\n({livres} disponíveis)"
                bg = COR["coluna_hoje"] if d == ag.dia_atual else COR["celula"]
                celula(s + 1, d + 1, texto.strip(), bg, COR["passado"] if d < ag.dia_atual else COR["texto"], FONTE)

        self.tabela_plano.delete(*self.tabela_plano.get_children())
        for p in self.plano.por_tarefa:
            tarefa = self.tarefas[p.tarefa]
            horarios = ", ".join(f"{DIAS[d][:3]}-{TURNOS[s][0]}" for d, s in p.horarios)
            self.tabela_plano.insert("", "end", values=(tarefa.nome, tarefa.vezes_por_semana, horarios,
                                                        f"{p.custo:.1f}", p.nos_expandidos, p.nos_sem_heuristica))
        self.info_plano.set(
            f"Custo total do plano: {self.plano.custo:.1f}   |   A*: {self.plano.nos_expandidos} nós expandidos   |   "
            f"Busca de custo uniforme (sem heurística): {self.plano.nos_sem_heuristica} nós   |   "
            f"tempo: {self.plano.tempo * 1000:.0f} ms")

    def _atualizar_integrantes(self) -> None:
        ag = self.agente
        self.info_fonte.set(f"Fonte dos dados: {self.fonte}")
        self.tabela_integrantes.delete(*self.tabela_integrantes.get_children())
        for i, p in enumerate(sorted(ag.integrantes, key=lambda p: -p.hierarquia)):
            minhas = [a for a in ag.estado if a is not None and ag.integrantes[a[1]] is p]
            self.tabela_integrantes.insert("", "end", values=(
                p.nome, p.cargo,
                ", ".join(DIAS[d] for d in sorted(p.dias_livres)) or "—",
                ", ".join(DIAS[d] for d in sorted(p.dias_preferidos)) or "—",
                f"{len(p.ocupados)} de 21",
                len(minhas),
                sum(ag.tarefas[a[0]].esforco for a in minhas)))

        r = self.resultado
        linhas = [f"Custo inicial (guloso): {r.custo_inicial:>8.0f}",
                  f"Custo final (SA):       {r.custo:>8.0f}   ({r.iteracoes} iterações, {r.tempo:.2f}s)",
                  "",
                  f"{'Componente':<45}{'qtd':>8}{'peso':>8}"]
        for chave, nome in NOMES_COMPONENTES.items():
            linhas.append(f"{nome:<45}{r.componentes[chave]:>8.0f}{PESOS[chave]:>8}")
        self.info_local.set("\n".join(linhas))

    def _descrever_mudanca(self, m: Mudanca) -> str:
        ag = self.agente

        def formatar(a):
            return "—" if a is None else f"{ag.integrantes[a[1]].nome}, {DIAS[a[2]]} ({TURNOS[a[3]].lower()})"

        tarefa = ag.tarefas[(m.depois or m.antes)[0]]
        nome = ("★ " if tarefa.extra else "") + tarefa.nome
        if m.antes is None:
            return f"{nome}: nova -> {formatar(m.depois)}"
        return f"{nome}: {formatar(m.antes)} -> {formatar(m.depois)}"

    def _log(self, texto: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


class DialogoImprevisto(tk.Toplevel):
    CAMPOS = {
        "indisponivel": ("dia", "integrante", "turno"),
        "extra": ("dia", "turno", "nome", "esforco"),
        "nao_realizada": ("dia", "ocorrencia"),
    }

    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Registrar imprevisto")
        self.resizable(False, False)
        self.transient(app)

        corpo = ttk.Frame(self, padding=12)
        corpo.pack(fill="both")
        self.var = {chave: tk.StringVar() for chave in
                    ("tipo", "dia", "integrante", "turno", "ocorrencia", "nome", "esforco")}
        self.linhas: dict[str, tuple[ttk.Label, tk.Widget]] = {}

        def linha(chave, rotulo, widget):
            r = len(self.linhas)
            texto = ttk.Label(corpo, text=rotulo)
            texto.grid(row=r, column=0, sticky="w", padx=(0, 8), pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3)
            self.linhas[chave] = (texto, widget)
            return widget

        def combo(chave, valores=()):
            return ttk.Combobox(corpo, textvariable=self.var[chave], values=list(valores),
                                state="readonly", width=42)

        linha("tipo", "Tipo:", combo("tipo", TIPOS.values()))
        self.cb_dia = linha("dia", "Dia:", combo("dia"))
        linha("integrante", "Integrante:", combo("integrante", [p.nome for p in app.agente.integrantes]))
        self.cb_turno = linha("turno", "Turno:", combo("turno"))
        self.cb_ocorrencia = linha("ocorrencia", "Tarefa:", combo("ocorrencia"))
        linha("nome", "Nova tarefa:", ttk.Entry(corpo, textvariable=self.var["nome"], width=45))
        linha("esforco", "Esforço (1-5):", ttk.Spinbox(corpo, from_=1, to=5, textvariable=self.var["esforco"],
                                                       width=5))

        botoes = ttk.Frame(corpo)
        botoes.grid(row=99, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botoes, text="Registrar", command=self._confirmar).pack(side="right", padx=6)

        self.var["tipo"].trace_add("write", lambda *_: self._ao_mudar_tipo())
        self.var["dia"].trace_add("write", lambda *_: self._ao_mudar_dia())
        self.var["esforco"].set("2")
        self.var["tipo"].set(TIPOS["indisponivel"])
        self.grab_set()

    def _tipo(self) -> str:
        return next(chave for chave, nome in TIPOS.items() if nome == self.var["tipo"].get())

    def _ao_mudar_tipo(self) -> None:
        tipo = self._tipo()
        for chave, (texto, widget) in self.linhas.items():
            if chave == "tipo" or chave in self.CAMPOS[tipo]:
                texto.grid()
                widget.grid()
            else:
                texto.grid_remove()
                widget.grid_remove()
        hoje = self.app.agente.dia_atual
        # tarefa não realizada: hoje ou dias anteriores; demais: hoje em diante
        self.dias = list(range(0, hoje + 1)) if tipo == "nao_realizada" else list(range(hoje, 7))
        self.cb_dia["values"] = [DIAS[d] for d in self.dias]
        self.turnos = (["Dia inteiro"] if tipo == "indisponivel" else ["Qualquer turno"]) + TURNOS
        self.cb_turno["values"] = self.turnos
        self.var["turno"].set(self.turnos[0])
        self.var["dia"].set(DIAS[hoje])

    def _ao_mudar_dia(self) -> None:
        ag = self.app.agente
        if not self.var["dia"].get():
            return
        dia = DIAS.index(self.var["dia"].get())
        self.ocorrencias = [k for k, a in enumerate(ag.estado)
                            if a is not None and a[2] == dia and k not in ag.nao_realizadas]
        self.cb_ocorrencia["values"] = [
            f"{ag.tarefas[ag.estado[k][0]].nome} — {ag.integrantes[ag.estado[k][1]].nome} "
            f"({TURNOS[ag.estado[k][3]].lower()})" for k in self.ocorrencias]
        self.var["ocorrencia"].set(self.cb_ocorrencia["values"][0] if self.ocorrencias else "")

    def _confirmar(self) -> None:
        tipo = self._tipo()
        dia = DIAS.index(self.var["dia"].get())
        turno = TURNOS.index(self.var["turno"].get()) if self.var["turno"].get() in TURNOS else None
        if tipo == "indisponivel":
            nomes = [p.nome for p in self.app.agente.integrantes]
            if self.var["integrante"].get() not in nomes:
                messagebox.showerror("Imprevisto", "Escolha o integrante.", parent=self)
                return
            imp = Imprevisto(tipo, dia, turno, integrante=nomes.index(self.var["integrante"].get()))
        elif tipo == "extra":
            nome = self.var["nome"].get().strip()
            if not nome:
                messagebox.showerror("Imprevisto", "Informe o nome da nova tarefa.", parent=self)
                return
            try:
                esforco = min(max(int(self.var["esforco"].get()), 1), 5)
            except ValueError:
                esforco = 2
            tarefa = Tarefa(nome, 1, esforco,
                            turnos_permitidos=(turno,) if turno is not None else (0, 1, 2),
                            dias_permitidos=(dia,), extra=True)
            imp = Imprevisto(tipo, dia, turno, nova_tarefa=tarefa)
        else:
            indice = self.cb_ocorrencia.current()
            if indice < 0:
                messagebox.showerror("Imprevisto", "Não há tarefa para esse dia.", parent=self)
                return
            imp = Imprevisto(tipo, dia, ocorrencia=self.ocorrencias[indice])
        self.destroy()
        self.app.registrar_imprevisto(imp)


def imprimir_escala(integrantes: list[Integrante], tarefas: list[Tarefa]) -> None:
    plano = planejar_semana(integrantes, tarefas)
    print(f"Busca clássica: plano com custo {plano.custo:.1f}, {plano.nos_expandidos} nós expandidos pelo A* "
          f"({plano.nos_sem_heuristica} sem heurística)")
    for p in plano.por_tarefa:
        horarios = ", ".join(f"{DIAS[d][:3]}-{TURNOS[s][0]}" for d, s in p.horarios)
        print(f"  {tarefas[p.tarefa].nome:<24} {horarios}")

    r = gerar_escala(integrantes, tarefas, plano.horarios)
    print(f"\nBusca local: custo {r.custo_inicial:.0f} (guloso) -> {r.custo:.0f} (SA) em {r.tempo:.1f}s")
    print("Violações:", {k: v for k, v in r.componentes.items() if v})
    for i, p in enumerate(integrantes):
        print(f"\n{p.nome} ({p.cargo})")
        for t, _, d, s in sorted((a for a in r.estado if a and a[1] == i), key=lambda a: (a[2], a[3])):
            print(f"  {DIAS[d]:<8} {TURNOS[s]:<6} {tarefas[t].nome}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestão e logística doméstica para república")
    parser.add_argument("--forms", metavar="CSV", help="CSV exportado das respostas do Google Forms")
    parser.add_argument("--sheets", metavar="LINK", help="link da planilha de respostas do Google Forms")
    parser.add_argument("--texto", action="store_true", help="imprime a escala no terminal, sem interface")
    parser.add_argument("--exemplo-csv", metavar="ARQUIVO", help="gera um CSV de exemplo no formato do Forms")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.exemplo_csv:
        dados.gerar_csv_exemplo(dados.integrantes_simulados(), args.exemplo_csv)
        print(f"CSV de exemplo salvo em {args.exemplo_csv}")
        return

    avisos: list[str] = []
    if args.forms:
        integrantes, avisos = dados.carregar_forms_arquivo(args.forms)
        fonte = f"Google Forms ({args.forms})"
    elif args.sheets:
        integrantes, avisos = dados.carregar_forms_google_sheets(args.sheets)
        fonte = "Google Forms (planilha online)"
    else:
        integrantes, fonte = dados.integrantes_simulados(), "Dados simulados"
    for aviso in avisos:
        print("Aviso:", aviso)

    if args.texto:
        imprimir_escala(integrantes, dados.tarefas_padrao())
        return
    App(integrantes, dados.tarefas_padrao(), fonte).mainloop()


if __name__ == "__main__":
    main()
