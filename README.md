#  SISTEMA INTELIGENTE DE GESTÃO E LOGÍSTICA DOMÉSTICA PARA REPÚBLICA

**Autores:** Vinícius Cardoso de Souza, Vitor de Souza Leite, Gustavo Dias Miranda  
**Instituição:** Universidade Federal de Ouro Preto (UFOP) - Projeto Prático 1 de Inteligência Artificial

---

##  1. OBJETIVO

Desenvolver um sistema multiagente que automatize as decisões operacionais de uma república. O sistema lida com três classes de problema:

*   Alocar as tarefas sem conflito com a grade de aulas da UFOP e com o trabalho e os compromissos de cada integrante.
*   Definir quando cada tarefa será executada ao longo da semana.
*   Reagir aos imprevistos do dia a dia, recalculando a escala.

Cada classe de problema é resolvida por um agente com uma técnica de busca diferente, conforme a proposta do trabalho:

*   **Busca Clássica**: Define a melhor ordem para executar as tarefas.
*   **Busca Local**: Aloca os integrantes por prioridade e disponibilidade.
*   **Busca Online**: Recalcula a escala de acordo com os imprevistos diários.

**Saída:** uma tabela dinâmica, exibida numa interface gráfica e atualizada diariamente de acordo com a situação dos integrantes.

---

##  2. COMO EXECUTAR

**Requisitos:** Python 3.10 ou superior, com `tkinter`. Não há dependências externas.

No terminal, execute o comando abaixo:

```bash
# abre a interface com dados simulados
python main.py
```

---

## 3. ESTRUTURA DOS ARQUIVOS

*   `main.py`: Interface gráfica e linha de comando.
*   `dados.py`: Modelos de dados, dados simulados e leitura do Google Forms.
*   `busca_classica.py`: Agente de Busca Clássica.
*   `busca_local.py`: Agente de Busca Local.
*   `busca_online.py`: Agente de Busca Online.
*   `exemplo_respostas_forms.csv`: Exemplo do formato das respostas do Forms.

##  4. ETAPA 1 - MODELAGEM DO PROBLEMA (`dados.py`)

### 4.1 Tempo
A semana é dividida em 7 dias e 3 turnos, num total de 21 horários.

### 4.2 Integrantes
Cada integrante tem:
*   Nome.
*   Nível hierárquico.
*   Horários ocupados:Com aula, trabalho ou compromisso.
*   Dias livres: Dias em que não executa tarefa, mesmo estando disponível.
*   Dias preferidos para fazer tarefas.

### 4.3 Hierarquia Republicana
Do maior para o menor nível:
*   **Nível 5 - Decano:** até 2 dias livres
*   **Nível 4 - Vice-Decano:** até 1 dia livre
*   **Nível 3 - Morador:** até 1 dia livre
*   **Nível 2 - Semi-Bixo:** nenhum dia livre
*   **Nível 1 - Calouro:** nenhum dia livre

A hierarquia é o limite do projeto e entra no sistema de duas formas:
a) Os dias livres, que só os níveis mais altos podem escolher, são restrição rígida, ninguém recebe tarefa no seu dia livre.
b) Colocar alguém fora dos seus dias preferidos é penalizado proporcionalmente ao nível. Por isso os integrantes de maior hierarquia têm prioridade na escolha do melhor dia. A quantidade de dias livres por nível fica na constante `MAX_DIAS_LIVRES`.

### 4.4 Tarefas
Cada tarefa tem nome, quantidade de vezes por semana, esforço, turnos e dias permitidos, e dependências. 
As tarefas cadastradas totalizam 23 ocorrências por semana.

### 4.5 Entrada de informações (Google Forms)
O sistema recebe as respostas via CSV ou Link Público. As colunas são reconhecidas por palavras-chave (nome, hierarquia, livre, prefer e o dia entre colchetes).

---

##  5. ETAPA 2 - BUSCA CLÁSSICA (`busca_classica.py`)

**Função:** definir a melhor ordem de execução das tarefas.

### 5.1 Decomposição
As tarefas são planejadas uma de cada vez, numa ordem fixa:
1.  Pré-requisitos primeiro.
2.  Tarefas mais restritas.
3.  Em caso de empate, as de maior esforço.

### 5.2 Formulação do problema de busca
*   **Estado:** Ocorrências já marcadas, último dia usado.
*   **Ação:** Marcar a próxima ocorrência num (dia, turno) posterior ao último dia usado.
*   **Objetivo:** Todas as ocorrências semanais da tarefa marcadas.
*   **Custo:** Soma dos custos dos horários escolhidos.

### 5.3 Algoritmo: A*
`f(n) = g(n) + h(n)`
A heurística é admissível: cada ocorrência restante custará pelo menos o menor custo de horário, e o espaçamento nunca é negativo. O A* encontra a sequência ótima.

---

##  6. ETAPA 3 - BUSCA LOCAL (`busca_local.py`)

**Função:** Alocar os integrantes nas tarefas por prioridade e disponibilidade.

*   **Representação:** Um estado é a escala completa.
*   **Função de Custo:** Penaliza integrante indisponível (1000 - rígida), dia repetido (1000 - rígida), choques (60), dependências (40), dias seguidos (10), desequilíbrio de carga (4), preferências (3) e mudanças (15).
*   **Algoritmo:** Solução inicial gulosa (heurística MRV) refinada por **Simulated Annealing** (15.000 iterações, temperatura inicial 50, resfriamento geométrico até 0,05). Permite sair de mínimos locais.

---

##  7. ETAPA 4 - BUSCA ONLINE (`busca_online.py`)

**Função:** Recalcular a escala de acordo com os imprevistos diários.

*   **Imprevistos:** Integrante indisponível, Tarefa extra urgente, Tarefa não realizada.
*   **Replanejamento:** 
    1. Trava os dias anteriores.
    2. Reparo guloso nas tarefas afetadas.
    3. Ajuste fino com Simulated Annealing curto e "frio". Prefere alterar o mínimo possível a escala de quem não foi afetado.

---

##  8. ETAPA 5 - INTERFACE / SAÍDA (`main.py`)

A interface foi feita em `tkinter` e tem quatro abas principais:
*   **Escala Semanal:** A tabela dinâmica, com integrantes nas linhas e dias nas colunas. Mostra dias livres, conflitos, alterações e check-in.
*   **Plano da Semana:** Métricas da Busca Clássica (comparação de nós do A* e Custo Uniforme).
*   **Integrantes e Busca Local:** Dados de cada morador, termômetro de esforço e balanço da função de custo do Simulated Annealing.
*   **Imprevistos:** Histórico de tudo o que rolou (escala original e alterações feitas online).

Atualização diária: a escala começa no dia da semana atual. Se o programa ficar aberto quando a data mudar, ele avança o dia automaticamente.

---

##  9. HISTÓRICO DE DESENVOLVIMENTO

1.  Leitura da proposta e divisão arquitetural dos agentes em arquivos separados (`main`, `classica`, `local`, `online`, `dados`).
2.  Decisão de usar o Google Forms preparado.
3.  Primeira versão com deslocamento físico removida para focar apenas em dias e turnos.
4.  Implementação da hierarquia oficial de repúblicas.
5.  Separação dos papéis de cada agente garantida. Testes extensivos realizados verificando ausência de violações rígidas.

---

##  10. LIMITAÇÕES E PONTOS EM ABERTO

*   Os integrantes, as grades de aula e a lista de tarefas padrão são simulados.
*   Os pesos das funções de custo e a quantidade de dias livres por nível foram definidos de forma empírica e podem ser recalibrados (`PESOS` e `MAX_DIAS_LIVRES`).
*   A Busca Clássica é ótima para cada tarefa individualmente, dada a ordem de planejamento, mas não necessariamente para a semana inteira de uma vez.
*   Os imprevistos valem só para a semana corrente. Ao gerar uma nova semana, o sistema puxa de novo os dados originais do Forms.
