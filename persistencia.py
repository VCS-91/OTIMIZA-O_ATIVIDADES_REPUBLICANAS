# Salva e recupera o estado do painel num arquivo JSON, para a escala, os
# imprevistos, as tarefas concluídas e o pingômetro sobreviverem ao fechar o programa.
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from busca_classica import PlanoSemana, PlanoTarefa
from busca_local import ResultadoLocal
from busca_online import AgenteOnline, Imprevisto, Mudanca
from dados import Integrante, Tarefa

VERSAO = 1
ARQUIVO_PADRAO = Path(__file__).with_name("estado_republica.json")


# ---------------------------------------------------------------- conversões

def _aloc(a):
    return None if a is None else list(a)


def _aloc_de(a):
    return None if a is None else tuple(a)


def integrante_para_dict(p: Integrante) -> dict:
    return {"nome": p.nome, "hierarquia": p.hierarquia,
            "ocupados": sorted([d, s] for d, s in p.ocupados),
            "dias_livres": sorted(p.dias_livres),
            "dias_preferidos": sorted(p.dias_preferidos)}


def integrante_de_dict(d: dict) -> Integrante:
    return Integrante(d["nome"], d["hierarquia"], {tuple(x) for x in d["ocupados"]},
                      set(d["dias_livres"]), set(d["dias_preferidos"]))


def tarefa_para_dict(t: Tarefa) -> dict:
    return {"nome": t.nome, "vezes_por_semana": t.vezes_por_semana, "esforco": t.esforco,
            "turnos_permitidos": list(t.turnos_permitidos),
            "dias_permitidos": list(t.dias_permitidos),
            "depende_de": list(t.depende_de), "extra": t.extra}


def tarefa_de_dict(d: dict) -> Tarefa:
    return Tarefa(d["nome"], d["vezes_por_semana"], d["esforco"], tuple(d["turnos_permitidos"]),
                  tuple(d["dias_permitidos"]), tuple(d["depende_de"]), d["extra"])


def plano_para_dict(p: PlanoSemana) -> dict:
    return {"horarios": [list(h) for h in p.horarios], "custo": p.custo, "tempo": p.tempo,
            "custo_inicial": p.custo_inicial, "rodadas": p.rodadas,
            "por_tarefa": [{"tarefa": x.tarefa, "horarios": [list(h) for h in x.horarios],
                            "custo": x.custo, "nos_expandidos": x.nos_expandidos,
                            "nos_sem_heuristica": x.nos_sem_heuristica} for x in p.por_tarefa]}


def plano_de_dict(d: dict) -> PlanoSemana:
    por_tarefa = [PlanoTarefa(x["tarefa"], [tuple(h) for h in x["horarios"]], x["custo"],
                              x["nos_expandidos"], x["nos_sem_heuristica"]) for x in d["por_tarefa"]]
    return PlanoSemana([tuple(h) for h in d["horarios"]], d["custo"], d["tempo"], por_tarefa,
                       d.get("custo_inicial", d["custo"]), d.get("rodadas", 0))


def resultado_para_dict(r: ResultadoLocal) -> dict:
    return {"estado": [_aloc(a) for a in r.estado], "custo": r.custo,
            "custo_inicial": r.custo_inicial, "componentes": r.componentes,
            "iteracoes": r.iteracoes, "tempo": r.tempo}


def resultado_de_dict(d: dict) -> ResultadoLocal:
    return ResultadoLocal([_aloc_de(a) for a in d["estado"]], d["custo"], d["custo_inicial"],
                          d["componentes"], d["iteracoes"], d["tempo"])


def _imprevisto_para_dict(imp: Imprevisto) -> dict:
    return {"tipo": imp.tipo, "dia": imp.dia, "turno": imp.turno, "integrante": imp.integrante,
            "ocorrencia": imp.ocorrencia,
            "nova_tarefa": tarefa_para_dict(imp.nova_tarefa) if imp.nova_tarefa else None}


def _imprevisto_de_dict(d: dict) -> Imprevisto:
    nova = tarefa_de_dict(d["nova_tarefa"]) if d["nova_tarefa"] else None
    return Imprevisto(d["tipo"], d["dia"], d["turno"], d["integrante"], d["ocorrencia"], nova)


def agente_para_dict(ag: AgenteOnline) -> dict:
    return {"integrantes": [integrante_para_dict(p) for p in ag.integrantes],
            "tarefas": [tarefa_para_dict(t) for t in ag.tarefas],
            "estado": [_aloc(a) for a in ag.estado],
            "dia_atual": ag.dia_atual,
            "alteradas": sorted(ag.alteradas),
            "nao_realizadas": sorted(ag.nao_realizadas),
            "historico": [{"imprevisto": _imprevisto_para_dict(imp),
                           "mudancas": [{"ocorrencia": m.ocorrencia, "antes": _aloc(m.antes),
                                         "depois": _aloc(m.depois)} for m in mudancas]}
                          for imp, mudancas in ag.historico]}


def agente_de_dict(d: dict) -> AgenteOnline:
    ag = AgenteOnline([integrante_de_dict(x) for x in d["integrantes"]],
                      [tarefa_de_dict(x) for x in d["tarefas"]],
                      [_aloc_de(a) for a in d["estado"]], d["dia_atual"])
    ag.alteradas = set(d["alteradas"])
    ag.nao_realizadas = set(d["nao_realizadas"])
    ag.historico = [(_imprevisto_de_dict(h["imprevisto"]),
                     [Mudanca(m["ocorrencia"], _aloc_de(m["antes"]), _aloc_de(m["depois"]))
                      for m in h["mudancas"]])
                    for h in d["historico"]]
    return ag


# ---------------------------------------------------------------- arquivo

def salvar(estado: dict, caminho: str | Path = ARQUIVO_PADRAO) -> None:
    """Grava num arquivo temporário e depois troca, para nunca deixar o JSON pela metade."""
    caminho = Path(caminho)
    fd, temporario = tempfile.mkstemp(
        dir=caminho.parent, prefix=".estado_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"versao": VERSAO, **estado}, f, ensure_ascii=False, indent=1)
        os.replace(temporario, caminho)
    except BaseException:
        try:
            os.remove(temporario)
        except OSError:
            pass
        raise


def carregar(caminho: str | Path = ARQUIVO_PADRAO) -> dict | None:
    """Devolve o estado salvo, ou None se ainda não existe nenhum."""
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        estado = json.load(f)
    if estado.get("versao") != VERSAO:
        raise ValueError(
            f"arquivo de versão {estado.get('versao')}, esperado {VERSAO}")
    return estado
