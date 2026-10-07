"""
RedatorAgent — geração automática das mensagens.

Etapa 4 do fluxo exigido pelo Desafio 5: *"geração automática das
mensagens"*, usando IA Generativa.

Como funciona
-------------

1. **Consolidação por destinatário.** Vários alertas do mesmo produtor
   viram uma única mensagem (política anti-fadiga em ``rules.yaml``).
2. **Montagem do bloco de fatos.** Só entram no prompt dados já apurados:
   nada é estimado pelo modelo.
3. **Redação pelo LLM (Groq).** Saída estruturada em JSON, com limite de
   caracteres por canal declarado no prompt.
4. **Revisão automática.** Um modelo rápido confere a mensagem contra os
   fatos autorizados (números inventados, promessa de pagamento, tamanho).
5. **Contingência determinística.** Sem chave de API, sem cota ou com erro
   de rede, a mensagem é montada por *template* — o fluxo do desafio
   continua integralmente demonstrável, e a interface deixa claro qual
   caminho foi usado.

Além das mensagens individuais, o agente produz **boletins consolidados**
(digests) para as personas institucionais — banco, seguradora, cooperativa,
assistência técnica, corretor e gestor público.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

import pandas as pd

from ..llm.groq_client import GroqClient, LLMIndisponivel
from ..llm.prompts import (
    prompt_digest,
    prompt_mensagem_estruturada,
    prompt_revisao,
)
from ..models import Alerta, Mensagem
from ..personas import (
    LIMITE_CANAL,
    PERSONAS_INSTITUCIONAIS,
    PERSONAS_MUTUARIO,
    Persona,
    get_persona,
    PESO_SEVERIDADE,
)
from ..rules.engine import MotorRegras
from ..utils.formato import (
    data_curta,
    data_extensa,
    hectares,
    inteiro,
    num,
    reais,
    reais_compacto,
    truncar,
)
from ..weather.indicadores import contexto_climatico_resumido
from .base import Agente, Contexto


class RedatorAgent(Agente):
    nome = "RedatorAgent"
    papel = "Geração das mensagens com IA Generativa"
    descricao = (
        "Consolida os alertas por destinatário e redige a comunicação "
        "personalizada por persona e canal usando um modelo de linguagem na "
        "GroqCloud, com revisão automática e contingência determinística."
    )

    def __init__(
        self,
        cliente: GroqClient | None = None,
        motor: MotorRegras | None = None,
        *,
        revisar: bool = True,
    ) -> None:
        super().__init__()
        self.cliente = cliente or GroqClient()
        self.motor = motor or MotorRegras()
        self.revisar = revisar
        self._llm_ok = True  # vira False após a primeira falha definitiva

    # ==================================================================
    def _executar(self, ctx: Contexto) -> str:
        ctx.telemetria_llm = self.cliente.telemetria
        if not ctx.alertas:
            return "Nenhum alerta — nenhuma mensagem a redigir."

        usar_llm = bool(ctx.usar_llm and self.cliente.disponivel)
        if ctx.usar_llm and not self.cliente.disponivel:
            ctx.avisar(
                "GROQ_API_KEY não configurada: as mensagens foram geradas pelo "
                "redator determinístico (templates). Configure a chave para "
                "ativar a redação por IA Generativa."
            )

        mensagens: list[Mensagem] = []
        mensagens += self._mensagens_individuais(ctx, usar_llm)
        mensagens += self._boletins_institucionais(ctx, usar_llm)

        mensagens.sort(key=lambda m: (-PESO_SEVERIDADE.get(m.severidade, 0), -m.score))
        ctx.mensagens = mensagens

        por_llm = sum(1 for m in mensagens if m.gerado_por == "llm")
        return (
            f"{len(mensagens)} mensagens geradas "
            f"({por_llm} por IA Generativa, {len(mensagens) - por_llm} por template); "
            f"{len({m.canal for m in mensagens})} canais; "
            f"{len({m.persona for m in mensagens})} personas."
        )

    # ==================================================================
    # Mensagens individuais (personas de mutuário)
    # ==================================================================
    def _mensagens_individuais(self, ctx: Contexto, usar_llm: bool) -> list[Mensagem]:
        alvo = [a for a in ctx.alertas if a.persona in PERSONAS_MUTUARIO]
        if not alvo:
            return []

        # Consolida por destinatário (a operação, pseudonimizada)
        grupos: dict[str, list[Alerta]] = defaultdict(list)
        for a in alvo:
            grupos[self._destinatario_id(a)].append(a)

        # Prioriza os destinatários de maior risco dentro do teto de mensagens
        ordenados = sorted(
            grupos.items(),
            key=lambda kv: (
                -max(x.severidade_peso for x in kv[1]),
                -max(x.score for x in kv[1]),
            ),
        )
        teto = max(1, int(ctx.max_mensagens))
        limitados = self._distribuir_por_persona(ordenados, teto)
        if len(ordenados) > teto:
            ctx.avisar(
                f"{len(ordenados) - teto} destinatários ficaram fora desta execução "
                f"por causa do teto de {teto} mensagens (proteção de cota). "
                "Os alertas continuam registrados."
            )

        mensagens: list[Mensagem] = []
        for _, alertas in limitados:
            principal = max(alertas, key=lambda a: (a.severidade_peso, a.score))
            persona = get_persona(principal.persona)
            canal = self._escolher_canal(persona, ctx.canais_ativos)
            if PESO_SEVERIDADE.get(principal.severidade, 0) < PESO_SEVERIDADE.get(
                persona.severidade_minima, 0
            ):
                continue
            mensagens.append(
                self._redigir(
                    ctx=ctx,
                    persona=persona,
                    canal=canal,
                    alertas=alertas,
                    principal=principal,
                    usar_llm=usar_llm,
                )
            )
        return mensagens

    @staticmethod
    def _distribuir_por_persona(
        ordenados: list[tuple[str, list[Alerta]]], teto: int
    ) -> list[tuple[str, list[Alerta]]]:
        """
        Distribui o teto de mensagens entre as personas em rodízio.

        Ordenar apenas por risco faria a fila ser tomada pelas operações de
        maior valor — quase sempre do mesmo perfil. Em uma central real, o
        produtor familiar com risco alto e ticket baixo também precisa ser
        avisado. O rodízio preserva a ordem de risco *dentro* de cada
        persona e garante presença de todas as que têm alerta.
        """
        if len(ordenados) <= teto:
            return ordenados

        filas: dict[str, list[tuple[str, list[Alerta]]]] = defaultdict(list)
        for item in ordenados:
            principal = max(item[1], key=lambda a: (a.severidade_peso, a.score))
            filas[principal.persona].append(item)

        # Personas com maior severidade máxima entram primeiro no rodízio.
        ordem_personas = sorted(
            filas,
            key=lambda p: -max(
                max(a.severidade_peso for a in it[1]) for it in filas[p]
            ),
        )
        selecionados: list[tuple[str, list[Alerta]]] = []
        while len(selecionados) < teto and any(filas[p] for p in ordem_personas):
            for p in ordem_personas:
                if not filas[p]:
                    continue
                selecionados.append(filas[p].pop(0))
                if len(selecionados) >= teto:
                    break
        return selecionados

    # ==================================================================
    # Boletins institucionais
    # ==================================================================
    def _boletins_institucionais(self, ctx: Contexto, usar_llm: bool) -> list[Mensagem]:
        if not ctx.alertas:
            return []
        df = pd.DataFrame([a.to_row() for a in ctx.alertas])
        mensagens: list[Mensagem] = []

        for codigo in PERSONAS_INSTITUCIONAIS:
            persona = get_persona(codigo)
            relevantes = [
                a for a in ctx.alertas
                if codigo in {p for ac in a.acionamentos for p in ac.get("personas", [])}
                and PESO_SEVERIDADE.get(a.severidade, 0)
                >= PESO_SEVERIDADE.get(persona.severidade_minima, 0)
            ]
            if not relevantes:
                continue

            sub = df[df["id"].isin({a.id for a in relevantes})]
            metricas = self._metricas_digest(sub, persona)
            destaques = self._destaques_digest(sub, persona)
            canal = self._canal_do_digest(persona, ctx.canais_ativos)

            texto, assunto, origem, modelo, acoes = self._digest_texto(
                persona=persona,
                periodo=f"{ctx.data_ref.strftime('%d/%m/%Y')} — horizonte de {ctx.horizonte_dias} dias",
                metricas=metricas,
                destaques=destaques,
                usar_llm=usar_llm,
            )

            limite = LIMITE_CANAL.get(canal, persona.limite_caracteres)
            if len(texto) > limite:
                texto = truncar(texto, limite)

            severidade = max(
                (a.severidade for a in relevantes),
                key=lambda s: PESO_SEVERIDADE.get(s, 0),
            )

            # O identificador do boletim precisa distinguir **situações**, e
            # não apenas persona, canal e dia. Sem o evento dominante, dois
            # boletins do mesmo dia — um de seca, outro de geada — recebiam o
            # mesmo id e um sobrescrevia o outro no outbox, apagando o rastro
            # de auditoria do primeiro e corrompendo a janela anti-fadiga.
            # Foi um defeito real, encontrado por teste: a repetição imediata
            # passou a suprimir *menos* do que a primeira execução.
            evento_dominante = (
                sub["evento"].mode().iloc[0]
                if not sub.empty and "evento" in sub.columns
                and not sub["evento"].mode().empty
                else "consolidado"
            )
            mensagens.append(
                Mensagem(
                    id=Mensagem.novo_id(
                        codigo, canal, f"digest:{evento_dominante}", ctx.data_ref),
                    destinatario_id=f"INST-{codigo.upper()}",
                    destinatario_nome=persona.nome,
                    persona=codigo,
                    persona_nome=persona.nome,
                    canal=canal,
                    assunto=assunto,
                    texto=texto,
                    alertas=[a.id for a in relevantes],
                    severidade=severidade,
                    score=float(sub["score"].max()) if not sub.empty else 0.0,
                    municipio="",
                    uf=", ".join(
                        [u for u in sorted(sub["uf"].dropna().astype(str).unique()) if u.strip()][:6]
                    ) if not sub.empty else "",
                    evento=f"consolidado:{evento_dominante}",
                    gerado_por=origem,
                    modelo=modelo,
                    resumo_interno=(
                        f"Boletim consolidado de {len(relevantes)} alertas para "
                        f"{persona.nome}."
                    ),
                    acoes=acoes,
                    caracteres=len(texto),
                    limite_canal=limite,
                )
            )
        return mensagens

    # ==================================================================
    # Redação de uma mensagem individual
    # ==================================================================
    def _redigir(
        self,
        *,
        ctx: Contexto,
        persona: Persona,
        canal: str,
        alertas: Sequence[Alerta],
        principal: Alerta,
        usar_llm: bool,
    ) -> Mensagem:
        dados = self._bloco_de_fatos(principal, alertas, persona)
        # Só entram no prompt as regras cuja ação é dirigida a ESTA persona:
        # não faz sentido pedir a um produtor que "eleve o município para
        # acompanhamento diário da área de risco".
        acionamentos = self._acionamentos_da_persona(alertas, persona.codigo)
        limite = LIMITE_CANAL.get(canal, persona.limite_caracteres)

        texto, assunto, origem, modelo, resumo, acoes, confianca = "", "", "template", "", "", [], 1.0

        if usar_llm and self._llm_ok:
            try:
                sistema, usuario = prompt_mensagem_estruturada(
                    persona=persona, canal=canal, dados=dados, acionamentos=acionamentos
                )
                bruto = self.cliente.json(
                    sistema=sistema,
                    usuario=usuario,
                    modelo=self.cliente.settings.modelo_redacao,
                    max_tokens=2000,
                    tarefa=f"mensagem:{persona.codigo}:{canal}",
                )
                texto = str(bruto.get("mensagem", "")).strip()
                assunto = str(bruto.get("assunto", "")).strip()
                resumo = str(bruto.get("resumo_interno", "")).strip()
                acoes = [str(x) for x in (bruto.get("acoes") or [])][:4]
                try:
                    confianca = float(bruto.get("confianca", 0.8))
                except (TypeError, ValueError):
                    confianca = 0.8
                if texto:
                    origem = "llm"
                    modelo = self.cliente.settings.modelo_redacao
            except LLMIndisponivel as exc:
                self._llm_ok = False
                ctx.avisar(f"IA Generativa indisponível ({exc}). Usando templates.")
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Falha na redação por LLM: %s", exc)

        if not texto:
            texto, assunto, acoes = self._template(
                persona, canal, principal, alertas, dados, acionamentos
            )
            origem, modelo = "template", ""
            resumo = resumo or (
                f"Gerada por template determinístico a partir das regras "
                f"{', '.join(principal.regras)}."
            )

        # Garante o contrato de tamanho do canal mesmo se o modelo exagerar
        if len(texto) > limite:
            texto = truncar(texto, limite)

        revisao: dict[str, Any] = {}
        if self.revisar and origem == "llm" and self._llm_ok:
            revisao = self._revisar(texto, dados, limite)
            if revisao.get("aprovada") is False and revisao.get("mensagem_corrigida"):
                texto = truncar(str(revisao["mensagem_corrigida"]), limite)
                revisao["aplicada_correcao"] = True

        explicacao = " ".join(
            ac.get("explicacao", "") for ac in principal.acionamentos[:2]
        ).strip()

        return Mensagem(
            id=Mensagem.novo_id(self._destinatario_id(principal), canal, principal.evento, ctx.data_ref),
            destinatario_id=self._destinatario_id(principal),
            destinatario_nome=self._destinatario_nome(principal, persona),
            persona=persona.codigo,
            persona_nome=persona.nome,
            canal=canal,
            assunto=assunto or self._assunto_padrao(principal),
            texto=texto,
            alertas=[a.id for a in alertas],
            severidade=principal.severidade,
            score=max(a.score for a in alertas),
            municipio=principal.municipio,
            uf=principal.uf,
            evento=principal.evento,
            gerado_por=origem,
            modelo=modelo,
            resumo_interno=resumo,
            acoes=acoes or self._acoes(acionamentos),
            caracteres=len(texto),
            limite_canal=limite,
            revisao={**revisao, "confianca_modelo": confianca} if origem == "llm" else {},
            explicacao=explicacao,
        )

    # ------------------------------------------------------------------
    def _revisar(self, texto: str, dados: dict[str, Any], limite: int) -> dict[str, Any]:
        """Segunda passagem barata de conformidade (modelo rápido)."""
        try:
            sistema, usuario = prompt_revisao(mensagem=texto, dados=dados, limite=limite)
            return self.cliente.json(
                sistema=sistema,
                usuario=usuario,
                modelo=self.cliente.settings.modelo_rapido,
                temperatura=0.0,
                max_tokens=1500,
                tarefa="revisao",
            )
        except LLMIndisponivel:
            return {}
        except Exception as exc:  # noqa: BLE001
            self.log.debug("Revisão automática falhou: %s", exc)
            return {}

    # ==================================================================
    # Bloco de fatos autorizados
    # ==================================================================
    @staticmethod
    def _bloco_de_fatos(
        principal: Alerta, alertas: Sequence[Alerta], persona: Persona
    ) -> dict[str, Any]:
        ind = principal.indicadores
        fatos: dict[str, Any] = {
            "municipio": principal.municipio,
            "uf": principal.uf,
            "evento_principal": principal.evento_nome,
            "severidade": principal.severidade,
            "dia_de_maior_risco": data_extensa(principal.dia_pico) if principal.dia_pico else "nos próximos dias",
            "janela_de_acao_horas": principal.janela_acao_h,
            "cultura": principal.produto,
            "fase_da_lavoura": principal.fase_nome,
            "area_financiada_ha": round(principal.area_ha, 1),
            "valor_financiado_reais": round(principal.valor_credito, 2),
            "programa_de_credito": principal.programa,
            "instituicao_financeira": principal.instituicao,
            "cobertura_declarada": principal.tipo_seguro,
            "possui_cobertura": principal.tem_cobertura,
            "evento_coberto_pelo_proagro": principal.cobertura_proagro_evento,
            "lavoura_irrigada": principal.irrigada,
            "resumo_climatico": contexto_climatico_resumido(ind),
            "indicadores_chave": {
                k: v for k, v in ind.items()
                if k in {
                    "prec_7d", "prec_max_24h", "dias_secos_consecutivos",
                    "balanco_hidrico_14d", "tmin_min", "tmax_max",
                    "dias_tmax_ge_35", "rajada_max", "prob_granizo",
                    "dias_com_chuva_7d", "umidade_media",
                }
            },
            "outros_eventos_no_periodo": sorted(
                {a.evento_nome for a in alertas if a.evento != principal.evento}
            ),
            "recomendacao_agronomica_da_fase": principal.recomendacao_fase,
            "regras_disparadas": principal.regras,
        }
        if principal.dias_para_colheita is not None:
            fatos["dias_ate_a_colheita"] = int(principal.dias_para_colheita)
        if principal.dias_para_vencimento is not None and persona.prioriza_valor_financeiro:
            fatos["dias_ate_o_vencimento"] = int(principal.dias_para_vencimento)
        hist = principal.historico_municipio.get("freq_evento")
        if hist:
            fatos["participacao_historica_do_evento_no_municipio"] = (
                f"{float(hist) * 100:.0f}% dos acionamentos do Proagro"
            )
        # ---------------------------------------------------------------
        # Fatos vindos de fontes externas gratuitas e públicas.
        #
        # Entram no bloco fechado como qualquer outro fato: o modelo pode
        # usá-los, nunca inventá-los. Cada um só aparece quando existe de
        # verdade — campo ausente é melhor do que campo aproximado, porque
        # o produtor pode levar esta mensagem ao gerente ou ao perito.
        # ---------------------------------------------------------------
        ext = principal.contexto_externo or {}

        anomalia = ext.get("anomalia_chuva") or {}
        if anomalia.get("classificacao") and anomalia["classificacao"] != "sem referência":
            fatos["chuva_prevista_vs_media_historica"] = (
                f"{anomalia['classificacao']} "
                f"({anomalia.get('previsto_mm')} mm previstos contra "
                f"{anomalia.get('normal_mm')} mm de normal para a janela, "
                "conforme a climatologia da NASA POWER)"
            )

        zarc = ext.get("zarc") or {}
        if zarc.get("avaliavel"):
            fatos["aderencia_ao_zarc"] = zarc.get("explicacao", "")
            fatos["janela_de_plantio_zarc"] = ext.get("janela_zarc", "")

        perda = ext.get("perda_estimada") or {}
        if perda.get("perda_reais") and persona.prioriza_valor_financeiro:
            fatos["perda_estimada_reais"] = perda["perda_reais"]
            fatos["perda_estimada_base"] = ext.get("base_perda", "")
            fatos["perda_estimada_unidades"] = (
                f"{perda.get('perda_unidades')} {perda.get('unidade')}"
            )

        protecao = ext.get("protecao_municipio") or {}
        if protecao.get("diagnostico"):
            fatos["protecao_do_municipio"] = (
                f"{protecao['diagnostico']} — {protecao['cobertura_publica']:.0%} "
                f"da area financiada com cobertura no Sicor e "
                f"{protecao['cobertura_privada']:.0%} com seguro rural privado "
                "subvencionado (PSR/MAPA)"
            )

        # O motivo de indeferimento mais frequente do município é, na prática,
        # a informação mais acionável que existe para quem pode vir a abrir um
        # pedido de cobertura: diz o que documentar ANTES de precisar.
        motivo = ext.get("motivo_negativa_frequente")
        if motivo and principal.cobertura_proagro_evento:
            fatos["motivo_de_indeferimento_mais_comum_no_municipio"] = motivo
        deferimento = ext.get("deferimento_historico") or 0.0
        if deferimento and principal.cobertura_proagro_evento:
            fatos["taxa_historica_de_deferimento_no_municipio"] = f"{deferimento:.0%}"
        prazo = ext.get("prazo_pagamento_dias") or 0.0
        if prazo and persona.prioriza_valor_financeiro:
            fatos["prazo_medio_historico_ate_o_pagamento_dias"] = int(prazo)

        if not persona.aceita_dado_agronomico:
            fatos.pop("recomendacao_agronomica_da_fase", None)
            fatos.pop("janela_de_plantio_zarc", None)
        return fatos

    # ==================================================================
    # Templates determinísticos (contingência e modo sem LLM)
    # ==================================================================
    def _template(
        self,
        persona: Persona,
        canal: str,
        a: Alerta,
        alertas: Sequence[Alerta],
        dados: dict[str, Any],
        acionamentos: Sequence[dict[str, Any]] | None = None,
    ) -> tuple[str, str, list[str]]:
        quando = data_curta(a.dia_pico) if a.dia_pico else "nos próximos dias"
        gravidade = {
            "informativo": "Aviso", "atencao": "Atenção",
            "alerta": "ALERTA", "critico": "ALERTA CRÍTICO",
        }[a.severidade]
        acoes = self._acoes(acionamentos if acionamentos is not None else a.acionamentos)
        resumo_clima = contexto_climatico_resumido(a.indicadores)
        objeto = self._objeto_produtivo(a)

        cobertura_txt = (
            f"Sua operação consta com {a.tipo_seguro}. Se houver perda, comunique "
            "o agente financeiro o quanto antes — a cobertura depende de "
            "comprovação e análise técnica."
            if a.tem_cobertura
            else "Sua operação não consta com cobertura de risco declarada. "
            "Vale conversar com seu agente financeiro sobre alternativas para a próxima safra."
        )

        if canal == "sms":
            texto = truncar(
                f"{gravidade}: {a.evento_nome.lower()} previsto para {a.municipio}-{a.uf} "
                f"em {quando}. {objeto['posse_cap']} ({num(a.area_ha, 1)} ha) "
                f"esta em {a.fase_nome.lower()}. {acoes[0]} "
                f"AgroSentinela - alerta automatico.",
                LIMITE_CANAL["sms"],
            )
            return texto, "", acoes

        if canal == "push":
            titulo = truncar(f"{gravidade}: {a.evento_nome} em {a.municipio}", 45)
            corpo = truncar(f"{objeto['rotulo']} em {a.fase_nome.lower()}. {acoes[0]}", 120)
            return f"{titulo} | {corpo}", titulo, acoes

        if canal == "whatsapp":
            # O WhatsApp tem 700 caracteres: em vez de truncar no meio de uma
            # frase, montamos um texto curto por construção — duas ações e uma
            # linha de cobertura condensada.
            cobertura_curta = (
                f"Sua operação consta com {a.tipo_seguro}. Havendo perda, avise "
                "o agente financeiro o quanto antes."
                if a.tem_cobertura
                else "Sua operação não consta com cobertura de risco declarada. "
                "Vale conversar com seu agente financeiro."
            )
            linhas = [
                f"{gravidade} — {a.evento_nome} em {a.municipio}-{a.uf}",
                "",
                f"A previsão indica {a.evento_nome.lower()} com maior risco em {quando}. "
                f"{objeto['posse_cap']} ({num(a.area_ha, 1)} ha) está em "
                f"{a.fase_nome.lower()}, estágio sensível a esse evento.",
                "",
                "O que fazer agora:",
            ]
            linhas += [f"• {truncar(x, 150)}" for x in acoes[:2]]
            linhas += ["", cobertura_curta, "", "AgroSentinela — alerta automático."]
            texto = "\n".join(linhas)
            if len(texto) > LIMITE_CANAL["whatsapp"]:
                # Último recurso: uma ação só, ainda com a frase de cobertura.
                linhas = linhas[:5] + [f"• {truncar(acoes[0], 130)}", "",
                                       cobertura_curta, "",
                                       "AgroSentinela — alerta automático."]
                texto = truncar("\n".join(linhas), LIMITE_CANAL["whatsapp"])
            return texto, "", acoes

        if canal == "voz":
            texto = (
                f"Olá. Aqui é o AgroSentinela, com um aviso automático. "
                f"Está prevista a ocorrência de {a.evento_nome.lower()} em {a.municipio}, "
                f"{a.uf}, com maior risco em {quando}. "
                f"{objeto['posse_cap']} está em {a.fase_nome.lower()}. "
                f"Recomendação principal: {acoes[0]} "
                f"Para falar com um atendente, fique na linha."
            )
            return truncar(texto, LIMITE_CANAL["voz"]), "", acoes

        if canal == "painel":
            linhas = [
                f"{gravidade} · {a.evento_nome} · {a.municipio}-{a.uf} · pico em {quando}",
                "",
                f"Exposição: {reais(a.valor_credito)} em {hectares(a.area_ha)} de "
                f"{objeto['rotulo'].lower()} ({a.fase_nome.lower()}).",
                f"Indicadores: {resumo_clima}.",
                f"Regras disparadas: {', '.join(a.regras)}.",
                f"Cobertura: {a.tipo_seguro}.",
                "",
                "Ações recomendadas:",
            ]
            linhas += [f"{i}. {x}" for i, x in enumerate(acoes, 1)]
            return truncar("\n".join(linhas), LIMITE_CANAL["painel"]), self._assunto_padrao(a), acoes

        # e-mail (padrão)
        assunto = self._assunto_padrao(a)
        corpo = [
            self._saudacao(persona),
            "",
            f"O monitoramento automático do AgroSentinela identificou risco de "
            f"{a.evento_nome.lower()} em {a.municipio}-{a.uf}, com maior probabilidade "
            f"em {quando}.",
            "",
            f"Operação: {objeto['rotulo']} · {hectares(a.area_ha)} · {reais(a.valor_credito)} · "
            f"{a.programa}.",
            f"Estágio atual: {a.fase_nome}.",
            f"Indicadores que sustentam o alerta: {resumo_clima}.",
            "",
            "Ações recomendadas:",
        ]
        corpo += [f"  {i}. {x}" for i, x in enumerate(acoes, 1)]
        if a.recomendacao_fase and persona.aceita_dado_agronomico:
            corpo += ["", f"Orientação para a fase atual: {a.recomendacao_fase}"]
        corpo += ["", cobertura_txt, "",
                  "Esta é uma comunicação automática e preventiva, baseada em previsão "
                  "meteorológica pública. Previsões mudam — acompanhe a atualização diária.",
                  "AgroSentinela — alerta automático."]
        return truncar("\n".join(corpo), LIMITE_CANAL["email"]), assunto, acoes

    # ==================================================================
    # Digest institucional
    # ==================================================================
    def _digest_texto(
        self,
        *,
        persona: Persona,
        periodo: str,
        metricas: dict[str, Any],
        destaques: list[dict[str, Any]],
        usar_llm: bool,
    ) -> tuple[str, str, str, str, list[str]]:
        if usar_llm and self._llm_ok:
            try:
                sistema, usuario = prompt_digest(
                    persona=persona, periodo=periodo, metricas=metricas, destaques=destaques
                )
                texto = self.cliente.texto(
                    sistema=sistema,
                    usuario=usuario,
                    modelo=self.cliente.settings.modelo_redacao,
                    max_tokens=2000,
                    tarefa=f"digest:{persona.codigo}",
                )
                if texto:
                    assunto = ""
                    if texto.lower().startswith("assunto:"):
                        primeira, _, resto = texto.partition("\n")
                        assunto = primeira.split(":", 1)[1].strip()
                        texto = resto.strip() or texto
                    return texto, assunto or f"Boletim AgroSentinela — {periodo}", "llm", \
                        self.cliente.settings.modelo_redacao, []
            except LLMIndisponivel:
                self._llm_ok = False
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Digest por LLM falhou: %s", exc)

        # Template determinístico
        assunto = f"Boletim AgroSentinela — {metricas.get('alertas', 0)} alertas · {periodo}"
        linhas = [
            f"Boletim de exposição climática — {periodo}",
            "",
            f"Foram identificados {metricas.get('alertas', 0)} alertas em "
            f"{metricas.get('municipios', 0)} municípios, envolvendo "
            f"{reais_compacto(metricas.get('exposicao', 0))} em operações de crédito rural "
            f"({hectares(metricas.get('area_ha', 0))}).",
            "",
            "Prioridades:",
        ]
        for i, d in enumerate(destaques[:6], 1):
            linhas.append(
                f"{i}. {d.get('titulo', '')} — {d.get('detalhe', '')}"
            )
        linhas += [
            "",
            f"Operações sem cobertura de risco declarada: "
            f"{metricas.get('sem_cobertura', 0)} "
            f"({reais_compacto(metricas.get('exposicao_sem_cobertura', 0))}).",
            "",
            f"Recomendação principal: {persona.decisao_alvo}",
            "",
            "AgroSentinela — boletim automático gerado a partir dos microdados do "
            "Sicor/Proagro (Banco Central) e de previsão meteorológica pública.",
        ]
        return "\n".join(linhas), assunto, "template", "", []

    @staticmethod
    def _metricas_digest(sub: pd.DataFrame, persona: Persona) -> dict[str, Any]:
        if sub.empty:
            return {}
        m = {
            "alertas": int(len(sub)),
            "operacoes": int(sub["ref_bacen"].nunique()),
            "municipios": int(sub["cd_ibge"].nunique()),
            "ufs": int(sub["uf"].nunique()),
            "exposicao": float(sub["valor_credito"].sum()),
            "area_ha": float(sub["area_ha"].sum()),
            "criticos": int((sub["severidade"] == "critico").sum()),
            "alertas_severidade_alerta": int((sub["severidade"] == "alerta").sum()),
            "sem_cobertura": int((~sub["tem_cobertura"]).sum()),
            "exposicao_sem_cobertura": float(sub.loc[~sub["tem_cobertura"], "valor_credito"].sum()),
            "score_medio": round(float(sub["score"].mean()), 1),
            "eventos": sub["evento_nome"].value_counts().head(5).to_dict(),
            "culturas": sub["produto"].value_counts().head(5).to_dict(),
        }
        if persona.agrega_por == "uf":
            m["por_uf"] = (
                sub.groupby("uf")["valor_credito"].sum().sort_values(ascending=False).head(8).round(2).to_dict()
            )
        return m

    @staticmethod
    def _destaques_digest(sub: pd.DataFrame, persona: Persona) -> list[dict[str, Any]]:
        if sub.empty:
            return []
        chave = {"municipio": "municipio", "uf": "uf", "carteira": "municipio"}.get(
            persona.agrega_por, "municipio"
        )
        agg = (
            sub.groupby([chave, "evento_nome"], as_index=False)
            .agg(
                alertas=("id", "count"),
                exposicao=("valor_credito", "sum"),
                area=("area_ha", "sum"),
                score=("score", "max"),
                criticos=("severidade", lambda s: int((s == "critico").sum())),
            )
            .sort_values(["criticos", "exposicao"], ascending=False)
            .head(8)
        )
        return [
            {
                "titulo": f"{r[chave]} · {r['evento_nome']}",
                "detalhe": (
                    f"{int(r['alertas'])} alertas ({int(r['criticos'])} críticos), "
                    f"{reais_compacto(r['exposicao'])} expostos, "
                    f"{hectares(r['area'])}, score máximo {r['score']:.0f}"
                ),
                "alertas": int(r["alertas"]),
                "exposicao": float(r["exposicao"]),
                "criticos": int(r["criticos"]),
            }
            for _, r in agg.iterrows()
        ]

    # ==================================================================
    # Utilidades
    # ==================================================================
    @staticmethod
    def _saudacao(persona: Persona) -> str:
        return {
            "produtor_familiar": "Olá,",
            "produtor_empresarial": "Prezado(a) produtor(a),",
            "cooperativa": "Prezados(as),",
            "assistencia_tecnica": "Prezado(a) responsável técnico(a),",
            "corretor_associacao": "Prezado(a) parceiro(a),",
            "gerente_credito_rural": "Prezada equipe,",
            "subscricao_seguradora": "Prezada equipe de risco,",
            "gestor_politica_publica": "Prezados(as),",
        }.get(persona.codigo, "Prezado(a),")

    @staticmethod
    def _acionamentos_da_persona(
        alertas: Sequence[Alerta], persona_codigo: str
    ) -> list[dict[str, Any]]:
        """
        Seleciona apenas as regras cuja lista ``personas`` inclui o
        destinatário. Se nenhuma regra for dirigida a ele, devolve todas —
        assim a mensagem nunca fica sem conteúdo.
        """
        todos = [ac for a in alertas for ac in a.acionamentos]
        dirigidos = [ac for ac in todos if persona_codigo in (ac.get("personas") or [])]
        return dirigidos or todos

    @staticmethod
    def _acoes(acionamentos: Sequence[dict[str, Any]], limite: int = 3) -> list[str]:
        """Ações únicas, na ordem de severidade em que as regras dispararam."""
        vistas: list[str] = []
        for ac in sorted(
            acionamentos,
            key=lambda x: (-PESO_SEVERIDADE.get(x.get("severidade", ""), 0), -float(x.get("score", 0))),
        ):
            acao = (ac.get("acao") or "").strip()
            if acao and acao not in vistas:
                vistas.append(acao)
            if len(vistas) >= limite:
                break
        return vistas or ["Acompanhar a atualização diária da previsão."]

    @staticmethod
    def _objeto_produtivo(a: Alerta) -> dict[str, str]:
        """
        Como se referir ao objeto financiado. Falar em "sua lavoura de
        bovinocultura" é errado; o vocabulário muda entre lavoura, pomar,
        canavial e rebanho.
        """
        cultura = (a.cultura or "").upper()
        if cultura in {"BOVINOS"}:
            return {"rotulo": "Rebanho bovino", "posse": "seu rebanho",
                    "posse_cap": "Seu rebanho"}
        if cultura in {"PASTAGEM"}:
            return {"rotulo": "Pastagem", "posse": "sua pastagem",
                    "posse_cap": "Sua pastagem"}
        if cultura in {"CAFE", "LARANJA", "UVA", "MACA"}:
            termo = {"CAFE": "cafezal", "LARANJA": "pomar de citros",
                     "UVA": "parreiral", "MACA": "pomar de maçã"}[cultura]
            return {"rotulo": a.produto, "posse": f"seu {termo}"
                    if termo.endswith(("l", "r")) else f"sua {termo}",
                    "posse_cap": f"Seu {termo}" if termo.endswith(("l", "r")) else f"Sua {termo}"}
        if cultura == "CANA":
            return {"rotulo": "Cana-de-açúcar", "posse": "seu canavial",
                    "posse_cap": "Seu canavial"}
        if cultura == "HORTALICAS":
            return {"rotulo": "Hortaliças", "posse": "sua horta",
                    "posse_cap": "Sua horta"}
        rotulo = a.produto or "Lavoura"
        return {
            "rotulo": rotulo,
            "posse": f"sua lavoura de {rotulo.lower()}",
            "posse_cap": f"Sua lavoura de {rotulo.lower()}",
        }

    @staticmethod
    def _destinatario_id(a: Alerta) -> str:
        """
        Identificador pseudonimizado do destinatário.

        Os microdados do Sicor não divulgam nome, e o CPF/CNPJ aparece
        apenas em bases restritas. O sistema usa a referência da operação
        como chave — suficiente para o roteamento e aderente à LGPD
        (princípio da minimização de dados).
        """
        return f"OP-{a.ref_bacen}-{a.nu_ordem}"

    @staticmethod
    def _destinatario_nome(a: Alerta, persona: Persona) -> str:
        rotulo = {
            "produtor_familiar": "Produtor(a) familiar",
            "produtor_empresarial": "Produtor(a)",
            "cooperativa": "Cooperativa",
        }.get(persona.codigo, "Destinatário")
        return f"{rotulo} · operação {a.ref_bacen[-6:]} · {a.municipio}-{a.uf}"

    @staticmethod
    def _assunto_padrao(a: Alerta) -> str:
        prefixo = {"critico": "[CRÍTICO]", "alerta": "[ALERTA]",
                   "atencao": "[ATENÇÃO]", "informativo": "[AVISO]"}[a.severidade]
        objeto = RedatorAgent._objeto_produtivo(a)
        return truncar(
            f"{prefixo} {a.evento_nome} em {a.municipio}-{a.uf} — {objeto['posse']}",
            90,
        )

    @staticmethod
    def _canal_do_digest(persona: Persona, canais_ativos: Sequence[str]) -> str:
        """
        Boletim consolidado é texto longo: prefere canais que comportam isso.

        Mandar um digest de 1.200 caracteres por WhatsApp resultaria em
        truncamento agressivo e perda das prioridades — que é justamente o
        conteúdo útil para quem recebe.
        """
        preferencia = ("painel", "email")
        for canal in preferencia:
            if canal in canais_ativos and canal in persona.canais:
                return canal
        for canal in preferencia:
            if canal in canais_ativos:
                return canal
        return RedatorAgent._escolher_canal(persona, canais_ativos)

    @staticmethod
    def _escolher_canal(persona: Persona, canais_ativos: Sequence[str]) -> str:
        if persona.canal_padrao in canais_ativos:
            return persona.canal_padrao
        for c in persona.canais:
            if c in canais_ativos:
                return c
        return canais_ativos[0] if canais_ativos else persona.canal_padrao

    # ------------------------------------------------------------------
    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if not ctx.mensagens:
            return {"mensagens": 0}
        t = self.cliente.telemetria.resumo()
        return {
            "mensagens": len(ctx.mensagens),
            "por_llm": sum(1 for m in ctx.mensagens if m.gerado_por == "llm"),
            "por_template": sum(1 for m in ctx.mensagens if m.gerado_por == "template"),
            "fora_do_limite": sum(1 for m in ctx.mensagens if not m.dentro_do_limite),
            "chamadas_llm": t["chamadas_api"],
            "tokens_llm": t["tokens_total"],
        }
