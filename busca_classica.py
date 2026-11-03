# Algoritmo A* para montar o esqueleto da semana (dia e turno das tarefas).
# A heurística h(n) é admissível: ocorrências restantes * menor custo possível.
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
    "esforco_no_dia": 1,       # por ponto de esforço já marcado no mesmo dia
    # × (intervalo entre repetições - intervalo ideal)²
    "espacamento": 4,
    "dependencia": 50,         # pré-requisito ausente no dia ou marcado num turno posterior
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
    custo: float
    tempo: float
    por_tarefa: list[PlanoTarefa] = field(default_factory=list)

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


def planejar_semana(integrantes: list[Integrante], tarefas: list[Tarefa]) -> PlanoSemana:
    inicio = time.perf_counter()
    total = len(integrantes)
    disponiveis = {(d, s): sum(p.disponivel(d, s) for p in integrantes)
                   for d in range(7) for s in range(3)}
    nomes = {t.nome for t in tarefas}
    ocupacao = Counter()          # tarefas já marcadas em cada (dia, turno)
    esforco_dia = Counter()       # esforço já marcado em cada dia
    turno_de: dict[tuple[str, int], int] = {}  # (tarefa, dia) -> turno
    escolhidos: dict[int, list[tuple[int, int]]] = {}
    por_tarefa = []

    for t in _ordem_de_planejamento(tarefas):
        tarefa = tarefas[t]

        def custo(d: int, s: int) -> float:
            c = (PESOS["poucos_disponiveis"] * (1 - disponiveis[d, s] / total)
                 + PESOS["turno_cheio"] * ocupacao[d, s]
                 + PESOS["esforco_no_dia"] * esforco_dia[d])
            if disponiveis[d, s] - ocupacao[d, s] <= 0:
                c += PESOS["sem_ninguem"]
            for dep in tarefa.depende_de:
                if dep in nomes and turno_de.get((dep, d), math.inf) > s:
                    c += PESOS["dependencia"]
            return c

        custo_horario = {(d, s): custo(
            d, s) for d in tarefa.dias_permitidos for s in tarefa.turnos_permitidos}
        horarios, custo_total, nos = _a_estrela(
            tarefa, custo_horario, usar_heuristica=True)
        _, _, nos_ucs = _a_estrela(
            tarefa, custo_horario, usar_heuristica=False)
        por_tarefa.append(PlanoTarefa(t, horarios, custo_total, nos, nos_ucs))
        escolhidos[t] = horarios
        for d, s in horarios:
            ocupacao[d, s] += 1
            esforco_dia[d] += tarefa.esforco
            turno_de[tarefa.nome, d] = s

    alinhado = [h for t in range(len(tarefas)) for h in escolhidos[t]]
    return PlanoSemana(alinhado, sum(p.custo for p in por_tarefa), time.perf_counter() - inicio, por_tarefa)