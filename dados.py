# Lê as respostas exportadas do Forms e converte pra lista de Integrantes.
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
TURNOS = ["Manhã", "Tarde", "Noite"]
HIERARQUIAS = {5: "Decano", 4: "Vice-Decano",
               3: "Morador", 2: "Semi-Bixo", 1: "Calouro"}
# Quantos dias livres (sem tarefa, mesmo estando disponível) cada nível pode escolher.
MAX_DIAS_LIVRES = {5: 2, 4: 1, 3: 1, 2: 0, 1: 0}


@dataclass
class Integrante:
    nome: str
    hierarquia: int
    ocupados: set[tuple[int, int]] = field(
        default_factory=set)  # (dia, turno) com aula/trabalho
    dias_livres: set[int] = field(default_factory=set)
    dias_preferidos: set[int] = field(default_factory=set)

    @property
    def cargo(self) -> str:
        return HIERARQUIAS.get(self.hierarquia, f"Nível {self.hierarquia}")

    def disponivel(self, dia: int, turno: int) -> bool:
        return dia not in self.dias_livres and (dia, turno) not in self.ocupados


@dataclass
class Tarefa:
    nome: str
    vezes_por_semana: int
    esforco: int
    turnos_permitidos: tuple[int, ...] = (0, 1, 2)
    dias_permitidos: tuple[int, ...] = tuple(range(7))
    # tarefas que, no mesmo dia, devem vir antes
    depende_de: tuple[str, ...] = ()
    extra: bool = False  # criada pela busca online (imprevisto ou repetição)


# ---------------------------------------------------------------- dados simulados

def _agenda(**dias: str) -> set[tuple[int, int]]:
    """_agenda(seg="MT", ter="N") -> {(0, 0), (0, 1), (1, 2)}"""
    chaves = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    letras = {"M": 0, "T": 1, "N": 2}
    return {(chaves.index(d), letras[l]) for d, turnos in dias.items() for l in turnos}


def integrantes_simulados() -> list[Integrante]:
    return [
        Integrante("Carlos", 5, _agenda(seg="M", ter="MT",
                   qua="M", qui="MT"), {5, 6}, {0, 2}),
        Integrante("Bruno", 4, _agenda(seg="MT", ter="MT",
                   qua="M", qui="MT", sex="MT"), {4}, {2}),
        Integrante("Diego", 3, _agenda(seg="MT", ter="N",
                   qua="MT", qui="N", sex="MT"), {6}, {1, 3}),
        Integrante("Felipe", 3, _agenda(seg="T", ter="T", qua="T",
                   qui="T", sex="T", sab="M"), set(), {4}),
        Integrante("Lucas", 2, _agenda(seg="MN", qua="MN", sex="M")),
        Integrante("Gabriel", 1, _agenda(
            seg="MT", ter="M", qua="MT", qui="M", sex="M")),
        Integrante("Henrique", 1, _agenda(
            ter="MT", qua="MT", qui="MT", sex="MT", sab="M")),
    ]


def tarefas_padrao() -> list[Tarefa]:
    return [
        Tarefa("Lavar louça", 7, 2, turnos_permitidos=(1, 2)),
        Tarefa("Limpar fogão e bancada", 2, 2, depende_de=("Lavar louça",)),
        Tarefa("Varrer a casa", 3, 2),
        Tarefa("Passar pano", 2, 3, depende_de=("Varrer a casa",)),
        Tarefa("Limpar banheiro", 2, 3),
        Tarefa("Levar o lixo", 3, 1, turnos_permitidos=(
            2,), dias_permitidos=(0, 2, 4)),
        Tarefa("Lavar panos e toalhas", 1, 2),
        Tarefa("Compras do mercado", 1, 3, turnos_permitidos=(0, 1)),
        Tarefa("Limpar o quintal", 1, 2, turnos_permitidos=(0, 1)),
        Tarefa("Organizar a geladeira", 1, 1),
    ]


# ---------------------------------------------------------------- Google Forms

_CHAVES_DIA = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
# Ordem importa: "vice-decano" contém "decano" e "semi-bixo" contém "bixo".
_PALAVRAS_HIERARQUIA = [("vice", 4), ("semi", 2), ("decano", 5), ("morador", 3),
                        ("calouro", 1), ("bixo", 1), ("bicho", 1)]


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower().strip()


def _dia(texto: str) -> int | None:
    chave = _normalizar(texto)[:3]
    return _CHAVES_DIA.index(chave) if chave in _CHAVES_DIA else None


def _turno(texto: str) -> int | None:
    n = _normalizar(texto)
    for i, nome in enumerate(("manha", "tarde", "noite")):
        if nome in n:
            return i
    return None


def _itens(valor: str | None) -> list[str]:
    return [p.strip() for p in re.split(r"[;,]", valor or "") if p.strip()]


def _hierarquia(valor: str) -> int:
    n = _normalizar(valor)
    for palavra, nivel in _PALAVRAS_HIERARQUIA:
        if palavra in n:
            return nivel
    m = re.search(r"\d", n)
    return int(m.group()) if m and int(m.group()) in HIERARQUIAS else 1


def ler_respostas_forms(texto_csv: str) -> tuple[list[Integrante], list[str]]:
    """Converte o CSV de respostas do Forms em integrantes. Devolve (integrantes, avisos)."""
    leitor = csv.DictReader(io.StringIO(texto_csv.lstrip("\ufeff")))
    colunas = leitor.fieldnames or []

    def achar(*chaves: str) -> str | None:
        for c in colunas:
            if "[" not in c and any(k in _normalizar(c) for k in chaves):
                return c
        return None

    col_nome = achar("nome")
    col_hierarquia = achar("hierarquia", "cargo")
    col_livres = achar("livre")
    col_preferidos = achar("prefer")
    col_grade = {}
    for c in colunas:
        m = re.search(r"\[(.+?)\]\s*$", c)
        if m and _dia(m.group(1)) is not None:
            col_grade[c] = _dia(m.group(1))
    if col_nome is None:
        raise ValueError("O CSV não tem uma coluna de nome.")

    avisos = []
    por_nome: dict[str, Integrante] = {}
    for linha in leitor:
        nome = (linha.get(col_nome) or "").strip()
        if not nome:
            continue
        nivel = _hierarquia(linha.get(col_hierarquia, "")
                            ) if col_hierarquia else 1
        ocupados = {(d, t) for c, d in col_grade.items()
                    for item in _itens(linha.get(c)) if (t := _turno(item)) is not None}
        livres = [d for item in _itens(linha.get(col_livres)) if (
            d := _dia(item)) is not None]
        maximo = MAX_DIAS_LIVRES.get(nivel, 0)
        if len(livres) > maximo:
            avisos.append(f"Atenção: {nome} pediu {len(livres)} dias livres, mas como {HIERARQUIAS[nivel]} só tem direito a {maximo}. Cortando os excedentes.")
            livres = livres[:maximo]
        preferidos = {d for item in _itens(
            linha.get(col_preferidos)) if (d := _dia(item)) is not None}
        # Se a mesma pessoa respondeu mais de uma vez, vale a resposta mais recente.
        por_nome[_normalizar(nome)] = Integrante(
            nome, nivel, ocupados, set(livres), preferidos)

    if not por_nome:
        raise ValueError("Nenhuma resposta válida encontrada no CSV.")
    return list(por_nome.values()), avisos


def carregar_forms_arquivo(caminho: str) -> tuple[list[Integrante], list[str]]:
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return ler_respostas_forms(f.read())


def link_para_csv(url: str) -> str:
    """Converte o link da planilha de respostas no link de exportação em CSV."""
    if "/d/e/" in url or "format=csv" in url or "output=csv" in url:
        return url
    m = re.search(r"/spreadsheets/d/([\w-]+)", url)
    if not m:
        return url
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return (f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv"
            + (f"&gid={gid.group(1)}" if gid else ""))


def carregar_forms_google_sheets(url: str) -> tuple[list[Integrante], list[str]]:
    try:
        with urllib.request.urlopen(link_para_csv(url), timeout=15) as resposta:
            return ler_respostas_forms(resposta.read().decode("utf-8-sig"))
    except Exception as e:
        raise RuntimeError(f"Falha ao conectar no Google Planilhas. Verifique o link ou a internet. Erro: {e}")


def gerar_csv_exemplo(integrantes: list[Integrante], caminho: str) -> None:
    """Escreve os integrantes no mesmo formato do CSV exportado pelo Forms."""
    cabecalho = (["Carimbo de data/hora", "Nome", "Hierarquia na república"]
                 + [f"Horários ocupados (aulas, trabalho, compromissos) [{d}]" for d in DIAS]
                 + ["Dias livres (sem tarefas)", "Dias preferidos para tarefas"])
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(cabecalho)
        for p in integrantes:
            grade = [", ".join(TURNOS[s] for s in range(
                3) if (d, s) in p.ocupados) for d in range(7)]
            escritor.writerow([agora, p.nome, p.cargo, *grade,
                               ", ".join(DIAS[d]
                                         for d in sorted(p.dias_livres)),
                               ", ".join(DIAS[d] for d in sorted(p.dias_preferidos))])