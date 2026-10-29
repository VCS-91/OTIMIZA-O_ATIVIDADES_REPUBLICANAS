=====================================================================
 SISTEMA INTELIGENTE DE GESTÃO E LOGÍSTICA DOMÉSTICA PARA REPÚBLICA
=====================================================================

Autores: Vinícius Cardoso de Souza, Vitor de Souza Leite, Gustavo Dias Miranda
Universidade Federal de Ouro Preto (UFOP) - Trabalho 1 de Inteligência Artificial


---------------------------------------------------------------------
1. OBJETIVO
---------------------------------------------------------------------

Desenvolver um sistema multiagente que automatize as decisões operacionais
de uma república. O sistema lida com três classes de problema:

  - alocar as tarefas domésticas sem conflito com a grade de aulas da UFOP
    e com o trabalho e os compromissos de cada integrante;
  - definir quando cada tarefa será executada ao longo da semana;
  - reagir aos imprevistos do dia a dia, recalculando a escala.

Cada classe de problema é resolvida por um agente com uma técnica de busca
diferente, conforme a proposta do trabalho:

  Busca Clássica -> define a melhor ordem (dia e turno) para executar as tarefas
  Busca Local    -> aloca os integrantes por prioridade e disponibilidade
  Busca Online   -> recalcula a escala de acordo com os imprevistos diários

Saída: uma tabela dinâmica, exibida numa interface gráfica e atualizada
diariamente de acordo com a situação dos integrantes.


---------------------------------------------------------------------
2. COMO EXECUTAR
---------------------------------------------------------------------

Requisitos: Python 3.10 ou superior, com tkinter (já vem com o instalador
oficial do Python no Windows). Não há dependências externas.

  python main.py                          abre a interface com dados simulados
  python main.py --forms respostas.csv    abre a interface com as respostas do Forms
  python main.py --sheets <link>          lê direto da planilha de respostas do Forms
  python main.py --texto                  imprime o plano e a escala no terminal
  python main.py --exemplo-csv saida.csv  gera um CSV de exemplo no formato do Forms


---------------------------------------------------------------------
3. ESTRUTURA DOS ARQUIVOS
---------------------------------------------------------------------

  main.py                      interface gráfica (tabela dinâmica) e linha de comando
  dados.py                     modelos de dados, dados simulados e leitura do Google Forms
  busca_classica.py            agente de Busca Clássica (A*)
  busca_local.py               agente de Busca Local (guloso + Simulated Annealing)
  busca_online.py              agente de Busca Online (replanejamento com imprevistos)
  exemplo_respostas_forms.csv  exemplo do formato das respostas do Forms

O fluxo do sistema é:

  Forms / dados simulados
        |
        v
  [Busca Clássica]  -> em que dia e turno acontece cada tarefa
        |
        v
  [Busca Local]     -> quem executa cada tarefa
        |
        v
  Tabela dinâmica (interface)  <---->  [Busca Online]  <- imprevistos do dia


---------------------------------------------------------------------
4. ETAPA 1 - MODELAGEM DO PROBLEMA (dados.py)
---------------------------------------------------------------------

4.1 Tempo
  A semana é dividida em 7 dias (segunda a domingo) e 3 turnos
  (manhã, tarde e noite), num total de 21 horários.

4.2 Integrantes
  Cada integrante tem:
    - nome;
    - nível hierárquico;
    - horários ocupados: pares (dia, turno) com aula, trabalho ou compromisso;
    - dias livres: dias em que não executa tarefa, mesmo estando disponível;
    - dias preferidos para fazer tarefas.

4.3 Hierarquia republicana
  Do maior para o menor nível:

    Nível 5 - Decano        até 2 dias livres
    Nível 4 - Vice-Decano   até 1 dia livre
    Nível 3 - Morador       até 1 dia livre
    Nível 2 - Semi-Bixo     nenhum dia livre
    Nível 1 - Calouro       nenhum dia livre

  A hierarquia é o limite do projeto e entra no sistema de duas formas:
    a) os dias livres, que só os níveis mais altos podem escolher, são
       restrição rígida: ninguém recebe tarefa no seu dia livre;
    b) colocar alguém fora dos seus dias preferidos é penalizado
       proporcionalmente ao nível. Por isso os integrantes de maior
       hierarquia têm prioridade na escolha do melhor dia.
  A quantidade de dias livres por nível fica na constante MAX_DIAS_LIVRES.

4.4 Tarefas
  Cada tarefa tem:
    - nome;
    - quantidade de vezes por semana;
    - esforço (peso de 1 a 5);
    - turnos e dias permitidos (ex.: o lixo só sai na segunda, quarta e
      sexta, à noite);
    - dependências: tarefas que, no mesmo dia, precisam vir antes
      (ex.: varrer antes de passar pano; lavar a louça antes de limpar
      o fogão).

  As tarefas cadastradas são lavar louça (7x), limpar fogão e bancada (2x),
  varrer a casa (3x), passar pano (2x), limpar banheiro (2x), levar o
  lixo (3x), lavar panos e toalhas, compras do mercado, limpar o quintal
  e organizar a geladeira (1x cada), num total de 23 ocorrências por semana.

4.5 Entrada de informações (Google Forms)
  O sistema foi preparado para receber as respostas de um Google Forms,
  mas por enquanto roda com dados simulados (7 integrantes com grades de
  aula fictícias). O Forms deve ter as perguntas:

    - Nome                     (resposta curta)
    - Hierarquia na república  (múltipla escolha: Decano / Vice-Decano /
                                Morador / Semi-Bixo / Calouro)
    - Horários ocupados        (grade de caixas de seleção: linhas = dias,
                                colunas = Manhã / Tarde / Noite)
    - Dias livres              (caixas de seleção com os dias)
    - Dias preferidos          (caixas de seleção com os dias)

  As respostas podem ser lidas de duas formas:
    a) arquivo CSV baixado da planilha de respostas
       (Arquivo > Fazer download > CSV);
    b) link da planilha, que deve estar compartilhada como "qualquer
       pessoa com o link pode ver". O sistema converte o link para o
       endereço de exportação em CSV.

  As colunas são reconhecidas por palavras-chave (nome, hierarquia, livre,
  prefer e o dia entre colchetes), então o texto exato das perguntas pode
  variar. Acentos e maiúsculas são ignorados. Se alguém responder mais de
  uma vez, vale a resposta mais recente. Se alguém pedir mais dias livres
  do que a hierarquia permite, ficam só os primeiros e o sistema emite
  um aviso.


---------------------------------------------------------------------
5. ETAPA 2 - BUSCA CLÁSSICA (busca_classica.py)
---------------------------------------------------------------------

Função: definir a melhor ordem de execução das tarefas, isto é, em que dia
e turno cada ocorrência acontece. Nesta etapa ainda não se escolhe quem
executa a tarefa.

5.1 Decomposição
  As tarefas são planejadas uma de cada vez, numa ordem fixa:
    1) primeiro os pré-requisitos (ex.: "Varrer a casa" antes de "Passar
       pano"), para que as dependências possam ser verificadas;
    2) depois as tarefas mais restritas, com menos horários possíveis por
       ocorrência (ex.: "Levar o lixo");
    3) em caso de empate, as de maior esforço.
  Cada tarefa planejada passa a ocupar os seus horários, o que influencia
  o custo das tarefas seguintes.

5.2 Formulação do problema de busca (para cada tarefa)
  Estado:   (ocorrências já marcadas, último dia usado)
  Inicial:  (0, nenhum)
  Ação:     marcar a próxima ocorrência num (dia, turno) posterior ao
            último dia usado, deixando dias suficientes para as restantes.
            Como os dias são sempre crescentes, a mesma tarefa nunca se
            repete no mesmo dia e não há permutações equivalentes.
  Objetivo: todas as ocorrências semanais da tarefa marcadas.
  Custo:    soma dos custos dos horários escolhidos:

    poucos disponíveis  10 x fração dos integrantes ocupados no turno
    turno cheio          6 por tarefa já marcada no mesmo turno
    esforço no dia       1 por ponto de esforço já marcado no mesmo dia
    espaçamento          4 x (intervalo entre repetições - intervalo ideal)²,
                         onde o intervalo ideal = 7 / vezes por semana
    dependência         50 se o pré-requisito não está no dia, ou está num
                         turno posterior
    sem ninguém       1000 se não sobra nenhum integrante livre no turno

5.3 Algoritmo: A*
  f(n) = g(n) + h(n), em que g(n) é o custo acumulado e
  h(n) = (ocorrências restantes) x (menor custo de horário possível).

  A heurística é admissível: cada ocorrência restante custará pelo menos o
  menor custo de horário, e o espaçamento nunca é negativo. Por isso o A*
  encontra a sequência de horários ótima para cada tarefa.

  Para comparação, o mesmo subproblema também é resolvido sem heurística
  (h = 0, ou seja, Busca de Custo Uniforme). A interface mostra os nós
  expandidos pelos dois. Com os dados simulados, o A* expande 37 nós e a
  busca de custo uniforme expande 41. A diferença é pequena porque cada
  tarefa tem poucas combinações de horário, e tende a crescer com mais
  tarefas e repetições.


---------------------------------------------------------------------
6. ETAPA 3 - BUSCA LOCAL (busca_local.py)
---------------------------------------------------------------------

Função: alocar os integrantes nas tarefas por prioridade, conforme a
disponibilidade de cada um (aulas, trabalho, hierarquia e outros
compromissos). O dia e o turno de cada ocorrência vêm da Busca Clássica.

6.1 Representação
  Um estado é a escala completa: uma lista de alocações
  (tarefa, integrante, dia, turno), uma por ocorrência.

6.2 Função de custo (a ser minimizada)

    indisponível   1000  tarefa em horário de aula/trabalho ou em dia livre (rígida)
    dia repetido   1000  mesma tarefa duas vezes no mesmo dia (rígida)
    choque           60  integrante com duas tarefas no mesmo turno
    dependência      40  pré-requisito ausente no dia ou em turno posterior
    dias seguidos    10  tarefa de até 3x/semana em dias consecutivos
    carga             4  soma dos (esforço do integrante - média)²
    preferência       3  x nível hierárquico, quando a tarefa cai fora
                         dos dias preferidos do integrante
    mudança          15  alteração em relação à escala anterior
                         (usado só pela Busca Online)

6.3 Algoritmo
  a) Solução inicial gulosa: as ocorrências com menos opções escolhem
     primeiro (heurística MRV, "mínimos valores restantes"); em caso de
     empate, as de maior esforço. Cada ocorrência recebe o integrante que
     gera o menor custo no momento.
  b) Refinamento por Simulated Annealing:
       - 15.000 iterações;
       - temperatura inicial 50, com resfriamento geométrico até 0,05;
       - três tipos de vizinho: trocar a alocação por outra opção
         qualquer do domínio (50%), trocar só o responsável (25%) e
         trocar os responsáveis de duas ocorrências (25%);
       - uma piora de custo delta é aceita com probabilidade exp(-delta/T),
         o que permite sair de mínimos locais.

  Com os dados simulados, o custo cai de cerca de 100 a 120 (solução
  gulosa) para cerca de 50 em menos de 1 segundo, sem nenhuma restrição
  rígida violada.


---------------------------------------------------------------------
7. ETAPA 4 - BUSCA ONLINE (busca_online.py)
---------------------------------------------------------------------

Função: recalcular a escala de acordo com os imprevistos diários.

Diferente da Busca Local, que planeja a semana inteira conhecendo todas as
informações, o agente online só conhece o que já aconteceu: ele decide à
medida que os eventos chegam, ao longo da semana.

7.1 Imprevistos tratados
  - Integrante indisponível: num turno ou no dia inteiro (prova, doença,
    viagem...). Os horários passam a constar como ocupados até o fim
    da semana.
  - Tarefa extra urgente: uma nova tarefa para um dia e, opcionalmente,
    um turno (ex.: limpar a casa depois de uma festa).
  - Tarefa não realizada: a tarefa fica marcada como não feita e uma
    repetição é criada para hoje ou para os próximos dias permitidos.

7.2 Replanejamento
  1) Os dias anteriores ao dia atual são travados e não mudam mais.
  2) Reparo: as ocorrências futuras que ficaram inviáveis e as novas
     ocorrências são realocadas pelo mesmo procedimento guloso da Busca
     Local. Aqui o domínio inclui também o dia e o turno, então a tarefa
     pode mudar de horário, e não só de responsável.
  3) Ajuste fino: um Simulated Annealing curto e "frio" (3.000 iterações,
     temperatura inicial 5). A função de custo inclui a penalidade de
     "mudança", então o agente prefere alterar o mínimo possível a escala
     de quem não foi afetado.
  4) As alterações são registradas no histórico e destacadas na tabela.

  Há também um botão "Imprevisto aleatório", que sorteia um imprevisto
  plausível para simular a semana.


---------------------------------------------------------------------
8. ETAPA 5 - INTERFACE / SAÍDA (main.py)
---------------------------------------------------------------------

A interface foi feita em tkinter e tem quatro abas:

  Escala semanal
    A tabela dinâmica, com integrantes nas linhas e dias nas colunas. Cada
    célula mostra as tarefas e os turnos (M/T/N) do integrante naquele dia.
    Cores:
      cinza    dia livre
      vermelho conflito com horário
      amarelo  célula alterada pela Busca Online
      azul     dia de hoje
    Os dias que já passaram aparecem em cinza claro.
    Marcas: ★ tarefa extra; ✗ tarefa não realizada.

  Plano da semana (Busca Clássica)
    Grade turno x dia com as tarefas de cada horário e o número de
    integrantes disponíveis. Abaixo, para cada tarefa, os horários
    escolhidos, o custo e os nós expandidos pelo A* e pela busca de
    custo uniforme.

  Integrantes e Busca Local
    Dados de cada integrante (hierarquia, dias livres e preferidos, turnos
    ocupados, número de tarefas e esforço total). Mostra também o custo
    da solução gulosa e do Simulated Annealing, e cada componente da
    função de custo.

  Imprevistos (Busca Online)
    Histórico de tudo o que aconteceu: escalas geradas, imprevistos e cada
    alteração feita ("tarefa: responsável/dia antigo -> novo").

Botões da barra superior:
  - Dados simulados / Importar CSV do Forms / Importar do Google Planilhas
  - Gerar nova escala   (roda a Busca Clássica e a Busca Local de novo)
  - Registrar imprevisto / Imprevisto aleatório   (aciona a Busca Online)
  - Avançar dia   (passa para o dia seguinte; no fim do domingo, uma nova
                   semana é planejada)

Atualização diária: a escala começa no dia da semana atual. Se o programa
ficar aberto quando a data mudar, ele avança o dia automaticamente (a data
é verificada a cada minuto).


---------------------------------------------------------------------
9. HISTÓRICO DE DESENVOLVIMENTO
---------------------------------------------------------------------

  1) Leitura da proposta (objetivo, entrada, limites e papel de cada busca)
     e divisão do código em main.py, busca_classica.py, busca_local.py e
     busca_online.py. O arquivo dados.py foi criado para concentrar os
     modelos compartilhados e evitar importações circulares.
  2) Decisões iniciais: usar dados simulados por enquanto, deixando a
     leitura do Google Forms (CSV ou link da planilha) já pronta, e fazer
     a saída numa interface gráfica.
  3) Primeira versão: a Busca Local escolhia o integrante, o dia e o turno,
     e a Busca Clássica ordenava as tarefas de cada dia minimizando o
     deslocamento numa planta da casa.
  4) Revisão: a hierarquia passou a ter cinco níveis (Decano, Vice-Decano,
     Morador, Semi-Bixo, Calouro). A planta e as distâncias foram removidas,
     porque não fazem parte da proposta e não há planta real da casa.
     A Busca Clássica passou a distribuir as tarefas na semana (dia e
     turno), e a Busca Local passou a escolher apenas os responsáveis.
     Os papéis de cada agente ficaram separados.
  5) Ajuste: a penalidade de dependência passou a valer igual nas três
     buscas (pré-requisito ausente no dia ou em turno posterior).

Testes realizados: execução no modo texto; geração do CSV de exemplo e
importação dele de volta; simulação de várias semanas com imprevistos
aleatórios e manuais, verificando que a escala final não viola nenhuma
restrição rígida.


---------------------------------------------------------------------
10. LIMITAÇÕES E PONTOS EM ABERTO
---------------------------------------------------------------------

  - Os integrantes, as grades de aula e a lista de tarefas são simulados.
    As tarefas reais da república devem ser ajustadas em
    dados.tarefas_padrao().
  - Os pesos das funções de custo e a quantidade de dias livres por nível
    foram definidos de forma empírica e podem ser recalibrados (PESOS em
    busca_classica.py e busca_local.py; MAX_DIAS_LIVRES em dados.py).
  - A Busca Clássica é ótima para cada tarefa, dada a ordem de
    planejamento, mas não necessariamente para a semana inteira de uma
    vez.
  - Os imprevistos valem só para a semana corrente. Ao gerar uma nova
    semana, valem de novo os dados originais do Forms.
