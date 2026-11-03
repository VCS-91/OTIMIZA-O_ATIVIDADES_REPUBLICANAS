# Algoritmo A* para montar o esqueleto da semana (dia e turno das tarefas).
# A heurística h(n) é admissível: ocorrências restantes * menor custo possível.
# Cada tarefa é resolvida pelo A* e depois a semana é refinada tarefa a tarefa,
# com o A* vendo todas as outras tarefas, até o custo global parar de cair.
from __future__ import annotations

import heapq
import itertools
import math
import time
from collections import Counter
from dataclasses import dataclass, field

from dados import Integrante, Tarefa

PESOS = {
    # × fração dos integrantes ocupados (aula/trabalho/dia livre) no turno
    "poucos_disponiveis": 10,
    "turno_cheio": 6,          # por tarefa já marcada no mesmo turno
    # × esforço da tarefa × esforço das outras tarefas marcadas no mesmo dia
    "esforco_no_dia": 0.5,
    # × (intervalo entre repetições - intervalo ideal)²
    "espacamento": 4,
    # pré-requisito ausente no dia, ou marcado no mesmo turno ou num turno posterior
    "dependencia": 50,
    "sem_ninguem": 1000,       # nenhum integrante livre sobrando naquele turno
}


@dataclass
class PlanoTarefa:
    tarefa: int
    horarios: list[tuple[int, int]]
    custo: float
    nos_expandidos: int
    nos_sem_heuristica: int  # busca de custo uniforme no mesmo subproblema, para comparação


@dataclass
class PlanoSemana:
    # alinhado com ProblemaEscala.ocorrencias()
    horarios: list[tuple[int, int]]
    custo: float                 # custo global da semana (custo_global)
    tempo: float
    por_tarefa: list[PlanoTarefa] = field(default_factory=list)
    custo_inicial: float = 0.0   # custo global após a 1ª passada, antes do refino
    rodadas: int = 0             # rodadas de refino executadas

    @property
    def nos_expandidos(self) -> int:
        return sum(p.nos_expandidos for p in self.por_tarefa)

    @property
    def nos_sem_heuristica(self) -> int:
        return sum(p.nos_sem_heuristica for p in self.por_tarefa)


def _ordem_de_planejamento(tarefas: list[Tarefa]) -> list[int]:
    # Coloca quem tem pré-requisito primeiro e depois as tarefas mais difíceis de encaixar
    indice = {t.nome: i for i, t in enumerate(tarefas)}
    nivel: dict[int, int] = {}

    def calcular(i: int) -> int:
        if i not in nivel:
            nivel[i] = 0  # trava pra não dar loop infinito se rolar dependência circular
            deps = [indice[d] for d in tarefas[i].depende_de if d in indice]
            nivel[i] = 1 + max(map(calcular, deps)) if deps else 0
        return nivel[i]

    def folga(i: int) -> float:
        t = tarefas[i]
        return len(t.dias_permitidos) * len(t.turnos_permitidos) / t.vezes_por_semana

    return sorted(range(len(tarefas)), key=lambda i: (calcular(i), folga(i), -tarefas[i].esforco))


def _a_estrela(tarefa: Tarefa, custo_horario: dict[tuple[int, int], float],
               usar_heuristica: bool) -> tuple[list[tuple[int, int]], float, int]:
    vezes = tarefa.vezes_por_semana
    dias = sorted(tarefa.dias_permitidos)
    if vezes > len(dias):
        raise ValueError(
            f"\"{tarefa.nome}\" precisa de {vezes} dias, mas só {len(dias)} são permitidos.")
    ideal = 7 / vezes
    minimo = min(custo_horario.values())

    def h(marcadas: int) -> float:
        return (vezes - marcadas) * minimo if usar_heuristica else 0

    contador = itertools.count()
    fronteira = [(h(0), next(contador), 0.0, 0, -1, ())]
    melhor_g = {(0, -1): 0.0}
    expandidos = 0
    while fronteira:
        _, _, g, marcadas, ultimo, caminho = heapq.heappop(fronteira)
        if g > melhor_g.get((marcadas, ultimo), math.inf):
            continue
        if marcadas == vezes:
            return list(caminho), g, expandidos
        expandidos += 1
        restantes = vezes - marcadas - 1
        for d in dias:
            # depois do último dia usado, e deixando dias suficientes para as próximas ocorrências
            if d <= ultimo or sum(1 for x in dias if x > d) < restantes:
                continue
            espaco = PESOS["espacamento"] * \
                (d - ultimo - ideal) ** 2 if ultimo >= 0 else 0
            for s in tarefa.turnos_permitidos:
                g2 = g + custo_horario[d, s] + espaco
                if g2 < melhor_g.get((marcadas + 1, d), math.inf):
                    melhor_g[marcadas + 1, d] = g2
                    heapq.heappush(fronteira, (g2 + h(marcadas + 1), next(contador), g2, marcadas + 1, d,
                                               caminho + ((d, s),)))
    raise ValueError(f"Não há horários possíveis para \"{tarefa.nome}\".")


def _dependentes(tarefas: list[Tarefa]) -> list[list[int]]:
    """dependentes[t] = tarefas que têm a tarefa t como pré-requisito."""
    return [[u for u, outra in enumerate(tarefas) if tarefa.nome in outra.depende_de]
            for tarefa in tarefas]


def _custos_horario(t: int, tarefas: list[Tarefa], planejadas: dict[int, list[tuple[int, int]]],
                    disponiveis: dict[tuple[int, int], int], total: int,
                    dependentes: list[list[int]]) -> dict[tuple[int, int], float]:
    """Custo de colocar uma ocorrência da tarefa t em cada (dia, turno), com as
    outras tarefas de `planejadas` fixas.

    Cada valor é o quanto o custo global (custo_global) aumenta, a menos de uma
    constante que não depende dos horários escolhidos para t. Por isso, quando só
    a tarefa t pode mudar, o caminho mais barato do A* é também o plano que
    deixa a semana inteira mais barata.
    """
    nomes = {x.nome for x in tarefas}
    ocupacao = Counter()          # tarefas marcadas em cada (dia, turno)
    esforco_dia = Counter()       # esforço marcado em cada dia
    turno_de: dict[tuple[str, int], int] = {}  # (tarefa, dia) -> turno
    for u, horarios in planejadas.items():
        if u == t:
            continue
        for d, s in horarios:
            ocupacao[d, s] += 1
            esforco_dia[d] += tarefas[u].esforco
            turno_de[tarefas[u].nome, d] = s

    tarefa = tarefas[t]
    # tarefas que dependem de t e já estão na semana
    dependentes_marcadas = [u for u in dependentes[t] if u != t and u in planejadas]
    custos = {}
    for d in tarefa.dias_permitidos:
        for s in tarefa.turnos_permitidos:
            c = (PESOS["poucos_disponiveis"] * (1 - disponiveis[d, s] / total)
                 + PESOS["turno_cheio"] * ocupacao[d, s]
                 + PESOS["esforco_no_dia"] * tarefa.esforco * esforco_dia[d])
            if disponiveis[d, s] - ocupacao[d, s] <= 0:
                c += PESOS["sem_ninguem"]
            # pré-requisito de t ausente no dia, ou no mesmo turno / turno posterior
            for dep in tarefa.depende_de:
                if dep in nomes and turno_de.get((dep, d), math.inf) >= s:
                    c += PESOS["dependencia"]
            # t é pré-requisito: só "cobre" a tarefa dependente se ela estiver no
            # mesmo dia e num turno posterior. Quem não cobre paga a penalidade.
            for u in dependentes_marcadas:
                if turno_de.get((tarefas[u].nome, d), -1) <= s:
                    c += PESOS["dependencia"]
            custos[d, s] = c
    return custos


def _custo_caminho(horarios: list[tuple[int, int]], tarefa: Tarefa,
                   custos: dict[tuple[int, int], float]) -> float:
    """Mesmo custo que o A* acumula: custo dos horários + espaçamento."""
    ideal = 7 / tarefa.vezes_por_semana
    c = sum(custos[h] for h in horarios)
    for (d1, _), (d2, _) in zip(horarios, horarios[1:]):
        c += PESOS["espacamento"] * (d2 - d1 - ideal) ** 2
    return c


def custo_global(tarefas: list[Tarefa], planejadas: dict[int, list[tuple[int, int]]],
                 disponiveis: dict[tuple[int, int], int], total: int) -> float:
    """Custo da semana inteira, olhando todas as tarefas ao mesmo tempo."""
    nomes = {x.nome for x in tarefas}
    por_horario = Counter()
    esforcos_dia: dict[int, list[int]] = {}
    turno_de: dict[tuple[str, int], int] = {}
    c = 0.0
    for t, horarios in planejadas.items():
        tarefa = tarefas[t]
        unario = {h: PESOS["poucos_disponiveis"] *
                  (1 - disponiveis[h] / total) for h in horarios}
        c += _custo_caminho(horarios, tarefa, unario)
        for d, s in horarios:
            por_horario[d, s] += 1
            esforcos_dia.setdefault(d, []).append(tarefa.esforco)
            turno_de[tarefa.nome, d] = s
    for h, n in por_horario.items():
        c += PESOS["turno_cheio"] * n * (n - 1) / 2       # cada par no mesmo turno
        c += PESOS["sem_ninguem"] * max(0, n - disponiveis[h])
    for esforcos in esforcos_dia.values():
        soma = sum(esforcos)
        # para cada par de tarefas no mesmo dia, o produto dos esforços
        c += PESOS["esforco_no_dia"] * \
            (soma * soma - sum(e * e for e in esforcos)) / 2
    for t, horarios in planejadas.items():
        for d, s in horarios:
            for dep in tarefas[t].depende_de:
                if dep in nomes and turno_de.get((dep, d), math.inf) >= s:
                    c += PESOS["dependencia"]
    return c


def planejar_semana(integrantes: list[Integrante], tarefas: list[Tarefa],
                    max_rodadas: int = 10) -> PlanoSemana:
    """1ª passada: cada tarefa, na ordem de planejamento, é marcada pelo A*
    vendo só as tarefas já planejadas.
    Refino: cada tarefa é replanejada pelo A* vendo a semana inteira (todas as
    outras fixas), e o novo plano só é aceito se o custo global cair. As rodadas
    se repetem até nenhuma tarefa conseguir melhorar sozinha."""
    inicio = time.perf_counter()
    total = len(integrantes)
    disponiveis = {(d, s): sum(p.disponivel(d, s) for p in integrantes)
                   for d in range(7) for s in range(3)}
    dependentes = _dependentes(tarefas)
    ordem = _ordem_de_planejamento(tarefas)
    escolhidos: dict[int, list[tuple[int, int]]] = {}
    nos = Counter()
    nos_ucs = Counter()

    def resolver(t: int) -> list[tuple[int, int]]:
        custos = _custos_horario(
            t, tarefas, escolhidos, disponiveis, total, dependentes)
        horarios, _, n = _a_estrela(tarefas[t], custos, usar_heuristica=True)
        _, _, n_ucs = _a_estrela(tarefas[t], custos, usar_heuristica=False)
        nos[t] += n
        nos_ucs[t] += n_ucs
        return horarios

    for t in ordem:
        escolhidos[t] = resolver(t)
    custo_inicial = atual = custo_global(
        tarefas, escolhidos, disponiveis, total)

    rodadas = 0
    while rodadas < max_rodadas:
        rodadas += 1
        melhorou = False
        for t in ordem:
            horarios = resolver(t)
            if horarios == escolhidos[t]:
                continue
            candidato = {**escolhidos, t: horarios}
            novo = custo_global(tarefas, candidato, disponiveis, total)
            if novo < atual - 1e-9:
                escolhidos, atual, melhorou = candidato, novo, True
        if not melhorou:
            break

    # Custo de cada tarefa = quanto ela acrescenta ao custo global, vendo só as
    # anteriores na ordem de planejamento. A soma dá exatamente o custo global.
    por_tarefa = []
    anteriores: dict[int, list[tuple[int, int]]] = {}
    for t in ordem:
        custos = _custos_horario(
            t, tarefas, anteriores, disponiveis, total, dependentes)
        por_tarefa.append(PlanoTarefa(t, escolhidos[t], _custo_caminho(escolhidos[t], tarefas[t], custos),
                                      nos[t], nos_ucs[t]))
        anteriores[t] = escolhidos[t]

    alinhado = [h for t in range(len(tarefas)) for h in escolhidos[t]]
    return PlanoSemana(alinhado, atual, time.perf_counter() - inicio, por_tarefa,
                       custo_inicial, rodadas)