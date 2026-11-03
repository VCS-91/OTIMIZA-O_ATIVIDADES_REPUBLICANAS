# Agente reativo para os imprevistos da semana (Busca Online).
# Congela o que já passou, aplica um reparo guloso no que quebrou e faz 
# um Simulated Annealing rápido pra não bagunçar muito a escala do resto da casa.
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, replace

from busca_local import Alocacao, ProblemaEscala, simulated_annealing, solucao_gulosa
from dados import DIAS, TURNOS, Integrante, Tarefa

TIPOS = {
    "indisponivel": "Integrante indisponível",
    "extra": "Tarefa extra urgente",
    "nao_realizada": "Tarefa não realizada",
}

EXTRAS_POSSIVEIS = [
    Tarefa("Limpar a casa depois do rock", 1, 3),
    Tarefa("Desentupir a pia", 1, 2),
    Tarefa("Receber o botijão de gás", 1, 1),
]


@dataclass
class Imprevisto:
    tipo: str
    dia: int
    turno: int | None = None             # None = dia inteiro / qualquer turno
    integrante: int | None = None        # indisponivel
    ocorrencia: int | None = None        # nao_realizada: posição na escala
    nova_tarefa: Tarefa | None = None    # extra

    def descricao(self, agente: AgenteOnline) -> str:
        dia = DIAS[self.dia]
        if self.tipo == "indisponivel":
            quando = "o dia todo" if self.turno is None else f"no turno da {TURNOS[self.turno].lower()}"
            return f"{agente.integrantes[self.integrante].nome} ficou indisponível na {dia} ({quando})"
        if self.tipo == "extra":
            return f"tarefa extra \"{self.nova_tarefa.nome}\" para {dia}"
        t, i, _, _ = agente.estado[self.ocorrencia]
        return f"{dia}: \"{agente.tarefas[t].nome}\" ({agente.integrantes[i].nome}) não foi feita"


@dataclass
class Mudanca:
    ocorrencia: int
    antes: Alocacao | None
    depois: Alocacao | None


class AgenteOnline:
    def __init__(self, integrantes: list[Integrante], tarefas: list[Tarefa],
                 estado: list[Alocacao | None], dia_atual: int):
        # Cópias: os imprevistos valem só para a semana corrente.
        self.integrantes = copy.deepcopy(integrantes)
        self.tarefas = list(tarefas)
        self.estado = list(estado)
        self.dia_atual = dia_atual
        # ocorrências mexidas nesta semana
        self.alteradas: set[int] = set()
        self.nao_realizadas: set[int] = set()
        self.historico: list[tuple[Imprevisto, list[Mudanca]]] = []
        self._pendentes: list[tuple[int, int]] = []

    def registrar(self, imp: Imprevisto, rng: random.Random | None = None) -> list[Mudanca]:
        rng = rng or random.Random()
        if imp.tipo == "indisponivel":
            turnos = range(len(TURNOS)) if imp.turno is None else [imp.turno]
            self.integrantes[imp.integrante].ocupados.update(
                (imp.dia, s) for s in turnos)
        elif imp.tipo == "extra":
            self._nova_ocorrencia(imp.nova_tarefa)
        elif imp.tipo == "nao_realizada":
            self.nao_realizadas.add(imp.ocorrencia)
            base = self.tarefas[self.estado[imp.ocorrencia][0]]
            dias = tuple(d for d in base.dias_permitidos if d >= self.dia_atual) \
                or tuple(range(self.dia_atual, 7))
            self._nova_ocorrencia(
                replace(base, vezes_por_semana=1, dias_permitidos=dias, extra=True))
        mudancas = self.replanejar(rng)
        self.historico.append((imp, mudancas))
        return mudancas

    def _nova_ocorrencia(self, tarefa: Tarefa) -> None:
        self.tarefas.append(tarefa)
        self.estado.append(None)
        self._pendentes.append((len(self.estado) - 1, len(self.tarefas) - 1))

    def replanejar(self, rng: random.Random) -> list[Mudanca]:
        anterior = list(self.estado)
        fixos = {k for k, a in enumerate(
            self.estado) if a is not None and a[2] < self.dia_atual}
        problema = ProblemaEscala(
            self.integrantes, self.tarefas, fixos, self.dia_atual, anterior)

        # 1) reparo: ocorrências futuras que ficaram inviáveis voltam a ser pendentes
        pendentes, self._pendentes = self._pendentes, []
        for k, a in enumerate(self.estado):
            if a is not None and k not in fixos and not self.integrantes[a[1]].disponivel(a[2], a[3]):
                pendentes.append((k, a[0]))
                self.estado[k] = None
        estado = solucao_gulosa(problema, self.estado, pendentes, rng)

        # 2) ajuste fino com poucas iterações e temperatura baixa
        estado, _ = simulated_annealing(
            problema, estado, rng, iteracoes=3000, temperatura=5.0)
        self.estado = estado

        mudancas = [Mudanca(k, anterior[k], estado[k])
                    for k in range(len(estado)) if anterior[k] != estado[k]]
        self.alteradas.update(m.ocorrencia for m in mudancas)
        return mudancas

    def imprevisto_aleatorio(self, rng: random.Random) -> Imprevisto:
        """Sorteia um imprevisto plausível para hoje/amanhã (usado para simular a semana)."""
        hoje = self.dia_atual
        tipo = rng.choice(list(TIPOS))
        if tipo == "nao_realizada":
            feitas_hoje = [k for k, a in enumerate(self.estado)
                           if a is not None and a[2] == hoje and k not in self.nao_realizadas]
            if feitas_hoje:
                return Imprevisto(tipo, hoje, ocorrencia=rng.choice(feitas_hoje))
            tipo = "extra"
        if tipo == "extra":
            base = rng.choice(EXTRAS_POSSIVEIS)
            return Imprevisto(tipo, hoje, nova_tarefa=replace(base, dias_permitidos=(hoje,), extra=True))
        # indisponível justamente quando tinha tarefa, para forçar o replanejamento
        proximas = [
            a for a in self.estado if a is not None and hoje <= a[2] <= hoje + 1]
        if proximas:
            _, i, d, s = rng.choice(proximas)
            return Imprevisto(tipo, d, rng.choice([s, None]), integrante=i)
        return Imprevisto(tipo, hoje, None, integrante=rng.randrange(len(self.integrantes)))