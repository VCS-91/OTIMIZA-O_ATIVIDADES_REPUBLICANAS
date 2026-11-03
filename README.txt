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

  python main.py                          abre a interface (retoma a escala salva, se houver)
  python main.py --forms respostas.csv    abre a interface com as respostas do Forms
  python main.py --sheets <link>          lê direto da planilha de respostas do Forms
  python main.py --novo                   ignora a escala salva e começa do zero
  python main.py --texto                  imprime o plano e a escala no terminal
  python main.py --exemplo-csv saida.csv  gera um CSV de exemplo no formato do Forms

Para enviar as alterações ao GitHub (commit + pull + push), dê dois
cliques em atualizar_github.bat, ou rode no terminal, na pasta do projeto:
  .\atualizar_github.bat "mensagem do commit"

A escala fica salva no arquivo estado_republica.json, na pasta do projeto
(veja a seção 8). Com --forms ou --sheets, a escala salva só é retomada se
tiver vindo da mesma fonte; se a fonte for outra, começa uma escala nova.


---------------------------------------------------------------------
3. ESTRUTURA DOS ARQUIVOS
---------------------------------------------------------------------

  main.py                      interface gráfica (tabela dinâmica) e linha de comando
  dados.py                     modelos de dados, dados simulados e leitura do Google Forms
  busca_classica.py            agente de Busca Clássica (A*)
  busca_local.py               agente de Busca Local (guloso + Simulated Annealing)
  busca_online.py              agente de Busca Online (replanejamento com imprevistos)
  persistencia.py              salva e recupera a escala (estado_republica.json)
  atualizar_github.bat         faz commit e envia as alterações para o GitHub
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
    - dependências: tarefas que, no mesmo dia, precisam vir antes, num
      turno anterior (ex.: varrer antes de passar pano; lavar a louça
      antes de limpar o fogão). Como o pré-requisito fica sempre num turno
      anterior, a ordem de execução dentro do dia fica explícita na escala.

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

5.1 Decomposição e refino
  Buscar a semana inteira de uma vez não é viável: são 23 ocorrências, cada
  uma com até 21 horários. Por isso o problema é dividido por tarefa, em
  duas fases.

  1ª passada: as tarefas são planejadas uma de cada vez, numa ordem fixa:
    1) primeiro os pré-requisitos (ex.: "Varrer a casa" antes de "Passar
       pano"), para que as dependências possam ser verificadas;
    2) depois as tarefas mais restritas, com menos horários possíveis por
       ocorrência (ex.: "Levar o lixo");
    3) em caso de empate, as de maior esforço.
  Cada tarefa planejada passa a ocupar os seus horários, o que influencia
  o custo das tarefas seguintes.

  Refino: depois da 1ª passada, cada tarefa é replanejada pelo A* vendo
  a semana inteira. O que é e por que foi feito está na seção 5.5.

5.2 Formulação do problema de busca (para cada tarefa)
  Estado:   (ocorrências já marcadas, último dia usado)
  Inicial:  (0, nenhum)
  Ação:     marcar a próxima ocorrência num (dia, turno) posterior ao
            último dia usado, deixando dias suficientes para as restantes.
            Como os dias são sempre crescentes, a mesma tarefa nunca se
            repete no mesmo dia e não há permutações equivalentes.
  Objetivo: todas as ocorrências semanais da tarefa marcadas.
  Custo:    soma dos custos dos horários escolhidos ("outras tarefas" são
            as já planejadas na 1ª passada, ou todas as demais no refino):

    poucos disponíveis  10 x fração dos integrantes ocupados no turno
    turno cheio          6 por outra tarefa marcada no mesmo turno
    esforço no dia     0,5 x esforço da tarefa x esforço das outras
                         tarefas marcadas no mesmo dia
    espaçamento          4 x (intervalo entre repetições - intervalo ideal)²,
                         onde o intervalo ideal = 7 / vezes por semana
    dependência         50 se o pré-requisito não está no dia, ou está no
                         mesmo turno ou num turno posterior; no refino, vale
                         também para o pré-requisito que não "cobre" a
                         tarefa que depende dele
    sem ninguém       1000 se não sobra nenhum integrante livre no turno

  O custo global da semana soma os mesmos termos contando cada par de
  tarefas uma vez só (turno cheio e esforço no dia são custos por par).
  Na interface, o custo de cada tarefa é o quanto ela acrescenta ao custo
  global, na ordem de planejamento; a soma da coluna é o custo global.

5.3 Algoritmo: A*
  f(n) = g(n) + h(n), em que g(n) é o custo acumulado e
  h(n) = (ocorrências restantes) x (menor custo de horário possível).

  A heurística é admissível: cada ocorrência restante custará pelo menos o
  menor custo de horário, e o espaçamento nunca é negativo. Por isso o A*
  encontra a sequência de horários ótima para cada tarefa.

  Para comparação, o mesmo subproblema também é resolvido sem heurística
  (h = 0, ou seja, Busca de Custo Uniforme). A interface mostra os nós
  expandidos pelos dois, somando a 1ª passada e o refino. Com os dados
  simulados, o A* expande 90 nós e a busca de custo uniforme expande 111.
  A diferença é pequena porque cada tarefa tem poucas combinações de
  horário, e tende a crescer com mais tarefas e repetições.

5.4 Garantia de otimalidade
  - Para cada tarefa, com as outras fixas, o A* é ótimo (heurística
    admissível).
  - Para a semana inteira, o resultado é um ótimo local: nenhuma tarefa
    consegue diminuir o custo global mudando sozinha os seus horários.
    Não é garantido que seja o ótimo global, que exigiria buscar todas as
    tarefas juntas, num espaço grande demais.

5.5 Refino da semana: o que é e por que foi feito
  O que é
    O refino é uma segunda fase da Busca Clássica, executada depois que
    todas as tarefas já receberam dia e turno na 1ª passada. Ele funciona
    assim:
      1) pega uma tarefa e "apaga" os horários dela, deixando todas as
         outras tarefas da semana fixas no lugar;
      2) roda o A* de novo para essa tarefa, agora levando em conta a
         semana inteira (inclusive as tarefas planejadas depois dela);
      3) se o novo plano deixar o custo global da semana menor, ele
         substitui o antigo; se não, o antigo é mantido;
      4) faz isso para todas as tarefas. Essa volta completa é uma
         "rodada". As rodadas se repetem até uma rodada inteira passar
         sem nenhuma melhora (no máximo 10 rodadas).
    É a mesma ideia da "descida por coordenadas": melhorar uma parte do
    problema por vez, com o resto parado, até nenhuma parte melhorar.

  Por que foi feito
    Na 1ª passada, cada tarefa só "enxerga" as tarefas planejadas antes
    dela. A primeira tarefa da ordem escolhe os horários com a semana
    vazia, sem saber que depois virão outras tarefas disputando os mesmos
    turnos. Exemplo: "Varrer a casa" é planejada antes de "Passar pano" e
    pode ocupar um turno que seria melhor para outra tarefa, porque ainda
    não sabe que esse turno vai ficar cheio. Depois de marcada, ela nunca
    mais era revista. O resultado dependia muito da ordem de planejamento,
    e o A* garantia o ótimo de cada tarefa isolada, mas não um bom plano
    para a semana. O refino corrige isso: cada tarefa ganha a chance de
    rever a sua escolha sabendo onde todas as outras ficaram.

  Por que ele nunca piora a semana
    O custo de cada horário usado pelo A* foi reformulado para ser
    exatamente o quanto o custo global da semana aumenta quando a tarefa
    é colocada ali (a menos de uma constante, que não muda a escolha).
    Para isso, foram feitas duas mudanças:
      - o termo "esforço no dia" passou a ser calculado por par de tarefas
        (esforço de uma x esforço da outra), para valer o mesmo não importa
        qual das duas é planejada primeiro;
      - uma tarefa que é pré-requisito passou a "ver" quem depende dela
        (ex.: "Varrer a casa" sabe em que dias e turnos está o "Passar
        pano" e prefere ficar num turno anterior a ele).
    Com isso, o melhor caminho que o A* encontra para uma tarefa é também
    a melhor escolha para a semana, com as outras fixas. Como só se aceita
    troca que diminui o custo global, cada rodada melhora a semana ou
    mantém como está, e o processo sempre termina.

  Resultado com os dados simulados
    Custo global da semana: 173,5 na 1ª passada e 166,5 depois de 2
    rodadas de refino. Com esse esqueleto melhor, o custo da escala final
    (Busca Local) caiu de cerca de 48 para 27. A aba "Bastidores" da
    interface mostra o custo antes e depois do refino e o número de rodadas.

  Limite
    O refino chega a um ótimo local: nenhuma tarefa melhora mudando
    sozinha. Uma melhora que exigisse mudar duas tarefas ao mesmo tempo
    não é encontrada (seção 5.4).


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
    dependência      40  pré-requisito ausente no dia, no mesmo turno ou
                         em turno posterior
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

  Com os dados simulados, o custo cai de cerca de 60 a 95 (solução
  gulosa) para 27 em cerca de 1 segundo, sem nenhuma restrição rígida nem
  dependência violada.


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

Escala salva (persistência): depois de cada ação (tarefa feita, imprevisto,
multa, dia avançado...) e ao fechar a janela, o estado completo é gravado
em estado_republica.json: a escala, os imprevistos e as trocas da semana,
as tarefas concluídas, o pingômetro e o mural. A gravação é feita num
arquivo temporário que depois substitui o anterior, para o arquivo nunca
ficar pela metade. Ao abrir o programa de novo:
  - a escala é recuperada;
  - os dias que passaram com o programa fechado são avançados;
  - se a semana virou nesse meio-tempo, uma semana nova é montada já no
    dia de hoje.
Se o arquivo estiver corrompido, o programa avisa e começa uma escala nova.
O arquivo está no .gitignore, porque é um dado local da república.

Releitura do Forms: quando a semana vira, se os horários vieram de um CSV
ou da planilha online, as respostas do Forms são lidas de novo antes de
montar a nova semana. Assim, mudanças de grade de aula entram sozinhas.
As multas do pingômetro continuam com cada morador (são reassociadas pelo
nome). Se não der para ler o Forms (sem internet, arquivo apagado), os
horários anteriores são mantidos e o problema aparece no mural.


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
  6) Revisão contra a proposta e correções (detalhes na seção 11):
     persistência da escala e releitura semanal do Forms, correção do
     estado de tarefas concluídas que viram migué, e refino da Busca
     Clássica com dependências em turnos estritamente anteriores.

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
  - A Busca Clássica é ótima para cada tarefa com as outras fixas, e a
    semana chega a um ótimo local (nenhuma tarefa melhora sozinha), mas
    não há garantia de ótimo global (seção 5.4).
  - Os imprevistos valem só para a semana corrente. Ao gerar uma nova
    semana, valem de novo os dados do Forms (relidos na virada da semana).
  - O Forms é relido só na virada da semana. Uma mudança de grade no meio
    da semana deve ser lançada como imprevisto ("Morador deu baixa").
  - Se o botão "Passar Dia" for usado à mão, o dia da escala pode ficar à
    frente da data real, e a virada automática de data continua avançando
    a partir dele.


---------------------------------------------------------------------
11. CORREÇÕES FEITAS NA REVISÃO
---------------------------------------------------------------------

O código foi conferido contra a proposta do trabalho (objetivo, entrada,
limites, papel de cada busca e saída) e todas as funcionalidades foram
testadas. Estes problemas foram encontrados e corrigidos:

11.1 A escala não era salva (Saída: "tabela atualizada diariamente")
  Problema: tudo ficava só na memória. Ao fechar o programa, perdiam-se a
  escala, os imprevistos, as tarefas concluídas, o pingômetro e o mural.
  A tabela só era "atualizada diariamente" se o programa ficasse aberto o
  tempo todo, e o Forms nunca era relido sozinho.
  Correção: novo módulo persistencia.py e salvamento automático em
  estado_republica.json; ao reabrir, a escala é recuperada e os dias
  passados são compensados (inclusive a virada de semana); o Forms é
  relido na virada de cada semana, mantendo as multas de cada morador.
  Também foi criada a opção --novo, para começar do zero. Detalhes na
  seção 8.

11.2 Tarefa concluída e não feita ao mesmo tempo
  Problema: se uma tarefa já marcada como feita era registrada como "não
  foi feita" pela janela de imprevisto ou pelo "Simular B.O.", ela
  continuava na lista de concluídas. O card do dia ficava verde
  ("Concluída") mesmo com a dose de pinga aplicada e a tarefa
  realocada. Só o botão "Não fez" tratava esse caso.
  Correção: o tratamento passou para registrar_imprevisto (main.py), por
  onde passam todos os caminhos. Toda tarefa registrada como não feita
  sai da lista de concluídas.

11.3 Busca Clássica: ordem dentro do dia e otimalidade da semana
  Problema 1: a dependência aceitava o pré-requisito no mesmo turno. Por
  isso "Varrer a casa" e "Passar pano" chegavam a cair os dois no
  sábado à noite, com pessoas diferentes, sem uma ordem definida entre
  eles.
  Correção 1: o pré-requisito precisa estar num turno estritamente
  anterior, na Busca Clássica e na função de custo da Busca Local (que a
  Busca Online também usa). Agora varrer cai de manhã e passar pano à
  tarde ou à noite, e a ordem de execução aparece na própria escala.
  Problema 2: as tarefas eram planejadas uma de cada vez, e uma tarefa
  planejada cedo não levava em conta as seguintes. O plano não era
  ótimo nem localmente para a semana.
  Correção 2: foi criada a fase de refino (explicada na seção 5.5). Os custos do A*
  foram reformulados para coincidir com a variação do custo global. Por
  isso o termo "esforço no dia" passou a ser por par de tarefas e o
  pré-requisito passou a enxergar quem depende dele. O resultado é um
  ótimo local da semana. Com os dados simulados, o custo da Busca
  Clássica caiu de 173,5 para 166,5. Com o novo esqueleto, o custo final
  da escala (Busca Local) caiu de cerca de 48 para 27.

Como as correções foram verificadas:
  - escala fechada e reaberta: estado idêntico (escala, imprevistos,
    concluídas, pingômetro, mural);
  - reabertura 2 e 20 dias depois: o dia da escala volta a coincidir com
    a data real;
  - virada de semana com o CSV do Forms alterado: horários novos lidos,
    morador removido sai da escala, multas dos demais preservadas; com o
    CSV apagado, os horários anteriores são mantidos;
  - arquivo de estado corrompido: o programa começa do zero sem travar;
  - tarefa concluída depois registrada como não feita: sai das concluídas;
  - Busca Clássica: em 300 trocas aleatórias de plano, a variação do
    custo do A* foi igual à do custo global; nenhuma tarefa melhora
    sozinha no plano final; nenhuma dependência no mesmo turno;
  - 3 semanas simuladas com 3 imprevistos por dia: nenhuma restrição
    rígida violada e nenhuma tarefa sem responsável.
