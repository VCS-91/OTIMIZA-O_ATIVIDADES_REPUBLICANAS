"""Busca Local: aloca os integrantes nas tarefas da semana.

A busca clássica já definiu o dia e o turno de cada ocorrência de tarefa (ex.: a 2ª
vez que a casa é varrida na semana); aqui se escolhe quem faz cada uma, conforme a
disponibilidade (aulas, trabalho, compromissos, dias livres) e a hierarquia. Uma
solução gulosa inicial, em que cada ocorrência pega o integrante mais barato no
momento, é refinada por Simulated Annealing, minimizando a função de custo dos PESOS.

Sem horários definidos (caso da busca online), o domínio de cada ocorrência volta a
ser (integrante, dia, turno), e a mesma busca também pode mover a tarefa de horário.

A hierarquia entra no custo de duas formas: os dias livres escolhidos pelos mais
velhos são restrição rígida, e sair dos dias preferidos de alguém custa mais
quanto maior a hierarquia dessa pessoa (ela tem prioridade para escolher o dia).
"""
from __future__ import annotations

import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from dados import Integrante, Tarefa

# Pesos da função de custo. Os de 1000 são restrições rígidas.
PESOS = {
    "indisponivel": 1000,  # aula, trabalho, compromisso ou dia livre
    "dia_repetido": 1000,  # mesma tarefa duas vezes no mesmo dia
    "choque": 60,          # integrante com duas tarefas no mesmo turno
    "dependencia": 40,     # ex.: passar pano num dia sem varrer, ou num turno anterior
    "dias_seguidos": 10,   # tarefa de poucas vezes por semana em dias consecutivos
    "carga": 4,            # desequilíbrio de esforço entre integrantes (soma dos desvios²)
    "preferencia": 3,      # fora dos dias preferidos (multiplicado pelo nível hierárquico)
    "mudanca": 15,         # alteração em relação à escala anterior (usado pela busca online)
}

Alocacao = tuple[int, int, int, int]  # (tarefa, integrante, dia, turno)


class ProblemaEscala:
    def __init__(self, integrantes: list[Integrante], tarefas: list[Tarefa],
                 fixos: set[int] = frozenset(), dia_minimo: int = 0,
                 referencia: list[Alocacao | None] | None = None,
                 horarios: list[tuple[int, int]] | None = None):
        self.integrantes = integrantes
        self.tarefas = tarefas
        self.fixos = set(fixos)          # ocorrências que não podem ser mexidas
        self.dia_minimo = dia_minimo     # não aloca nada antes deste dia
        self.referencia = referencia     # escala anterior, para medir mudanças
        self.horarios = horarios         # (dia, turno) de cada ocorrência, vindos da busca clássica
        self._dependencias = {t.nome: t.depende_de for t in tarefas}
        self._dominios: dict[tuple[int, int], list[tuple[int, int, int]]] = {}

    def ocorrencias(self) -> list[int]:
        return [t for t, tarefa in enumerate(self.tarefas) for _ in range(tarefa.vezes_por_semana)]

    def dominio(self, k: int, t: int) -> list[tuple[int, int, int]]:
        """Todas as opções (integrante, dia, turno) para a ocorrência k, da tarefa t."""
        if self.horarios is not None and k < len(self.horarios):
            chave, horarios = (k, t), [self.horarios[k]]
        else:
            tarefa = self.tarefas[t]
            chave = (-1, t)
            horarios = [(d, s) for d in tarefa.dias_permitidos if d >= self.dia_minimo
                        for s in tarefa.turnos_permitidos]
        if chave not in self._dominios:
            self._dominios[chave] = [(i, d, s) for i in range(len(self.integrantes)) for d, s in horarios]
        return self._dominios[chave]

    def componentes(self, estado: list[Alocacao | None]) -> dict[str, float]:
        """Quantidade de cada tipo de violação (sem os pesos)."""
        c = dict.fromkeys(PESOS, 0.0)
        carga = [0] * len(self.integrantes)
        por_tarefa_dia = Counter()
        por_turno = Counter()
        turno_da_tarefa = {}
        dias_da_tarefa = defaultdict(set)
        for k, aloc in enumerate(estado):
            if aloc is None:
                continue
            t, i, d, s = aloc
            tarefa, pessoa = self.tarefas[t], self.integrantes[i]
            if not pessoa.disponivel(d, s):
                c["indisponivel"] += 1
            if pessoa.dias_preferidos and d not in pessoa.dias_preferidos:
                c["preferencia"] += pessoa.hierarquia
            carga[i] += tarefa.esforco
            por_tarefa_dia[t, d] += 1
            por_turno[i, d, s] += 1
            turno_da_tarefa[tarefa.nome, d] = s
            dias_da_tarefa[t].add(d)
            if self.referencia and k < len(self.referencia) and self.referencia[k] not in (None, aloc):
                c["mudanca"] += 1

        c["dia_repetido"] = sum(n - 1 for n in por_tarefa_dia.values())
        c["choque"] = sum(n - 1 for n in por_turno.values())
        for (nome, d), s in turno_da_tarefa.items():
            for dep in self._dependencias.get(nome, ()):
                # pré-requisito ausente nesse dia ou marcado num turno posterior
                if dep in self._dependencias and turno_da_tarefa.get((dep, d), math.inf) > s:
                    c["dependencia"] += 1
        for t, dias in dias_da_tarefa.items():
            tarefa = self.tarefas[t]
            if not tarefa.extra and tarefa.vezes_por_semana <= 3:
                c["dias_seguidos"] += sum(1 for d in dias if d + 1 in dias)
        media = sum(carga) / len(carga)
        c["carga"] = sum((x - media) ** 2 for x in carga)
        return c

    def custo(self, estado: list[Alocacao | None]) -> float:
        return sum(PESOS[k] * v for k, v in self.componentes(estado).items())

    def vizinho(self, estado: list[Alocacao], moveis: list[int], rng: random.Random) -> list[Alocacao]:
        novo = list(estado)
        k = rng.choice(moveis)
        t, i, d, s = novo[k]
        r = rng.random()
        if r < 0.5:    # nova opção qualquer do domínio
            novo[k] = (t, *rng.choice(self.dominio(k, t)))
        elif r < 0.75:  # troca só o responsável
            novo[k] = (t, rng.randrange(len(self.integrantes)), d, s)
        else:           # troca os responsáveis de duas ocorrências (os horários ficam)
            k2 = rng.choice(moveis)
            t2, i2, d2, s2 = novo[k2]
            novo[k], novo[k2] = (t, i2, d, s), (t2, i, d2, s2)
        return novo


def solucao_gulosa(problema: ProblemaEscala, estado: list[Alocacao | None],
                   pendentes: list[tuple[int, int]], rng: random.Random) -> list[Alocacao | None]:
    """Preenche as ocorrências pendentes (posição, tarefa), uma por vez, com a opção mais barata.

    Ocorrências com menos opções e mais esforço escolhem primeiro. Se não houver
    nenhuma opção (domínio vazio), a ocorrência continua sem responsável (None).
    """
    estado = list(estado)
    pendentes = list(pendentes)
    rng.shuffle(pendentes)
    pendentes.sort(key=lambda p: (len(problema.dominio(*p)), -problema.tarefas[p[1]].esforco))
    for k, t in pendentes:
        opcoes = list(problema.dominio(k, t))
        rng.shuffle(opcoes)
        melhor, melhor_custo = None, math.inf
        for opcao in opcoes:
            estado[k] = (t, *opcao)
            custo = problema.custo(estado)
            if custo < melhor_custo:
                melhor, melhor_custo = estado[k], custo
        estado[k] = melhor
    return estado


def simulated_annealing(problema: ProblemaEscala, estado: list[Alocacao | None], rng: random.Random,
                        iteracoes: int = 15000, temperatura: float = 50.0,
                        temperatura_final: float = 0.05) -> tuple[list[Alocacao | None], float]:
    moveis = [k for k, a in enumerate(estado)
              if a is not None and k not in problema.fixos and problema.dominio(k, a[0])]
    atual, custo_atual = list(estado), problema.custo(estado)
    melhor, custo_melhor = atual, custo_atual
    if not moveis:
        return melhor, custo_melhor
    resfriamento = (temperatura_final / temperatura) ** (1 / iteracoes)
    for _ in range(iteracoes):
        candidato = problema.vizinho(atual, moveis, rng)
        custo = problema.custo(candidato)
        delta = custo - custo_atual
        if delta <= 0 or rng.random() < math.exp(-delta / temperatura):
            atual, custo_atual = candidato, custo
            if custo < custo_melhor:
                melhor, custo_melhor = candidato, custo
        temperatura *= resfriamento
    return melhor, custo_melhor


@dataclass
class ResultadoLocal:
    estado: list[Alocacao | None]
    custo: float
    custo_inicial: float  # custo da solução gulosa, antes do Simulated Annealing
    componentes: dict[str, float]
    iteracoes: int
    tempo: float


def gerar_escala(integrantes: list[Integrante], tarefas: list[Tarefa], horarios: list[tuple[int, int]],
                 iteracoes: int = 15000, semente: int | None = None) -> ResultadoLocal:
    """Escolhe os responsáveis, com o dia e o turno de cada ocorrência já definidos em `horarios`."""
    rng = random.Random(semente)
    inicio = time.perf_counter()
    problema = ProblemaEscala(integrantes, tarefas, horarios=horarios)
    ocorrencias = problema.ocorrencias()
    estado = solucao_gulosa(problema, [None] * len(ocorrencias), list(enumerate(ocorrencias)), rng)
    custo_inicial = problema.custo(estado)
    estado, custo = simulated_annealing(problema, estado, rng, iteracoes)
    return ResultadoLocal(estado, custo, custo_inicial, problema.componentes(estado),
                          iteracoes, time.perf_counter() - inicio)
