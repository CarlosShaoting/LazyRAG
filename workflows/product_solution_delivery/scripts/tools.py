# Generated from the source package's embedded LazyMind contract bundle.
# flake8: noqa: Q000,B014
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import uuid
import zlib
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lazymind.chat.engine.subagent.context import require_context
from lazymind.chat.engine.subagent.tools import _save_artifact


PACKAGE_RELEASE = "psd-2026-08-11-portable-lazymind-competitive-analysis-v1"
STAGE_SKILLS = {
    "direction": "shape-product-direction",
    "competitive": "analyze-competitors",
    "design": "product-design-full-cycle",
    "prd": "write-prd",
    "prototype": "build-product-prototype",
    "review": "review-product-artifact",
    "handoff": "prepare-development-handoff",
}
STAGE_ORDER = tuple(STAGE_SKILLS)
STAGE_RELAYS = {
    "direction": {"competitive", "design", "review"},
    "competitive": {"design", "review"},
    "design": {"prd", "prototype", "review", "handoff"},
    "prd": {"prototype", "review", "handoff"},
    "prototype": {"review", "handoff"},
    "review": {"handoff"},
    "handoff": set(),
}
TEXT_STAGES = {"direction", "design", "prd", "review", "handoff"}
STAGE_ALIASES = {
    "direction": {"direction", "shape-product-direction", "产品方向", "方向梳理"},
    "competitive": {
        "competitive", "competitor", "analyze-competitors", "竞品", "竞品与生态位", "生态位",
    },
    "design": {"design", "product-design-full-cycle", "产品方案", "产品设计", "方案设计"},
    "prd": {"prd", "write-prd", "需求文档"},
    "prototype": {"prototype", "build-product-prototype", "交互原型", "原型"},
    "review": {"review", "review-product-artifact", "方案评审", "产品评审", "评审"},
    "handoff": {"handoff", "prepare-development-handoff", "研发交付", "开发交付"},
}
STAGE_DISPLAY_LABELS = {
    "direction": "产品方向", "competitive": "竞品与生态位", "design": "产品方案",
    "prd": "PRD", "prototype": "交互原型", "review": "方案评审", "handoff": "研发交付",
}
STAGE_USER_OUTCOMES = {
    "direction": "目标用户、核心问题与产品范围",
    "competitive": "与同类产品的差异，以及适合切入的位置",
    "design": "功能如何运作、关键流程、界面与文案",
    "prd": "团队可以评审和执行的需求说明",
    "prototype": "关键流程的可操作交互示意",
    "review": "方案中的缺口、冲突与推进风险",
    "handoff": "研发实现与验收需要的信息",
}
DESIGN_DOMAINS = {
    "domain_state": "领域对象、数据语义与状态",
    "behavior_policy_trust": "行为、规则、权限与信任",
    "ia_semantics": "信息架构与语义",
    "journey_interaction_service": "用户旅程、交互与用户可见服务流程",
    "ui_visual_system": "界面、视觉与设计系统",
    "content_communication": "内容与沟通",
}
DESIGN_HARD_GATES = {
    "privacy", "identity", "permission", "silent_write", "cross_tenant",
    "high_loss_irreversible",
}
DESIGN_HARD_GATE_LABELS = {
    "privacy": "隐私",
    "identity": "身份",
    "permission": "权限",
    "silent_write": "静默写入",
    "cross_tenant": "跨租户隔离",
    "high_loss_irreversible": "高损失且不可逆",
}
DESIGN_DOMAIN_REFERENCES = {
    "domain_state": ["domain-model.md"],
    "behavior_policy_trust": ["product-behavior-decisions.md"],
    "ia_semantics": ["information-architecture.md"],
    "journey_interaction_service": ["journey-interaction.md"],
    "ui_visual_system": ["ui-quick-decisions.md", "ui-heavy-research.md"],
    "content_communication": ["content-communication.md"],
}
DESIGN_DOMAIN_EVIDENCE_GAPS = {
    "domain_state": "对象定义、数据来源、状态迁移、不变量、并发冲突和异常恢复",
    "behavior_policy_trust": "授权主体、触发条件、作用范围、拒绝/撤销、审计记录和责任归属",
    "ia_semantics": "用户心智模型、命名歧义、信息归属、检索路径和跨角色可发现性",
    "journey_interaction_service": "触发入口、关键路径、等待/失败反馈、人工接管和服务恢复",
    "ui_visual_system": "真实界面层级、组件状态、跨尺寸可读性、无障碍和设计系统约束",
    "content_communication": "受众、发送时机、信息层级、敏感内容暴露和误解后的纠正路径",
}
DESIGN_DOMAIN_HEAVY_REQUIREMENTS = {
    "domain_state": [
        "核验当前对象全集、数据来源、状态迁移、不变量和异常恢复",
        "给出外部对照、冲突边界及可验证的数据/状态规格",
    ],
    "behavior_policy_trust": [
        "跨至少六个不同产品形态记录真实做法、参数和来源",
        "补齐场景映射、产品定位、规律锚点、交互对比、条件化推荐、行为 token、验收和分层来源八类产出",
    ],
    "ia_semantics": [
        "使用真实截图或官方文档核验当前结构、对象全集、术语和入口",
        "至少比较页内调整、改名串联、终态重构三档成本方案及升级条件",
    ],
    "journey_interaction_service": [
        "实测当前关键路径、等待/失败/撤销/恢复状态和人工接管点",
        "覆盖差异产品形态并给出逐场景服务边界、可见反馈和验收",
    ],
    "ui_visual_system": [
        "至少覆盖官方材料、真实界面及一种一手用户反馈来源",
        "记录可量化视觉参数，并提供继承当前真实风格的现状/建议对比和实现验收",
    ],
    "content_communication": [
        "核验当前真实文案、受众、触发时机、敏感信息暴露和失败沟通",
        "用可追溯来源说明措辞差异、适用条件、纠错路径和无障碍要求",
    ],
}
DESIGN_ESCALATION_TRIGGERS = {
    "sustained_counterexamples", "practice_divergence", "trust_risk",
}


class ProductAssessmentDecision(BaseModel):
    """One product decision reported by a child Skill."""

    model_config = ConfigDict(extra="allow")

    decision_id: str = Field(
        default="",
        description="Stable decision identifier. Omit only when the validator should allocate one.",
    )
    status: Literal["proposed", "accepted", "reopened", "superseded"] = "proposed"
    value: Any = None
    accepted_by: str = ""
    acceptance_ref: str = ""
    hard_gates: list[str] = Field(default_factory=list)
    risk: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        aliases = {
            "pending": "proposed", "draft": "proposed", "unconfirmed": "proposed",
            "approved": "proposed", "confirmed": "proposed",
        }
        return aliases.get(str(value or "proposed").strip().lower(), value or "proposed")


class ProductAssessmentDependency(BaseModel):
    """A versioned dependency claim with a locatable source."""

    model_config = ConfigDict(extra="allow")

    artifact_type: str = ""
    source_slot: str = ""
    artifact_id: str | None = None
    version: str | None = None
    status: Literal["available", "missing", "outdated", "conflict"] | None = None
    evidence: str = ""
    handling: str = ""


class ProductAssessmentQuestion(BaseModel):
    """An unresolved question; blocking and HITL semantics remain explicit."""

    model_config = ConfigDict(extra="allow")

    question_id: str = ""
    question: str = ""
    blocking: bool = False
    confirmation: Literal["hard-stop", "confirmation-required", "advisory"] | None = None
    decision_id: str = ""


class ProductAssessmentCheck(BaseModel):
    """One evidence-backed quality check."""

    model_config = ConfigDict(extra="allow")

    status: Literal["passed", "failed", "not-checked"] = "not-checked"
    evidence: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        aliases = {
            "pass": "passed", "success": "passed", "ok": "passed",
            "fail": "failed", "error": "failed",
            "pending": "not-checked", "unchecked": "not-checked",
            "not_checked": "not-checked", "not checked": "not-checked",
        }
        return aliases.get(str(value or "not-checked").strip().lower(), value or "not-checked")


class _ProductStageAssessmentBase(BaseModel):
    """Shared, model-visible schema for child-stage quality output."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["draft", "reviewable"] = "draft"
    execution_depth: Literal["light", "minimum-fill", "full"] | None = None
    decisions: list[ProductAssessmentDecision] = Field(default_factory=list)
    dependencies: list[ProductAssessmentDependency] = Field(default_factory=list)
    open_questions: list[Union[str, ProductAssessmentQuestion]] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    checks: dict[str, ProductAssessmentCheck] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_artifact_status(cls, value: Any) -> Any:
        aliases = {
            "complete": "reviewable", "completed": "reviewable", "done": "reviewable",
            "pending": "draft", "incomplete": "draft",
        }
        return aliases.get(str(value or "draft").strip().lower(), value or "draft")

    @field_validator("decisions", "dependencies", "open_questions", "quality_notes", mode="before")
    @classmethod
    def normalize_array_fields(cls, value: Any) -> Any:
        if value in (None, ""):
            return []
        return value if isinstance(value, list) else [value]

    @field_validator("checks", mode="before")
    @classmethod
    def normalize_checks(cls, value: Any) -> Any:
        if value in (None, ""):
            return {}
        if not isinstance(value, list):
            return value
        normalized: dict[str, Any] = {}
        for index, item in enumerate(value, 1):
            if not isinstance(item, dict):
                normalized[f"check_{index}"] = item
                continue
            name = str(
                item.get("name") or item.get("check_id") or item.get("id") or f"check_{index}"
            ).strip()
            normalized[name] = {
                key: nested for key, nested in item.items()
                if key not in {"name", "check_id", "id"}
            }
        return normalized


class ProductNonHandoffAssessment(_ProductStageAssessmentBase):
    """Quality result for stages that cannot claim implementation readiness."""

    stage: Literal["direction", "competitive", "design", "prd", "prototype", "review"]
    implementation_readiness: Literal["not-assessed", "blocked"] = "not-assessed"

    @field_validator("implementation_readiness", mode="before")
    @classmethod
    def normalize_readiness(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = value.get("status") or value.get("value") or value.get("readiness")
        aliases = {
            "not_assessed": "not-assessed", "not assessed": "not-assessed",
            # A child model cannot promote a non-handoff artifact to implementation-ready.
            # Conservatively demote common overclaims instead of spending another model turn.
            "ready": "not-assessed", "ready-with-open-items": "not-assessed",
            "ready_with_open_items": "not-assessed",
        }
        return aliases.get(str(value or "not-assessed").strip().lower(), value or "not-assessed")


class ProductHandoffAssessment(_ProductStageAssessmentBase):
    """Handoff is the only child allowed to assess implementation readiness."""

    stage: Literal["handoff"]
    implementation_readiness: Literal[
        "not-assessed", "blocked", "ready-with-open-items", "ready"
    ] = "not-assessed"

    @field_validator("implementation_readiness", mode="before")
    @classmethod
    def normalize_readiness(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = value.get("status") or value.get("value") or value.get("readiness")
        aliases = {
            "not_assessed": "not-assessed", "not assessed": "not-assessed",
            "ready_with_open_items": "ready-with-open-items",
        }
        return aliases.get(str(value or "not-assessed").strip().lower(), value or "not-assessed")


ProductStageAssessmentInput = Annotated[
    Union[ProductNonHandoffAssessment, ProductHandoffAssessment],
    Field(discriminator="stage"),
]
for _assessment_model in (
    ProductAssessmentDecision, ProductAssessmentDependency, ProductAssessmentQuestion,
    ProductAssessmentCheck, _ProductStageAssessmentBase,
    ProductNonHandoffAssessment, ProductHandoffAssessment,
):
    # Workflow packages are exec'd into synthetic modules that are not guaranteed to
    # exist in sys.modules. Resolve postponed annotations while this namespace is intact.
    _assessment_model.model_rebuild(_types_namespace=globals())
ROUTER_REFERENCES = (
    "references/stage-registry.md",
    "references/routing.md",
    "references/artifact-protocol.md",
    "references/workspace.md",
    "references/human-control-and-failures.md",
    "references/runtime-host-contract.md",
    "assets/artifact-template.json",
    "assets/workspace-template.json",
)

# The immutable resource bundle remains the audit source for the contract hash, but the
# parent Router only needs this projection at inference time. Returning every Workspace,
# Manifest and failure reference made a deterministic seven-way choice exceed the generic
# large-result threshold (about 40 KiB) and needlessly consumed most of the step deadline.
ROUTER_RUNTIME_CONTRACT = """# Product stage Router contract

Apply this priority without exception:

1. Explicit stage selection from requested_stage, a stage approval, or the original runtime
   request. An explicit selection MUST be preserved even when its inputs are incomplete.
2. A high-confidence deterministic action/material rule.
3. Model recommendation only when the first two rules do not decide the stage.

After the Host's initial clarification (Ask user), a clean new project with no explicit stage,
bound project artifact, or uploaded product material MUST start at direction. Once direction is
delivered, competitive is the first recommended next stage and still requires the normal human
continue confirmation. Explicit stage selection remains authoritative and may start elsewhere.

Canonical stages and explicit product outcomes:

- direction: product direction / direction brief / clarify users, problem and scope
- competitive: competitor comparison and ecosystem positioning
- design: product solution / product design / mechanisms, rules, flows, UI and acceptance
- prd: PRD / requirements document
- prototype: interactive or HTML prototype
- review: review or audit an existing product artifact
- handoff: development handoff / implementation delivery package

Exact routing record fields:

- selected_stage: exactly one canonical stage above
- route_source: explicit | deterministic | model | fallback
- route_reason: a concise reason tied to the user request or supplied materials
- confidence: explicit | high | low
- alternatives: an array with no more than two canonical stages
- stage_chain: only a shortest forward chain explicitly authorized by the user; otherwise []
- stage_chain_authorized: true only for that explicit multi-stage authorization

The current Workflow Session executes selected_stage only. A stage_chain is planning metadata and
never crosses the stage confirmation boundary. The parent Router does no external research and
loads no child Skill. When design is selected, the next and only nested Router is the six-domain
product-design scope/effort Router; do not create another top-level Router.

The host validator is authoritative. It restores an explicit stage from the original runtime
request, canonicalizes common route-source wording, removes invalid/excess alternatives, and
reduces unauthorized chains to one stage. Publish its normalized result; never substitute a model
preference for an explicit stage.
"""

# LazyMind executes this source with a synthetic __file__ and does not guarantee a
# filesystem checkout for sibling resources. The build script replaces this block with
# a compressed, immutable mapping of canonical Skill contract resources.
# BEGIN EMBEDDED CONTRACT BUNDLE
RESOURCE_BUNDLE_B85 = (
    'c-rK>X>(lHl_mODGE`q|g&;_-u1Vo`grDW=Qngj~v&!AkVL1p8Oo}Lh01Ja`R=FYokN^^6g2X(K7zhv$C?G)+!jOsK!}}*H+?$!7'
    '{1@I{d+l@XxtRbZyI*~%*AX7T%$xU~dxkx(z4pJp^~rz#=x0BB_wKE?K6tC4q2bf^_U60U4>I>UJ8t!~bT@Q$wDokicC<I#%C@zB'
    'k?p+yY5T2gS4(H>J$(8>=F_*zrIpL$-gx*Tp4hxBZbegl@$5-7`6yn0U7j5L_ujtpi>LD8<?%#$dL{1dyF43@a)a^HN%_iOAFt&q'
    'd*_wCHTm!tzx+_Y+PEw}jwV*3r=#*uyQc6k+FOerkCj)aqx>UWQ=0$x-v09R_GMA-za8g};`xd4+Fs>(U;MH^8aTW>-n}f9WQ5iE'
    '!+7s&d186^OWgl>yu7km?VG9;HY*oP(ZFUjwR3sA!y)lvxvaX}i(3_@E9Va?Lpzn?3%rQFQFL;M2kmY6_rf?Qi_!7(=;&3vJj^jS'
    '%KJ3(JuXWVGMwt%0dHR}ZIw&Ae>feBbF<;7FOOeU`lh3eMHvpSjOPyjaJm$a4af86(P^F^R(przQM`)$Fxp#;d$%fE52M@yMzOsn'
    'kBf2}@$7DS@nLnX7!~uCqe6N5r97@$nwL>W`JHG_9z7YIO+~}wyeGcxU94OTT^=9ELo>hNHpu+Xj?T}!?lre$GnoA0T)g~MG&al0'
    'jK=eoy}ioXv}^#p=k8?Ylh0e*+GJfm?8vltbZ2_HvYFc*otdug=Js37Z5{2|%-!bB&$Hc`uGW8PZU5|@OlL>)t-H<lWZSiNbhdW4'
    '{!25q*E^Z+Y|EYY)|TeBOmk<;omTm0cTZ<luFtk*o8_(@_p+UOY1ccM=Jw{c``xWAT^ZS-t)I!S<&k`jJR{T6(cYbH?|%2ww?1vx'
    'js9u-pJl=gC=1ICg|DK*NwhH==O-`Emt^zEN??cNpUDK_tHFWGizo4z?4k$wDtPNmdGxFD3)!;$GQpLDmCC_0E|lL=m#3@M-p7~6'
    'BbUdc@$3*5aG_M$+qc<#JSOWLZsm9)7e9HxP2pBa#xx$C&qW(@mJZX8UwnvVojJfuy`GWrUY@M*>Ud-%8lT}UDupB2X|X)-boKJM'
    'SbkB6a{KbX@z;IjZH!*$=g%_n)5G}b!*Xd#{udurE+#8$W7VniXsIZhPJa4_(?xvIL^;4&%6v2UID<|2WG?f|j-Kvpr+#8z{@q9a'
    '_%r>tO>8)PeEj3i?$+DQvg<x>Zg0Jv?dsM~>$f64<=f~jn=p)q%-e5=BZ*%2zx}ohQTAp$eHb1enRhwR<%frr!fs`|x4g6$uVOK('
    '3lA?#hq4Sj#L4qy)_H#(B-t+U#1^LC9>HY}Pm|m&Di!5$#KT)MYw^*`sQ4ToZafsx80GuR16%Rx(dGFl1&KV=j`rLESKU98lT>+d'
    '7L6>q2ioSV*?BzFl)-P7zTEa+;(A$2DJw#W#~~TRz{|_xi}J{!+{cX}THekye<tTDBWI%eVEgjyLiTR5a`NC{#pKXLyYtcDYuP#&'
    'n+g&fiSs9wuV*o&#r~*ox!ivuQz6F#ie-0`Q(=3uTr9ZPohU@>G6UnHdn$!ud3hz;dz$&j=9_qz{Oil}t?HBY_{oL5Nabi-lt47H'
    'h9i42AfiiND%!iaJT7rcaX|6~oVvL~z5>^g+g)A_$4Xx?c$-h!o9}hq5&2eK7%vyMc&!Yxe*enbT=hFV_2pBqxj5Y-18``0zL!?*'
    '-o0b8cgq{aa%q7VCr4BUUfJriNvZ5Vz~Gmj%9g|TDyRoUS4PJVWPeu*gK}guP4~KPHT>YcAN*y*dw<>V{`(Cr9e3}El<XD_-=Jc&'
    'tF^1)i}#!4A#ouef3+5!_C{MGt@hnZ_C>j&czoT|Q*KtKzPd0FjjUGA&g3#om*1DFy~bpxTpllC4R)W2*n^zQPgdvlE>A`=(dSdq'
    'ke4M*P4}Dcwtd>(h2P)k%(i63-uU3t_KYZq?7imB?5!Izlb_4RyU`|^BYW$EOm}BbRxhy6O+$z!^POH5KW%OQqN7E%$&I@mx8$eU'
    '-`#6#ZE5Y!{65oq*Z+C9xxJ^kt>JcaTiZ=}7$4dxN8pAI_l>qwa%o3TXNx@Ihuno!G%C9>j~Qo_Wkl9Q=MQCqGd=B}w|D%u{YSV-'
    'm%Lm{x6Fd*#I{@Rxj#&%JenLYZ|&n}?V@e3{7o_dJdw|lbrpTxz&Xu)%TvRdmuZpt=*sHass7CGi16eg3ipP*VmWu{MkzaUQVgn*'
    '%Ef-TMY&<(;c?MevRAKO@+Ofu3%Z#x0BqH!tENRR6Ft1PEoaB6A`#SLhEd={4sfVPugayo$Uu>kJVd&yp-C%+Qk0+N^(jT0X>#i%'
    'Pnn#MF*jW~M@<=d7ZEh6(b~elT7#vycu-w_6+hXGi<7qEbBFSJnI@b6CNC1=)suL9FFM-1JX@9_MQ1ZIPBRzslaLT&%kkH0f2a_M'
    '=L-}NJh_!ZpZuJ6i<d4gOV2nCzEoEx%FW4SVR{xH+DKN9t2<+fxG|9^FQn6=LPlkTeGyEV9p{G3uf_8FEZfkT{j9aCyYs$G*l)hq'
    'nZ2ErqtKG=YOMSA`%tG|h3a1RT0%5RvIrcaX{cX!%KD0_S9|;9W89Z^!R6_EG>{X?T5mr?G6nkD-MrbPdV?JA?v9p@w%W&BbpakI'
    '$|v+aqRCt|>E<)FBSSxh+o>wbDVR@r!`7BN4c*z_;UU>B5hN<E>R$M|tG<tIF|Z9it+s<37xaz{3QzAXRn8xAq}btq_m3a{OqKY@'
    'Vo2YTohZj?EM7eoGfE~#zok174^N4bkTC}r7RslyayRO7IsEX{)Esf|I40Y?+V^#Iz9Xhsbo3INPB$nP8M}5+RCQ{?U_LBw`zehk'
    '#Eg0co8{uE_)^Y#?W65R`@)|O^RCne@#eQFr@?VI#lLlWx^`B>FLWY@isgy@@@X;Jc<Bw8Xz*2er%!FXmz9G}>@M~4Xv}zZS$#2I'
    'eKt{D_>#5|2jNC=r$<yw1N@cFjy6$Jw?x;pwu#@<RXe0NUitmx%)b9_MhsCg4&&wCXg|**Ktm2!h+k^vj(P<tBUr7X(1bhQ6*&_g'
    'Zcc7=JQgo6!Dh)p`>V&WY-fjNccw|t`Hj|FBL4csPJ@DhsW&;!{bpC2^ZZ0?*o7!RB0fCVG5A^>&HS7<Bje>A`CCkh>iWFyHOSg{'
    '`XtKFV<g4r@skz%v5i$U!t=hw7rK}iDVd5JY%Dq#JtrfyiKLA}Ur6>P-2idiL<Y-bB%)tm6Ytmr$&)oz8+_0ymPtpuejsaiyY&`U'
    'Q~%lACgPyI8P-WxlbVe-X)Sk}Tk(s2yq%0)oOd|}f&YSaS)3F3&tY-?ZQ!P4)b<UQ5;{hAg*p567OH8TrPXMqSYGR`?48H6XWa4C'
    '`BJ>Q?&pvaGa27NP853O>m%9pm9ss1Cg1cf#}D(-(z&SkDEH!<-Y2qV<=yFIpZ?(84815STi#lC=<%iq9dV2=OPe@KPI}uWl>Pno'
    '+x4*#^-#Fv{J^{e@xbK>1pBdeC(3M;m&66L$WW!Q>BA$Yg{KB&@@0?7eRXU703)bTBy>EfuSdi)TK0m;HuvK(zNaaMv6Je+_;=G{'
    '^29&acMbwQ`ZzwBN1(io0}_oD;qj@25$}OMcRaCO8HW!jeyHpgs63Gjh&XM)rQ8_ed(kw)D^HGb1~27}^khW?udCC0CcbhO3M%go'
    '%c97$#NL5v&u6L3;qi1El1s%qiXW}hfyd|+zz4f{Ql41|mrmv50S>8bKk@5N4rw!2);6Po0p0<6;Or||Fp=)@@v#d26*$AIL-Ffv'
    '{tzl=e7L+VM$d40YuwqrZU@S&@||eSz>Pl5*H{Ee9K^o1S;GAisi^yhKdX;(IB^t2Dxi*ntNn(nTr7xmqLNKXF$yeMQV~iu0t@^1'
    'bT*!N3<vrN4u5rF(oV+Ixf5rB%H*zw5+2#EJRdAC&4va7-9Z0O3mZ;OAlfkgIyzgIfAWYsK|Y4y=<aZIJ`k=URiSqt@kilQMvsLO'
    'dG%z)j|`_SlmRq{DtjgvQXwOn4m<;X`rm%La#pGi<vFDcRa^{+WP%Wv`Btk6<IL|=mwV-J#;Rre$iQIvzw8w&sazUltbn)VPL>^4'
    'J)5L#;a<!aL>PyGA6}x;Vp^uw9~#@28k-5iD%<IS*2l4{L*wF9GosFTF@<n6I1uffBxf=hf|%{m#RI1!89MQf7mfeaEOP!XkEg^*'
    'uN+`R_A7=+8J!Q~))wh$a^5b3t_`<)+S(dg?zgmMn=*+}r)$xO<0I?3I$i$q(1j<LWK<$E<n+XA&%#qCD?`;Ss$Wz{xNi7Xj-<S^'
    '?AEad(b9oAH1f&df*1^Zc|O9ud}w%T?2_iEcuAsyDEBC%uvK&-`Q{>@WcSMTyhC~EI4(@%yr0cPM|;s}Kb~FMgrySv3L8SbTgn0c'
    '7KYVa>YsGMd>{_?<jA29N6WLS{iSHTukxS|mJB0!$Gg$S!^`5tWvTb_BzJi>UOwBS;<XsB*m1oB<<l?aR92^Zqv^fO&F1cIF;1F0'
    'Z-wz-1d7IIAb^&ZDlgYWM3_f7IUzR)W#ao8Sjx*^dB31OcB#hs@-_u-rs-B|rx-&Be%$PA&E8hyre>#f-OIMv=eKAaWxr_6{#N|J'
    'dmWwKs*~kD*)Otf9rx~v6Vq@<4BU>}x8)l~kcP)`fCqB%v)*`R)18_^H2Iv)ycY%*#xD+Xz)X-ZGDrskZ@2agDVE$U4OTsS8Z|KE'
    '$^UX}*zzapmN=0{xiu=9XG7*r{5Jl~B#f#;agk+2Vgy~Dt#X(MJE++lzrtCPdHuEluE48-lk`MPb*es$TA#(w<J=?2gR$XI7$66v'
    'gSG`!6V?wMhS*|WR$Vp^^%`9RIrAE^X#Q<;D@>0DZ;do`HQ&956E0#t>RT2=&=jpMj8pQ{hvEzHjpXJy&!w$+_<~P|@ZX)YIDBC@'
    '-k(PFdws6_>ajZAdY(r{_;bc17(To#jz)V=<?WKx)!K=u1%A$Cpw~EjYcttpTdT32X+lt}K~3+@yV+X^u0WfWcFiAF6INtyv>_hR'
    'I*in%W4Onhyq6^nle^RLU&Lb2&=yRRYt+3(#KJ(5Nut6@RGbc@rF`@1`a`?vz~N<SHq5EXCbLD-_;);A5W_zDdMw(UOT~bpC&q@w'
    '?uiEF?Z(}QOE@06g)pqZL1daVWF_m{_(P4H{ixALx2Vv)l4C3#9*4d!BL^ury<TaE_N}g!s5G$K#s<vBLm16J`C4Vtm_)#+48^^W'
    'Q!3LVqZi?YU4)r0${!#77zb!>fT4h2eWY$V6eV`pj)uUl)eONXgJEf)_+PR<c-+z1)d**dhD!Ld7P=HE?A%lcZfcIwRAsNI+Z`c}'
    'cy2RZUcuP*7Lk?dU4WW-JZAc1vLLcYd<J<XS`AcyKJ|yQvAjdsE7rW|Zsa*GL`ttz*S@YkS?77UJl&~08{p9tQ<a0HUUd<b$w!G5'
    ';Bu4Lz~zIjXy{Sq?<jRMzi4jxJlh@Ex4|w>J2Gb3@L0yr`=i0H5zk>Pc)1ua6s~sV-S4Pvao+LXcIr|g0KFA$eivd0VgNo=Xy%!W'
    'E{p*nB=pr<G$1Q>43Qhy9GWImHIk&9<Z+?0Q^|<^rT^p@G9P^iU)^p=AqQEGC|P;<Bs%Z&ce2=7R2ZX1<*7k3PxHy~+&U!ri`B|V'
    'KcyCSle&=1Z`np3cwK&7qKFeMCHKUL)RGtX8ioXubow`9Y;y<Y;sy5F6F5WS4<gns%0<0VxvV@q<idHWV4r2CkBdCxNov-u2Q1vG'
    '2Vevz$q53LrP!=92R>d`=^KeQzN84ZeW{xpLAByabo#&>M3way@#y1n=?Qm;`l+Hu@&>$+N!G2;BjNXYU5LoZ>c4o`-Y5*n>M(iY'
    '|HL3~rZx-8hxoISRvdjeH@ZuG{?nFA-cC~hDIbyMFC^ajQvgL=Tq|_I-MLT?$6}{zn>+-`0jX>~3(p9xd^*+Gy?amN*|TW>Wx2GI'
    'guUfXV%*YHFt<!>iExFl$ady;)C}LWjA?!59svWD{$8b+N^@COPKaoj(6CLO@b{nm{2v<s*N;E`nY>1Q)Qa+6?&6bY;)-6Dj(p^f'
    '%M(4Bi>J@!r7S2YdZh3KCVH?poIzs&QABQO{Hfn+saj`GUmlBE+!lH2(=lRoiiQ%GTehRqHca)NZ>c@Bkb)rSOUIAqWf36}EM0)?'
    '2LzMbEKRpMn{RhF(pql5DY~(_r6qf>JA13KJ)6DN)zEYAR&%!)XKJSx#ATF)7b#J>KoW)9hLTa0PiobvqZs$qq(l<6_OU%^q~aiM'
    'cz({oR(i)2iBh6f5$puB@bt~a@`YWlhN769GMD&7d}p0Y`NSvcLerJe1$iKLqK58WXc^`J7PdHHn^ZAjd?A>D^pJTZs196Mnpz%F'
    'q1+^cLA)En#`+<JQW`PlWXNB>n~BAzo81pVQ74C$i6h+thFPF&R;R$_DlB9)cPM7rcTF?cqe4~c*U-nmML$(~A5^}6$Pid6+2qh#'
    'E<w?c<UBv2G4*5tJ6c0N@!XbIv(&vNb@TIbXcEgt<m%bWXlh(l^r%<S(ErD>j>`zB=&)r?ZQg1FM;f&9^3gla7%?OM8c0mc1O`;R'
    '6?a)0XCeqos#`e`S2f$#eW9Dor(=8!%7>ohXEMvFfO!~)@j*yz6NbrjIcrWx?Ym;Nk;CrnX-8V1yQixuQ|DGO{b}xqrs|pqACocA'
    'W0CF8!O&XnXqVshWX(nH`fY1>%N^dODbsvUG}9N&Z5eT#p^r3h#`Lp{#6-;WiH<-<)$Rw-1m8es$)77)K`9p(coWTRMa3C0DNMf|'
    'k6#|I<Fu(gk+K5e%rI3De8=Y`S1_D@d9erWcBN5BZ;*#I&gVsz`C}TuX56J3h+w7%sc-I^df^QZ=Jmts@~e8t*_Da~^BpSqRQ5Sc'
    'ktJXv+Jvb{8*L3*p|l@~@nHm&+sf`~DW*DzQnd86+S@DMHKVjwp+fy?aUY7&H#ErAGWgp06XYc@KhLT|BVxuy`y+6zg3!D_R68{u'
    'E~P5;OMOf`6yEMgt9WLBSVcJIF}(#wC`kx0qp?{oJ*?05d2cT<nU)KpKHZH1XCcIuc~5{wkL4-!WV>Mp>xu!3=BAe+L)F-T8F*Yh'
    '2!b;^lS~V0_5uMvOv%<LZ<H7+Zb5^XJ9BvTNKcKGhz+qquN$ksydB2h36e|fIyo4r>86w&d>jo7xDe)uoK=XrKt&qhMW3YG<*j$#'
    'YVPXFb_YgoclPeRHnAn%{im*u_P0KG>t6u_`t+@?mOI(I%{RWtc6N!d`t&Wpz~6uO{ZHR|hu?qE+SPiqwXL=LKEKnMYiMoP+-94<'
    '%su8t>n*#^JvaM1jW0F4_ul*US9jmPm*w>}K}LV6c<60*37qKj(UiIGN0}b}d;SXwYI_81t>hcc<PuoK@4N0a-^(`mu!S3t|Ap7)'
    '{w4h<I=da6&7JpC@7dLJPX?B~mDLfn_q4Uy7q_x4tr)O={%d@e$^0w-FZ|j+=)<4>B)Bmz>h8GL+7iwT4_4|LQ64=udp>_-G2Za9'
    'aF*o#?{&zS(--Ju@q(6~PQcz8MB@N|jSKz_|MwgJZuhe7NQ1ZXwSVot=#bBE{Bw^;<m=zueeK`;|E_y)cL~2IsGs3e?@7@wO8x3)'
    'TSv?1q9E}rhcB!d_&@hFW1rt>@955k!~66t=IvnLDoC3FU07BW|6&*{U5EkVmO(9>lS2l#Xe2X#oB8NN9M8AHrvi<bz3YHIz!ThR'
    'ZO?YuY5>BAliZc8$fs{*+gd+s6=&f_d-iwTgeauP8vrByBw%3>h_k1E+Wv2$m`LyB|2R4E$Dg6(7XWhdH~vb06)Ii$9im5%&Y1r9'
    '^#J}l+1>vn$NENxya;?Q{N`WX1od=fJ8yi}(QNV{n7Z!f&d;*lH*i6?r*&iXbm@BC(4vIjb=Up2tEGcNF8EQqtTY}}do#I5S9fQ#'
    'Oq+d!FaGUHq2czASee<**7U6s37h`ZR`15ON7PxI=}+y%-_R2u%oicOGG2;?;275+cTKW<H}r0JYHMJ;DJklnl)!bp0J{dV`_>h|'
    '^MbABzE|N-zr$tU@pi<L;yQ!csxb1~AaODHN`@B+H&qItRP#XoAba&_+?NC{)$P^<#8mgY?C-KII-}S>-FND~5713D+uFYA>Fnz0'
    'toxblQdyoGH5NpA#LlI@!DLm<ZVRW10`v14{Z(gh)GUuXMDp<Tk>n=4BVTqW2QpkL93)v9oPzeQR;QQJFZe}sYa4<)H=0{&Ri6$&'
    'aQafCzTMj1+I7b%S;_(@x8Io0xVjGTiYx0Y05zd6%FBSH;!|9l#l?cpd|Xw1lB(Gw%E8L&TzLxriM-Y7G@_=tM}P{gOv2$2qg>15'
    'EVCjyyl@g1a9K36A{KKak}9R6#>=y*>dsgrQ!K3F<DD;y!-&Mc?7boh?}xg)ZxQs|e0gTGe7+$r2_E6n<-9FEIqr{^i{&qi<%Khh'
    'Z6Fu*ErzcHd})v?;<LmCKn_XW2Z9k8hxw*=o-Z2>9LWo$a0k5;@#@hxy}*v~G6Z29;vk+mfRjM1jROnd0>ud6hB{#RIbDmIG*v3|'
    'RNO$2Mm?W!%x^5}`^O)D-1rIp`}2?A$%rnO6VOsy>DSfVmhB1v30?1GKKbd-8#>zC?q`xsmbnM}L@W53GwsctogKf;{OTk5v>UcT'
    'rmdsn^PYQ|-`)|UGebR_Y3<51x4{y+FF!GPZk2!;rv=l+f7fkJjR48ih?^v?_QotC$(phQIw&`3>0R-~T^(dHcZ09XyR%6$L;S!}'
    't`=ufl5;Ye0xrIBv0a&!8RE+;h<XgXjxHWx+fR<cuRVWQE*)t8YQ&eS5_#h>EQS`-+b4)cd9>d*eio`jDAtLlcH|FY7)M6F3yg(-'
    'fB4b=YD7RtQ<s_<Oh7D*w>zYHvQ4oa6@O%rKtNv<=Vb>hOeOWLi$NXFZ6UX&&li_jtY)Oaa<h0OGuypm(duBlChLhqW+IAl-{o<I'
    '5lr|s(=gMR-EDbTWDKQ95(rc13ob5BR|=cR22OreTY+^&>6OD)X^|HzT>hBaE33L<f)cT$9EC-uDODJS)Ocm+b+rG85eRui+LR)+'
    'm@3n1g|3k6bytPJ<u}zvscmq};L2|-(9(jkpvvX4G+@<sK^2s*CNsE%D?|a%Wo|WoJ!47lnhKc&g9G@phq`$%#ML=EL{sbMzv-%g'
    'V1JmpiC)e?O0uABWHWj+g5c7%$sC0)=uf_D5-W){)<RUTEx@_D^ad3mD4y2xfb18v)9S#**Ib1971Lw+N974kAmwL88ft|;00xaN'
    '13Q5{#j9nJLc}1~)y-&`g8Xr9N;SAZ3w82i^7atPGy4ctYNnjEB${*B5DDZSBAz51ah8oYboR8>*GgP{i5BP_jz%LFRP|oB!w^{c'
    'vN{iNgU{9nz=?(ofs1df$$9tPM)}Wos?5O)Gwi8aB|vO}2jNY1IDps>9mKs`DFhB<97xn{iMseoL`hP&R_*Pt4vbgMPs%fDby(dA'
    'k2``{Uu4^xuh=D5UGRn~6IG_=y<RyVR%JruD^t#?T@O9MK&U~%Yl}>v(Dn`~gt0WL9$Y1CAMu`qC1Jf%j0OQ@ni&7kE;am}DoxEk'
    'hv{@t#4k(O6k-UD6*XJB4r_JmVZ4nPG^EJcD`Y5TM7zVB&?IS9UfFb@w7%$kfY76;Z>X|&j<~h%Y9O_Jfr*{8$?<4>hM0O7zz@da'
    'g@TnCoeeUWPLc+$>*d8-+*gS9hNFRPo>E`FK($u`<mYQ~upT;W(2b=**+eRUp?H}M_SKlzA^HQe&yp{R>LWZ?1ld(Z9s~k=Og+HR'
    'ZLOc(>88oEbWkqM*aOvgsnOSor6U_dR&xJQbtoU576H~9c<n45MWSoEQFbD1wZzsVVBApHcg1hI+jF<!wv0MJVOt>?O#_d{RDlnz'
    't7%CN0VOhuv8iz<sPB?F4bzoxzYT;NUsv<ouqv4b(i(it;5#YkAF56QeHbnnz#J;WJeo|aqKcQ`2$=9WT5sGt5up`m9*_q6>hQH1'
    'QR75A;s?69W&V*D%0G%{o<Z-94~fM^C>n%JX#kWJoTHh2fZ3Oe@%lb5OV?ItT@YZ-ie?I5LiLzqzTi<7BMy1L`2se2{#X|F^7Ito'
    'Z<R9qSxv!(TlU53lXW05^e5(ID*T0?@cs^PHkbM(98;YEc?-}xSkjs)sj#XoSZAewz%QetO)=zEI~L_{UyvwPu@(i+iiwuwDQP78'
    '%_c^CJZ2zpC%4pkmQ}<8%h^>k8YcN-Kgwi+11+)vp270AvDxT=`JO50iOE2U8p0hFiUadXK}JlmQAh*pp)hlrux`8cdsx>uy~`rz'
    '<c7d+D4+|U=m|`+|3t~g(}(!I6&hm4naq<dKskw^_)JbTS@p#{POgrw(l=c`d&DYa57U4JHndyW+bx$KAYpegNdF2$)7mg+R?f?B'
    'J<(8g?Q1(Br6c?McrP0HlIUtZx_~XjbDPn{9JCBK>CBjHCWT!<+{UNVdW7UY^H}`RrApttqW|!1<zQV7Dl1B50CJ3p`7CdoQ-%2B'
    '9e+IvEg(kITuGFClpm&o@ZL@lR^5{|W+ym7L<1N|>{q{p<yhJ3j|wXuOv>*FHG@T}^UM?ig(%Cx66l4<H=SDgxqM8b!mub`k2>WW'
    'd<Si!8Dx*aOER$7SW0`6q$p*NxJ|fFl2?e<fmFE^3+LcO{syj1O?w)b*axekCik7NRH)DCY_)gQFNQ23VULu2kgpnqxh$Pk*Po;y'
    'e>}nEufBrUsj?IYNS$sw1{ypvkakU-TZkt2I+=%F@k9rPRzDw&p7)1#2*q@Q*3pW6kq2r*7vhO6+2^n!mIh^T_;5ULC4%`v^~tJz'
    's}_cTT@Rgyqdz=~#C}lUY+wg1N^#zh2G*{$qF}KP_j=`K2Zm5?4Jo+Q)66sUk?0_qW%}s@ujO3&-Q_k6BOQa#w$=4PIfhuD$+Kv3'
    'LMtcwqLbI8-ogwNrVY-y;>>vNO$ZQ%{=}Wy0*FY43aA(l7{SwudY7+!A)Qvi6;8q$9F32>xI7v5)dXhI_bn58NFYh{vOk6HO14XJ'
    '%x@QOHuxx-ZkK^vjmlDp!S3bBeq(h=?Ne3=<{s<pC1FHL2-{X-sy{d*4kJ}A2Yl5AM1Z1pD`y9Y3An#09g~Bc*Ro$R{+5R=TBSGi'
    'sEpHicLQKwo#O=H>0>RnhdcmX%`8fC50O}ikHuk^Q&Yg+d@&E&C<qzs4Q?6-D$k+9*OR(%RYIOL_soDfZFDmp+i>MfeGH~1{|ur?'
    '5VizwJz2XfA-n@;VW`L$2urybC!>B;T9pK2&#Cw8R-RiDmFQ0^j~KkEyx7z^9>Z|csRue?6RpS`T_^LwxDi=i>kXu62^?GWEBRj0'
    '{!60BC@7=xRXH!oF8nLmg@$`ftTyN9%YM**han%#vBn;8>{eD1;wh00=Ck%uUX%7pqySOdZVGWIYd#5dN1ylY8xee4J+5p$M>uO?'
    '8;+Yn;%QT|;Kty)MJ*3hXg~sKOCw$s-4lS+T*(7$);AUxLh+=r<7ViV#>MwF?mLS2zC}?jEV+_*6br_ON4*DGk1I+QNywV~^}89S'
    '<$W}O7P-j*tAhRNx!nFw4SMK1savSQA>*YmK$v4jy4l=y=hOCk_q*?Ov}c%yLHwruR<`p7OXuFbcR%AIS(=g0TovPb_f9t`mTGSF'
    'MRQv#(8GVqt&IA|!eJ_&tOk;Pq{hO0CMQ(AS7u$jVi&^$*z2&2Avn(7y5p(vAbMH3keLKaPP(BaprR-)ReOU2qRuiu`Q#Igv3&AB'
    '{u@;W@nbZNGC%q7AGCZ5I?hw35V!$YrVGsYn`Zvo-+r87bp~#F8w-Cc^KrKGZgcA`-L4xbKqumP;HB5T33`o{ZX)fRH5ISH`oZSh'
    '0@Pf@FBoD(?H5W;;d9b-6PZIdcSun~l%b-xYv!|`cvlYwq}wSv#&}6ojECAw7Dy9N%i@N>G?S?iN6CfGL@j$F7rGG^0L_WeS)~F?'
    '&eh+%>#IyA7}PT}@jFCkwI-Y;eX?nrZ!~w^=+IhIh8=toF>#Z1Pzn0oWxr~6(ADU7O^MYc@I<7sX6jq2rGi`_C8{Nlk~k0yc!v^P'
    'f8olIu1L)#o}mwOfCl0;ueRg3mP=0XMWfRh7X2kftt_Wu1_SG?ve7xh#6<;FdscX^9s&Y~3-ZoezWm&mT+(#b(9`UG!r<d(mtj9r'
    '<8Vts+bHs!CELCto>=S@{{Q6AbYyNx{vfv;uXhLKI;g7=d+C9VOKWl#$R0usC+eoWH^<*3**FtkG-UNV?D9H+1#edmK)qe4_UeW+'
    '9GPgVjb8Fjvi3m;0Y`=r+2etDb5UzjExE@?mt*~))gHQq#@Uz~^iq=yiacs2A~YrMnPv&r53Fx-(0v>n@8V0sRWw|lieI$Kt%^gp'
    'HCWjirdY?t#ThZ8ozQ_Lq_-5;E8Mpf1vN$nH>^LIp{arS;r>^ZthW^NoSah{|CB9+;MD3G{8tf*>aJ5pHc~=@K`Q@@1>!Z_R4Oz3'
    'JV_M*&`akK*Wx~}_BnzGdFEfedqwo!!v_5dTv^_UMK~W|!m7G<5=@Sm6SP-gLvF0V9M$b?CAmH=uXiQf*q9{5jS0*eD}+{U>rb_X'
    'JC=K6^KHHj{P8W8$y*=1g)FDJL!mGWIn9FdCI`tEqf4VuXID#dH5|0?AV|qEc%jDQmC|2c$gPJJm<5$*@PJ{w%P60h0vcP5SaXLa'
    'WVZ3~t9WHftXNY58f#Y5D?@wG<ihW*kSX)~3?1ss@8!dWh6epFzHdrH9h>Azm&%scc>mq^nlijjp~?7~f`+Al_MIXongP&i?rzF7'
    'rgWP8;-gP~p5d<2a0#?`#yz~_p5C-Z&RmzkfOn=eUzTN8SI_QcfGy;Jd+y$C?!2$>qC(H_a4+<daxum@^qkv`uy)Oztz9-7X`lit'
    '&o0lVyy$AQzyg#n6p0&7OGnrJuI}tz+=Q`0Uq?xKt8Q_hvnpz>Mtr3U(P$OQ>QLIv#W7Lz6|h(>qPW%a?czixu4Ij|NztXk2~Hk`'
    'le;0^l^bLWB{8+WeZEj{J;42N2$Iyyx%{hc6SHOee1s2GhTv?T0Ho()O(xTRW>91uzV~L;(n%#}RSM%LdN69DV#%VZw~=kf;lq@G'
    'b%f}NzJ1Lk=}~C{H130p5mcgBLFdh1P<`?=qvF=QtA5fM*a^2PdxGW-'
    'Wf1(MtLJ8yJie!!2m}K58vePb!|I-zZ~aqqi;U1^{^dq@v+Z4+b8(bK-'
    'kST7;HZsE604^=)dwxO8@0SjPE)78GRODcH@#EuzxN)W35;Ho=AQC=J#puw-cyFdl9dA_5MnK5O=$Yxs=h7vG*<1qhz7>Z*c%yPv'
    'YR5k{OTOxS`BK(Uymk)Jho~<aLOMNwR+sCaA1(O=9}3zox-+`-|GM0Y5nYu!8JO2Zg#e|H2J_1<dwa#kv;^Gz9jq<CXD6|%gcS@8'
    'sIzugxo~v!a_1zt~?fXqX^SM&u*%@68J1K@!3wd*Eqi>ulsEslOVUukxY6`c$+@VWDZ1eDjlO@KFZB`MrV0I>t~`wx^8sKMrmtp&'
    'n7ELVNvs#K!Tv$G4w2L9j*w^_+961|0WV1Hu(aL=FV(0w|gQcn#=@mBAtD6Th`G7-fE>7;Xiu-j=y0q;(t`T@AN~fH~b(Kg8{;a#'
    'll9p^G^y1wj<S<MZJYGqVOJ!yWHsMvI0R4F?(AM$ekPAovojJmhEiv4gk#UO!5FQKp5&VNI`nx7e;Sj0#GzC{37y__%UxhEj&aWq'
    '`F$c{5wWi3eq5lPShppxNt>19}(-eEod5)YeOh&vAEZrJ}%09H^<8?4&y=OWT_|Z@^Ne%%;bbvY~dVe_<GE-uUy5Bl!^8SeW1yJA'
    '&!v&>+sJ#@>;rDoW1zLfRb&Dirpm}py!?|6KQMmX{CgLjCH-<VojVo`pn?J*^+CJ6eCIM{ve&saNC>A2)E8yszNyQm+jhAnR>$OL'
    'WfYRV(7RA4&EPOz+Q)CQX`g_1MeUcs^p|<O*Z<nG?5DJi{#2bB6lS(^+uvyMgbS(i;XBp@ta21butRc)VJvCH2FMJoMf_kBi1s^G'
    'dD7=9Ojx88jUP7W4bQGY!qc-hPYDL<oK}XHN0M)_)^SACzS(R($V7JUe;wm(GCs^X8B-+bn9|IyoeVHaBY_^tj^GtYcpi-X%lc%M'
    'lTHYs{WhLPH_OJZ+x<en$;p)Q={cHZ`YgmDwo;j#2k6cGp7w=8IkyQ>SQA08!~4Dc$g5%h|g|k_kS;gT$3^m6Uxq=57Ws07fd6oh'
    '5o3#w<fnYI$i}r;C~;Dc(+}1%+bl~D8C<OnqliNk2{K0yD=RA(94~VIww6$Njn~;#c1cT7(_lp?PR=8NA>wEIEFNo?(%_$cK`f>q'
    'MOHP9LTQ2K@+K{Z|)X<i8J`^(?@qj2BFgfb2on^*Z6c9o~u|<f_ix%)!b$Ki+(YakSNvt0e*=GXUG+e4@LQ}qNS(GAD4LXB8Q{>G'
    'oXl;o<_NSTNwaidi_mm>Ckxu7==tSG$vj2P<w`8GY0}??Nq8~gketKxbSCByvad}*(u<Tn_?<`K|j&mL32~SBAZTvyFMTp7HdF!)'
    'YjXrW&l7(baaZgZfI>c32L@L!aQ%ROo-d~33hIrQAjB{kPP1VVk}d(u?T0$hJpwNC&xS(&C_u2F%b(RF1MrcCruD*aEx~qQ!l_dU'
    '<0Xw;N=Qo)Yy^|Utt2riqXo7C%*^;g>!=v=m~i<Kmbjn@!~~!V9OX!OJ`=m4=%uI3LSEqj((|$p-F==`jvleJsR0YM1oWrnmtR1f'
    'gFe-+MKIyz|G^)@*u9t#Un(KbU$EQhsQwgOr(t2SIlJ$j}rppo)y9}g42dYRL6*ilD9*>$nLPq_ohXW$sR?(p@3e0Y``7;vG`M$X'
    'A>#3J|=FrWG%v$hvOL;)t6$vtI9BdODaZa(fnEy(<3azsG|1D{Nk4%W<V&WZ^?<2nG>5TvAcBI$lYh1b0#NX)<6tes5Z3aQ=wFC?'
    '*m+mqi|9IVG>07CnydWP4%Zw(?KqbPt1hutdS9$r}@=r{~=fr$w8*xCyHzqAJRxPq{4i`DvFj@Wccog>u@ZurWgye+osN$vH<0?n'
    'ALi0QptY?JuIW{Npn;qGe(F5#Ry_)N@RKn2w-~LXN_$h^?6K>yV1>Acvw9xcz%uP-W3=fkafGL#KI2fGd2!|m4r|(qADE~i+Twbg'
    'V96)rK;hZnd~<Orn3RfYMX^S%WA<qw_B7SuRhOtG3$>NAzh;0sKanQDc4j9!S^Lus$QdKC`Zz42S!<TDi&kqAx-'
    'Tt`ngPz&XbTKUU?}V55M3WQI^JILkwqyfE--}#-)Z?fy5w&W%3k8Om;_;1jo-'
    'Qiqs5G<@_MM=&ERyI!H+=R8FVmc*&?My<($0rK9bzrTy{ba`|Ar{9u<6JQ^NcOHLtnfY_f@Uo-oL)mz@?_&pjUaZ^T5Sx^Nz%EX1'
    '{Bi)2)?H_nV_s?rH%ar)WRV`Ncl=$#Vp|ZpPk6xpdUHV%P42h0hTGaq4K6hsu2Z&CP|BCvK$DX|nXiyMy?F);Hv6#f+I;4=6xVj)'
    '_xH%j+SG(tQ5dT=m<|_C-Bl97?pWK#wSLH5Fu>LhwN%@^<@))y=>`-5MtHjKjb&Ye`Z&{`&H%A64MY>GE%m4T%zmQ4#$<IErF!S)'
    '3hpoHLa43yQ(ibF2W52oqw5-DkQceV0Zx`#-U@?Z}M}siv@{a$IVXssO-i6_R{p0rTJDuRTNZ}OJ<^Rq1?sRwG>-wOv@w3+MJ3Tk'
    'wl`CY%?fR}p$f~yNt<SOzU=L`x*Vgk{YkODY&9;u4jdz<{+Z%l=!A7l)>T0Zegs-9feiDoKc|*}bYummAmFVn70-AjG2w1t?KB{|'
    '0wsDKeO%OP%PJz6vC3DWmVni>W((z*y_}BkeClK_R55-bR%>h^y+OC{~oB9iwHtxlecfR6H^+u^Tb;w;!|EcNW<JEEQby6v0aS%('
    '*^rc{|pjFoR3jAU=4*Y$l=_W?il#y+w*|+fB`08blnO<bv;@|IT?al^eqz$)PyIMfoaQ~Xs*B`WYG?IDZ+g?AsVQL0yJoanLAw7_'
    '-2GFfFIY~LB+|k~p@u$CQ&VWKx<O<6RMf2+UBG5iaM<wqcq%|7uHsAZ-di9!nrQh1;zEyW9zJ0MiVG<(w$W2MZfx!;!9}0}(w54*'
    '$&b~XR8pNtJc@(I1nO(G({@9&LYhV?ul?ck)t!?tvl{0`S|9$WdWV`<S{p4_ehdto$n?3~~16P7cr<b9D=v=sna;2~cP4g%Rj6cP'
    '~X;JgS*49Gq^T|(to}v0T^wHz7YVRbk4)V|1`pf3v!)&(mZ`(S4iyo(4J#9)V=hCHDANl*@@j-($-jbg-+?L;7vGhGR+ge*1uefL'
    'Gy;CO_80iEi<cnTdhYR3<niaOfn_!?Pnt>N!7B{vOxxQT~tW(`rcedp#%n$=lY8bNw%kVUs%OW82+Yp0Lbs}Sz_jy<AWS}xjTZ85'
    '3-cxqFLJY<7tDX-dR4}2${F|I0^3T$OW3wRuo}ppl$EeFR^0>*T6A;7L9F${HuWS)n58JT#69SNhdd_LY$%h92SZm_ydPv$64&fN'
    'K;Yx){>1ijKbgNZVv(qE(3}d$#!vCx!Ui0+Y(#5bs<<ekfq(45Ml-CpMILfagG^$Uj!MQr1P5_(ofG<z*##VSPlo#T6U{$c%PqE-'
    'G3YWkSJ@7@W^Aupa1|(AtOmy+IQ2x=4Bp6uXE7zrh18mn{y_@moTN<$D!x+IE)WvFfxR$q>+7;UkGr7K88Gc2A)ynxfeB#0h3){U'
    'P>WL!EU*nafCrD6io<&d4@Qo?G4119R8KnRsdO6Ibi47PHJU|YPF;(41O1FvB<{wUTI1uW3{^4}kr|=w5Eh+B-O}q{|2(`JTF~qz'
    '06^Ip$a5Ttx`c8po6O9H>*8%|f$fa??Qmfda5Vh_c_OLvHE)>x6FFdt1*6D0rgaQm}9i0!AD9t0GW;z^$yekgN{OSG^qYZTb^gOg'
    'U!SroaKBg*d5U|Lv;_Bjbb$S8PRKwQgQ*pG88ZiauqpWQ+cVls~GM9I`2@VhQG-~*LSJEZBQ@lS`7?|dr+9_|1hb0Kn-h<21S3cb'
    '80~@LIuSbAhp6)O|4B0q+g836;uk<h)Un>s}UFir14yO5ap@-`MaDj(w3PU|;`J`NW1mno%r)76h5+jVFm_K!O&y~_7by~q!qigJ'
    ')U%I`FzaY-!ptLeVLR#aAoyz&su>7s^bX-)t_kVp*f%{9O9%3zQpEZ;(7hmDvjjSTOUphtB$9dKs!RRVWEFYwG4GeNvt)E#{{U%<'
    'RPAX3ODqaxVsQFo6C2dtP;vMH+K)PA6(viHM+(%>u6|@DQ@;j)oP=gDzu0l)}G6iPPz=ucfMfq_^6=w|AS5m-~(I5va-4uR`YUnh'
    'R#@>b46LK}qm|kZQI4YOIuAFBdFDJa(|C3DHhOv-`y_hF*Nltv~xN;8x=bdpVi61I5>qpk5uPysu!Ls++r*9cfqPerRxq(QE<V?x'
    'a(KUsMW6c_)EsYqi#`-{<u7he*M%akAWph7@OX4FNmnfOWjqAL)o}$M!_Ej>`JX|z^x;u9XpopyF5xa3F4wZ%B>2$;kd)3}WPEGp'
    '#n|^pJ+uhvS*7c(%>*9%Q$Q*zvO+PgFmwW|OV(|r}2kOm+8T%law&KAUr&HJ@v6xn!J~?5v7@~^;Xr_m+hu}=cMX-b_?r@^a3h47'
    'oh-?VwP3Nc1;JMi&e|RoVCFln}=^AFMYp$+iw{i`4U-_N`sg!nZRwL2I*jT&}6Ao{omW!|UgY+IMF%5`c5WlE}2<*CU=qc;GR`T7'
    'Ljji1^orq5RqvK;!UVCefNWr+Ycv@_E^zac<FHd1_6l@k!J}nP3@Qd`mR-Kb5%T-r~98cXHXp9Zsl%Dp^Y*$Cy7uj2$UrEizcQT#'
    'Xdu^a`u#aWtGTHXe#I?$HD(O>4XQrjCx%F=5UhD6&Z5bq^09DKUR$P*fp6*PuBWfayDNWN9&Xc2Ns#^_OrzB{?gfEYB<||+C+aIo'
    '=-c1Os8^}?;uT7m!0<11$FwrPj3FP^*zVaaEk3-IXIW|@3z9qn;6`O9mLu<$XQ&R+8b3p!+(*$|AiSLtrJ*`f<_p+aXYm2(ByyE*'
    'xZu0*rR}3r=w$ISb>w3tHkx@F7J-(VP6d1sAu0M@V0mKuX!=oV6mJrS;iC;X0sFf>}3hSOIr;NtS<y<}0ftOakoi?cQa))7&l*3G'
    '2Nz@dyg|>OSqQ}U1o+VMKt|QCaM1;!;yF6WmovdgnY^S+Z#8=taU8`l-UR$jyYuNF}6Et1dS0u%W!>+JgDiV+D(PvX1=GX|semqv'
    'w<j}FO`<|BQ0CDj(Z{<izl&60kc^M7^<*6l<@z`mwwnX%~*a?*tCNOA6SKxGnd`)k^?S*CV9NLPupicODE|O47={78IT$Q8kN*_|'
    'Myq|x9*k#zi%PZV^`UE-SSU%NFEH9C#iC3?Nq&A~2PWkE;cD(S&PCL^>yFlYU+Xui`QxcVnd3gtCprm@bFNRZ%+7Imm%J!d%QBxu'
    's*n052MQmz6Pz!q`)vY0G3@)~;WNE@rk~#RVkp#!`l!|P?&N(yrhFc+0rGhV*YNS21JGjSJ*@^Ev!hhr|HO>=a9WtZXI_37M&#};'
    '&c(xvm03-~L+F*vqqugBBjH9ykSiSB(wxvyadxexK)?GARG^-?r*lUy=-hQn$XAlaQM&UTQ{8C*MIKz!F4cW*_*WQaU=57;a0=Ta'
    'Fvc6rIr`ri&uNh}uI)*qd3KWr|2wWVFtqfI);1fFRlnTCFkHAJN?H<~ZEoGkaz#($m3VXLxk$=vArWkM-vWs5kqZ0%JlP2uGhM3<'
    'qnixMGKt#n=S-YSWLXuqTsBl`z?LhwOq|*(PInqP{x<o+K5{IOt^6N}#&-lFZrozY2>RhlN`VRKa<=5jv^Io$%tDs#}nl!|?5vv+'
    '^VI3}{>u}F;!Clbvps~JyMaSjjXXC@1LKb(~%8r$Xj>|?75|cUfGEz%61xf+}UADM77vg8(35m}|?v0QVLxqcs4Q|--IL|6OlaS-'
    'ddgSSe_02U|JntnAB<R9E2HU%3psS~&&Jj~;RWeqoD;+QQmP<LSncH^mzMbU30g6lTq#dOF2GY{&C&>nwE=8pg;&_}?h5KkDP)|*'
    '~F0H##Euc^JJ&Zhap@TL&Mch0n3Phi5c^?P6_A(tY9(iqz$XA{XR5$l6$>r<>?>Yp8KPq8TZhVUFmqS2ATP-'
    'iX0n0<l;iJX|OSgO{56qUe)<#)3j0#vNjX(M1lg7XQL_3R>rbJiB?Zjs13*xkv2JES-C9QiEVa*zml_#YPC-vl%4Fm3iOiOiW1c6'
    'jFODwpj4LG?6F=_J2i-O`GEM!iQuG3@I7*lgs>HzvT<^+hqx~3N2+m$HC|6!|msK3+7xgRx|BzU8PUF}73LL4D+vkmQNqI{7e-g@'
    'Td3!dZA$Sd9F;<;%0d7)A$_zx+(z2M=Y=C?{ZraddI8$GHXF?p=lREOW%ZRsX*X%(GmtJO@}T-vV)^;75-!llls<|L;0emKX;Y+G'
    '}Mv4ME>tAsCwldr&9TQdzjaY|f_CotNGr68vhJV{lG?z$^Qb~xE7C1>q*$>Wx!A(V_IoH+7Y1C^@%9-Z1#qs_cx-xo*e27Q|wH5{'
    '<@t7{I8W&vh`=d9PVK|Nh#WnX4W!T?%Kj<+djr)I_p+<~O=SB8D*U<HL%AzvJwEi@=3ca{~_7B_{Ybij48Yx0)5g`%DKsX8)VC8n'
    'F8H_kVFQ>!DcpG|aN#V8{TEx%G~WoqIr-16R1VPHWsSHbq6M)GaKxqz<6ny>e50QOWoSCF!}l4|SBsy#nb%#$?G&0AATnTRU_W6h'
    'Uy881|!aXwx?Rl1t*7#90B$5m5-VeqB4))!NLF#zr|Jz$>CIy^P>9@K3K<1kS0X(vF3t(?@>Cr^o!_;Wp^-iWjSv3~D+JmI)a79j'
    'JCa3U8y@8@~_!|AZz{LgXoa2N3AV%6C$Ny5@Kj82$g{hi+Dzvw&aiRV!#f1`d778!aInnjyXKPoBHlsSKayLrt+SLhmxS&Kh<H6b'
    'wJq;J0_73IAG^H6W{9nHIcclGlM$bm&C>!!E;D_skoboCzSaH^W;miNu8X-+r7mKIHesS=AqrBu*>^{;i>R7^1*VAH<?<P5c!rgR'
    'k?WhS)uMSw*NttcDg-{=^1M+Hl2=c9K3l9Oa!sMZI)dP35rNbQ7r73Dv5QknQPs{p5nr$3VUy_wHI!F*W+Zb9c4a0s1WMKWN1wS*'
    'Vbia&JC>VRuk{TEMUXCU0^=oLp*^S7sLs=elXpt81k{RK(GTejr1&l}wj8<QVeiQ35_J3EG-TYFPA${n>-813Xa*Ib+l<3Jr+enM'
    '<-Jt1P8z*|kRYpRFI6N7x8`Tc?W=RFLi@jV9h9Xk^`+r+sp+{4Z<<i<1$$EY?uTwAvdc4*&JjZ|RH)QfUwHqb{#f=jDV)FyQS2Ri'
    'cXK|8x!dDidGbIQ91j=<3+XyB4}A-N1&k_PIvPP|(rwc%Fwi)>rRJ(T-3m_olM^YMmX)MY=S{lV)}AM!SG;_*)OWL%KZ;2tvv*ci'
    'v=IdlC?1vpF#Xm)nSi0Wi(Iy2b7k*dYVWbtCxI@hDt=R36A=n*2eTWGc&zZ{Bt0W4%{1Dp;cOPcmnH^NzEe4>~L(Z*0+ro++@-Px'
    '8q?X4}%Z5b32w#q-ddpfi4WY9zmZC}FdMkagvc1LITJDKJ#{cUr`Lh2dV?m_Oucj?OfR@N??apjx7J4Kf~Et|R9D)(vstfo~(Fgq'
    '>>0zk#Hq{RbGF`actJpBQ=Mc4sYt4Yp8bCP>OEGIu1mKBkSHxA=|V3bI|qbtCil9~Rx4pykJbYY95ay}mEjh74Y(?gO}q9#$vDwx'
    '(l*dzD&KXppv4JYUS*tCef|FubxE584aOo=#Vww#q3sBulF-)BgGJ_qmVYGtG!wrh|KAvQB<kHa$F;BfG7k!x4d^Lsj>|MM~(?`f'
    't37=nC1h=^8?#ClQBvGh<Jof`Qr8w$W2);nA2yh@j&S7ul&tykw)Om<tHKp%_G{7taem6(Si7ThqW)JZ|hW+S9D;#{nS%mqC#?gz'
    '5k$6p~H0u$$Kl_P;q#^wO8E*RhmUxBX&TUEzaHxk`oAi;Z5DIBrWq>m-?bAS@X{v8`mrQNu1UB_iHvvdZ<?>!$N!?oe96mAgqKh}'
    '!xehv#8g!T6asH7)YL`m%WsCxlic|1nPD|*?lt+o|<N5`GfEk?X`)8qA2>{sWu%iwVAx9ysyyCa+QkP`QyN~QIdXO?L1X!k9y^+T'
    '7_P?`Y|F6*k9g0xw6TI;NXqeo&{Br7zWK<ZrJ7fH1%)0z}kUT>#Zh2NfQ+me?<{t#5duJyU2#SR(|v*kDt6f_=d8bz26RQwuF^Il'
    'HV5sON_-sc15)y2v3mS!=uR+|K)o+BGCV(C>!Ug(3!)KH)nft!n-Tt?65JC-x{&b);#^N^@sy2jQlt#n4nnAu|@|25k|!df^2y1)'
    'RsxtbkH2?o!D%*U9g%&^RdGa7<4lv)j8#?5M<T~=+8wf2r>ZH(zRW;Fb!<z8j%3(uzk7`APw&A%<erqJp^8a8xXeU5@QAVT~M|Mq'
    'T$^pu3qg>Vx0l-uO7SxmBfoKI&M)AmB`EYo~ygjs+oIGjls&7gNFq)4()%s0u++DkabMAp(-tXkKf2`DBkP{WDtR7Ya_Qs8(N;L6'
    '1`^h9tb;Hy(ynk3Q4e|5eTtvyAlmq;jWwO%`X=CH1m=+?jCPc;a1>4WpD9+B<@U&hVlbKaU~_@qW#E`o6a8OSigy_94${q*{*r5B'
    '0`N<#C$P6lWXFz$q;TD4cpwR5Z0g$*O)0JVK>q%fV$Bs8MY{3LT3N77kyN5BbCR&Jjw?}22R)JIs+Sh;0+*kLgY9{V~m?gwspvLz'
    'WGCk*a>vF@<(jToL`XO~>@9YNrl4!&0L(pNcHsT@25$B3LkC7Bk{B2&p28zVX{#`bBuh2wZ=#V=mowlI-eTeMg0nx%6H6Ak@1aRv'
    'epMWb1dWM8f7xD1mCG1r9^9K?nObK(i1EVMN77_JCiYCZhcN?i__sx&^@CAyU6Sp!DCmS2S|Ne5_xvyz1cjYGyuYI$QvI$((Av#)'
    '@i6oq&31gr=XD}-+QeI2;OLH6uQ-&bobdM9OJC|v)<(}sF8eeHymLOUm_2-Oh3Pb?(+pMJCKM6R9_-C}Q2ZXjkceV!y7c*_Q0{2I'
    'Uw)F6KJ-7ZS$9Usz3?XHc7@Ln~tiy=OF>Lrr9r?%u)mZ3!hW~7H}GwSqUn1g7f1ZcF4LqY6d&`A<ov$5`RVJq!KZ4vp-cLxP0V~i'
    '^MxoWnM(5i9-3a6@JpD^0S-R1uYGgIY)d{PZs4!RY=Mpn04RofW(=;>KQ+NiH>R2sTfJTyn~?aHCW&K|mI<X5;NTZW`Ld%Pn>?s)'
    'qhmyT{fPxi<~2|&(2aCZ?kK$-2!YAg*h!N&*kN_M#IZRVhdd*v0p@{LzdT{R7t3!uzek%wv;x939P6>ceVILEu2uCm573!Pw9C@K'
    '0f^F>g_4FAKHmVS-0)Kk}+iXI-<K;}d$hn0a9fq-4WwAN40k4l`pNPPQv_@YuMLPE`+C8S8=p^S{6wuZyx`m=GEqOeoM%U5Q;i17'
    'A?ahQ~HR^>EKE^9>$023Os8lW{UK`#Ov*3T<UvrtqbIyIyRGRfDw71G+QXQG&m<yc4Ie&ghuvM3{Z;Sc`h@um`}hl#Z1oyy^e+{2'
    'nJxOmg$DLS7e1Oz&@e^k8m&2rNbh^744FdJrj%U8u|HY}`uV|piT<OgxhKL6INln76>Gxaq^W}8rtT96`ZB*-5N<R}n4nS6rEbf@'
    'Dg{mmR%;Q29^bk#QU^wo`YHmLHG3>jY#3#z6Wvq#sr?NinscsY7#&Es*C<nm;pd|;~QD$~x5q}IR-wV6lK*Cx`40S_MGajnVj4=`'
    '!C72ySs$3puqNukxqFHWdhGfWopd;6RAqNQ71?~~B<BiE&6(?YL?)1j81<2TEB;}5qUu)A@xRNHD<D!bv@adkO0e`=A|R=LW#U=I'
    '!5rQue>ZB>AKcNx~!@)9k$t2WyE?{Pg7VQgo^nA-fC@C+!vc(hWOL7PQgbNXUIVq#RS1oe{^77?ZLX^XHw$)C9s9L6)4t#M!kXx$'
    '9sQ{;;$_k|JfD0q`th6GD84VG&kMGw!9jDmrTl-m;Klv6pVD{+;Yu1xlMKuvxnx-z}9t@0z3wr}ucSTq#^_gn@z_&o<{zRJLn>l~'
    'p8Rk7Nr5>ywZa1sWO!H!~rhJ>vgbf|%xNoU6@bZ4A(2G5lZEzR~+BSL|$3S?8k<c6!yfk%@Ylv7Y^WL{~zGE}3P613ISoPG{MK_0'
    '6oib@R0Q)71v8YqNf8$(K)ZyZi#{RRBR!37v-Zl^jIs#HSZuEGCKEUO6|RWUJueLJ1dO4f{`ngVl&W}NsvU1x}gG5*A|3Ul6GOld'
    'AT5JJDtq$Cyo?W7nkCFknzGXXdDn-blB`^$#+-g{rJ|L~_jvA;g~iTmuwKk;Aw!v12DcgJ9z7#J$;t>1=vSiZj_=m}sKI9Ox4&8x'
    '<>9AS^O%1Go~8a|aMPYW%e?v`0@e>;tyCPF7|d|bm$aBZsgn(OP!)Ldbg5A&eYuB(S4=|N3(k|)=o&P(#DfffzGDt#6ZQGpT$M6@'
    '3l#E93fmM>Jp4BtLFizdf?tj259UwxGEay~lWqtfzRrRHx8D|eZ}JToq&+yASsZ02@Hr>{i2n{5%3t+nfJMhrLP*FYvMmYk(@Kge'
    '|41l4huehq45)UDmj-f8}#Rqlch?{&1bw%mUw^U;sr$^27CPiK4fzFhLFkKO^TMz@%W@91SZ49gRvj16Qk>16FMY)BvKMe0ypEJT'
    '}g3GWiO4eEMJhf0^}Jgu<HeB3(`uO3w{CLNX@q@)aX1>ZBd3!}+WfeF%7Z{?W;9fK+~10@n==JZP|EOl+PLWU@H0<>(LmEcyfu7%'
    'ZpH@QHzfd|3)%8UCJ1N_f_-kk4sgd+cc%lHC4KB8KM_f><-x6}xO<jg^Y93*5nNh&O^NqDBymT1k)mLJz7KPi#`#XH}^vC%a}uIA'
    'xkrLbGs?oD~)7Ld@_`lAw@G~#gv2-f-5bf@WdC3i5AI(`4jL81KRg>@O)-K_3xB!rIRGa#^;D99AUlD5=cP)V!>;J!MTI~vjttTj'
    'nS)maKIv^CPN4Sg-KYxxMpDyf%KMBVhpB56WpA(dLw`?x)Ko5dPvZ|J_0ZD{N0xF`BY@w-RH<IHyhlj7M-JbYd~n{=*z-M#LDBdE'
    'bB>Kp|(?w10-queM!5BvvV00McUrWHfx)~YQH1#n%o3<`iYJS<C4?PqaiE!p=aj#ijN(_H^fwWd=73^0ovKd@}H7`aR5<>4X2H0='
    ')(RbW&Gw(OHi$dbYqyct#CycsKofaK#xnmtAF!k+bnBpoYK+{_M{SSMM@;V@DWvP0DN#iXcxOo;+Bc6x<8@vxO~jdjF<g$`a#>@>'
    'g&=^bf`x~@Bp85GWxP(Ht5>nm+EC1c!V(b;2B0o>h{KBcYJwqKa!#r~*o*}E*>!665hAyVNf!3OaFO;GL|a&HWqc<zv`E3t$3`w('
    'cG*b-9+1Mqm*#~WbUd#vz`T~o816+R23CNE3guEE>WSK%ut<p~*Y*k#9?KdjZlAlF~Waf))*<t8+XGVY&9GfwSPhsFrmhtI>2SjV'
    '!lYTpn@s_7l*qnQk`dn!;D*0|bYm@Z-|d6VM@(aT;PTaG0kXmC-'
    'SM$lNZ6b!iWR<z4-D+-0efuB;q7as405f(Bp;S*Zg;!v_~gw~AaUJQcD=JB31UxY&Mn5BS?Pk-DTDz$Ocl{#Y|84GW&oj7Ltq<Jy'
    ';X43w%=CcZN+^}RL+gc^3$LH<0U9>#+i}(I;I?Ncy_FDP%i1Ti9%D%c;DLjEMeX+0n!wWb{y8qSVEO>cq!4&Rn4SOl+JpM@|$#`('
    'r_u0CbFJ{eSiHNv3i$+%Iu^>A}x_j3|gQ0AH_%+vV&H0q8OqH)nRvHDBqes?D&&95)y(N(&^$kyb%*Z?3tY)k48&39U*_W~ao>Jf'
    'cQ$2bEy@y??iS`5?yyD5U30?u1-xme?^oi+Ub)0I0T+;$ftD1AxDoqP7lZI)F0CRw^q`tGLvxRF23Tqm+g?!YSeHk%x_G}91{qq4'
    'hQ(`-dMp47rt?UFjJzYZ+YdIZHJm%pieKXdDG{S78qlGq1J16aa)z5M$VnTvl2S!SoboV}el9rQu{$!sc@HNToyUrfFz+5e(@C^C'
    '-P>Hik3W5Z#4UH#;Ysyf0#1pyr$pd4WQt}J3>?*SQLi3>|co~C_qk#eL%3!~ueWBwE<nkr7a@q-N08QtQpNpk|(8AVe=I@$26*C('
    'R$n*_e(U$e&?A?ye`!d0Q*U|C0ZnOQ$!E@Mf)X>E#GO=58OQIJ2J0~%`Yn)pR8b4<U((i0)2KF?+JQ-jY73w9qVN<%YM!g5;X*PJ'
    'UueXgFOrhWwip9bs^UIo<>htBjR3bHZZ*3PB_%0dzLZotdZ|t@m(Q?+x=-evD^l94oOI1P5jeA-f{<){M<@2kDyRqo1J^KK0Ihz9'
    '6*RUF#1+*3i!ba;f9JZ|X-gmOiU)-;^5?uhz5eKGh)$Y4(4c^~Qei6^^N9#|q`{<dZGXSt&Wa1ueYuA89S^e~W?*QRt13a|0@SZe'
    '^2-H9yh%s&R<LV0%kVoAOEpDJBxyTyPGELt%6pQ4Gy5dF_a)8f!x2N5jL<P69aNO~8<#D=BNcsjRgnNYU1}PLQSf%84SB#?PURQT'
    '#w)t)YY)<>rCB!Hc0E^ULvvseF0QCnAXXgu<pEdu>{f}GQZ)F%t*KXzGwGWe{f(T7R^R4E4GJ9Q(ZSt$T@~hB`fNM399A6mtW;;A'
    'Su0GFOxumj7dwL3n_Nu)KWZqjtFuBHg@yyy;G}hpGQZDFDdPHN?UDU?Rs#A}#@Wp{AwZ7OTkb%8@I$ACr#3LJ|*QR8$Dr__aQa4e'
    '#&_x5(PKS-D%Y4+XMl?nnRi@xc*)#4P7n8Yw5~i*mT!5Xj)yIoatRv$Y8v=FK3W|Y=qm5@4Dto(LL$H%VFt-*3?VF2F^W^8$LTY5'
    '|!ai39(^GLxheOnX2Kf5nyRZ!=e>Jx%C)4BE#CC&%6bVu~<4D<jLuNuO9$9Bh&+Jg3J^+i6x$8sE3Onx(5JiGkN2H)3tFWTaTU4^'
    '~sQzqVzE>ujy|_j+VW%D|57q^D3Zmb%#(o~-7}-{|<`hC&rA5$*us7>U5&8D%!+2&1r|YZ)7C;@S&oi9!HyWYaCi68$!{6s0#WT;'
    'muWvmhoYu#hsz6~z0xcmBzw1*5fU|nwDQvf+muOxVj=(j<8rRBNH9yYQS^Q1Y9G1fI08yZ3Yvd>4$15H|oG5Y)i1(uNH0~M;p`Z%'
    'j%D9j(Z;cxmTU!RvAa+4>W!Eh&a5)@z<ET&NSo3E9aP?Pnhhn!`02KU$CkX{gP1vH=xVbh$kzpkqw+I{CWd5JIOxR2SM<^Ztu>L0'
    'b9obDZyX5$l2Up^L;Je8`qcoUkUH}<OtOA316ibf1&5&kF=#6F5z>yiELq!wa;;^$(Tyj1G-e1}E8fdU~;D&5gH-9LPZW)TQ#-y&'
    'Einez<z?FNuLVTi-tpPZv1C`Q?+APjmeOWU)1z(9Yfe*%3Th4T<91cJLgiH_eT%+riqma{%N)xmV!=~Vh%|lx<D`P)7WO5CK(+*)'
    '`au)O>*eUW}@NrZFSlc?+uD#B|Yy8FgcnHarG%yBl^t*+`hOMwP;XSo3M~@%H!&BwGIWDg!Mdbaxq${s|B^U6kZ+fTYKh=eC<rF9'
    'yMohJ_?`+PpOPr^4U{C#JOn}Z)Us!XgSS}LCu;Vhl%8(#W*4{w6M*GW}MH(f}wV>!s%wi9g^(K|eNvCbAy3De-nyc%N$`eDOJW9-'
    'G4Yh=pl{2E3oL$UNinEIo3*3cLSQhN8W6B+MmsO@a!_BvRNn3CXxwxdCl4m6BG0w!b4E267DjbLJj{`NmO)!W@CSfpU0??fn@f@O'
    '~2&KWS^j#oxi3p*l>_Hr!unZeZkfkZdwBA7#w}!<+XV+O@iO=fBLPBzl-9c(nWKN%eH8!ke^@J)3DXT>;0=gVP!3jWD<|!K8o+Z&'
    '}`JEt%_7{mCHmEWY2*XpdX)ljegy@#@IrfA}NHv$%D{MLV5R%x{-a%?v9;jNue&v}(kKD{(tHDY9lwukzZ9h2y)|B&JQ8Y>r>Cez'
    '#dVpYQ0cJ?=fI$O|vtRq}%5Kd35;>gCjDgj_^Sz54<<GQ1g$D8A;$&Rme!p*lD>DP02>skhL%%GNG&CAtwOkz)XKvQWvB$8c2|+A'
    '#8ytZmZ;~<#%pKXa6o={!F~tohzEwsi(vG;tbs~7Sd|F+9SlP<O)8|ShcqksCvlJ+>LDKfzmlkMqA3$N5aaY2tUTUh8fuV2p99E>'
    'tArIH|9qvf?nlO98Y1NNN?rR*h`!B`Xa0M#gjmp-M=pv4zNgnD~4R|4EBXYxL?dc@s-@>+tK)?L%kmy+tO-9(1#!qfkyxM17-tRG'
    'cc2<s_KuD^1s1$a!tBx^VDZG4g;@fC{;PNWt&+XQ>Y(V&Pa%gpP*K_`OOsk#k%hH6o8w&4Waw!3S1L7=CcFukSn#(kFXYbx?lX2*'
    'io5JhFgTI-*-O(w|=55)7byxaq&*X#|agRnSg<<dbYJPtQ4hhYh=@XSY`?4U|=wdR7)2$*~j=CyHrK6GS(Ls+;r^Cy$1(go-qAVG'
    'mH|tdW2^c(s3)drLiJh?=h^Dh`epG74Vz2GZxk&qBs->tax3+F^mOSS{RpK47&P~iXTt8%1o#Cf_Q5O_voug;qL(K^8%lMy;nz3R'
    '8eZvj~;FYqsxqJjE#8znYPHj_0!kOaZ^3rj6WvPt93&Uq?`YY{EGeqXyLhs(;UUS+2j^R^TBWqn;@2Wb8_mxnynoLWGNi?<0$_?!'
    's<C`j|xN$hNG2^mN`vl%0(48=yGR26xIvntA^T<y_!a_n@wWh^z<zaGFwC#7(II@WoyYe}@C+Ln312Mij)qH1-ojPo~ie_R9L#iy'
    'CZ65XGSMkb}XUI|%D8&?@++uquaRrRK<)RBVXjqgT*&+OlC&tL_fHy}zg8lQzyW?`Fe*|_Zn3<a$J?*!eJMU}rWdI#OW#HSC?aC('
    'Q*+97b=m?;?BedXl0P5q72w4|g=TvftSn{Ci>iQrWe7bXBm^@9WdQwHw^5`XDj>fWdKELQPj&gEPsUv&vFn3v83;2k<W8>gW+^&F'
    '6U4VCn&}N-drWnJdBOGLxV)UFm-Zl>7$3E{!!^pwp{m30WI|Ns0hY-AV@Ulr7k}>7)kcJE_pb!y;&lJmT7VX>sWeX$7K|@6iWoqt'
    '=^2c%0;!7RPx0>X5e{yWeu#Rwiw6}xRK^y$ro8-o7C@&vyH4;Fa&UV^de79_80s^NiggyFdMb2XYO}0d<yqabdL*Sb4X6&5=6Z9?'
    'x%CY%r<GlkF#kBIoiseK2Z)!lS6gxaPe~xP%wydzqI3}BP8GMbKt64u~Mvq_s&%}f5fA6sG&<o3pu{G6^<S+%!SgSW=NSb}4{w=~'
    'A5nt(LDe2;;zg5I&@)P99m7<5&U)j8mPDSEy29bQ$sd{e{*?koNjIm~1`d@za(T^36G2k2G)t|Y<`}BT?X5r)%`a8wb7v<eq{~Vt'
    'qO>!r?LlQgy-Bg#XNzyl-2~5R|-0-6xXLw?3UP4uN&5cvwZbt!Db8s98BEy$9K8j#Q>h7AH2Ip1NNcHKP<b0gw<xW6p>UmQHz!mT'
    'BK>$haUsSh8jk+@dBY1z>qb0cg>()-5_Is}lv<Zw{IzJ`KB0d^~H|aZBLRy70h~r8E8fpU-4K?sWv0P4u9gKn6VwWt7S4KHl*8ue'
    'RlLyvgcdO4ArJyZ<@k;ce{=R=ZI-QB9Ch+sqDft9HKg`LQM<tmUaVYrw65w+VkUcl2UvktAD`$XMFOaX3v070wS()4vSuJBu*i{k'
    'RKA%JM|K!jb6PEJPgihYsS15}+q9k66hfhc?5mqvX+ls=t{GvcfOmwDG1O2$wqxpE^aXAk`_{q<I;UN&(DMY)Jfa!5xHdwi&1m`;'
    '9_*DrIBfXoIO}^CFvNpzoY$?qKMo6fbykri0W9qxBZUBVK31+`7You}lNzon1VT5-_NLJ&wnU?0e_nO7n(VL*}9Jp2<14mMsIEwb'
    'x-Dt*bW>U73?O_G~sYRn!=5l58f?gNIx{K%O0t}<)Ea;;9ywLLTF1RVnYJ}+iM?6|?tJxMpTFkk`P0vc@;asD55b}S#5MafX&3I%'
    '6+@A~_1lMb{+;Sd@XQOl1sLq{o;i44M?&KP_StYo&i*@%(@M(Q8W>cgailVcDs~(Pa9$%JRbb=U*czZ`S9H+~I>}ol%X%SE<GtOA'
    '~qfOK6QmV#tnc7|48V21)Ttw_vgZ}Gv%iDgxVFn!{N?VW3uphl*V>bCYWsQ8uPHFP4WTUO$tG*8ogF)r5o?j<dxraT_%I|Xzv*SB'
    'hs!boqJsj+6Z+bBFJCGwGc4BOYk-f`{J@86g72MM#M$Q@?)B%ee=BkgC7D4`8$%_XUqTM-p(aYmk9`6eomfKgNoN<GA9Zx`a`WfS'
    'c&C!-Ss!(z~^xm3dd5da(tBZAT0eKs?DD%SAkHW=#*m|30$WRd*mhDYdr@QczE)7)M$Vj3ydP`^<=Fn#4*PwZ=E}q9j{neQZ@$rL'
    'xb82_^99?LYB(YC5Wi3hjXapx&>>*2RFsdBbm$2GKHXV7pE`At&aZ6B-Cd-u9zN*e`Ys1E^c=$rg6V9Oi>HO;{9a^ggF?b8uLn5)'
    'V1cYjU#XvVOBvdw$-d+CSjj4lq3l~%NF&EjBBU738zv-R&K?ajwQ1Fur!5Mo5GvcZB`vIu-kv;MmUSCfsPnD~D<k7`KfInK^XSAG'
    '_yKkbz#&5D;E{lUf@EjcH!{?ac+`d=^q}9=`mKwjE*Q7XF1F?;VLYExtukPPP=6PL=!?JgrOYKF92#cJv?F&0AL&eB~H{z#YJhDM'
    'I9^%@SP2I1rh+7qDQ=M6k9^@56h!~GthI8@tk^IWV8^jp{MfvbJ4*bG4+q=heTXLJ~lDH0|<(UPSeE>Fu#gF0A%ki}R;}_RZ%cXH'
    'LAvp-bGV3lfe~wj*WiKBbi1$yJWl~A9QH&qv<rN8!bmj7!2Hk#jUf$~krR4NW*DxS0!IC7GSeaT5=FQD|P_kw@VAIlP*AuSnM(Uj'
    'HKJ#9DCIB%vdI+;DGSQ#Z+8*P~e;R%uDS*qceLBXYM_7gaka!HC1h4EqXNRy5+H4svx4S(+n7IcpDcSYT#+sk64&}8evH2fKc3H9'
    'NVaHSi+-CM2ZrZ@qY(VaCxF#yXxCS*AAtG9Vpd|3q+hUH}uw6HI1JvuG^FRw8Mh%$SspFwBr%m^6=J$pNqsOKIbc3-P?p}qj3v)j'
    '6j)V1p)i_z0<48b(%iApQH36;hFGLLcPr$hCUL;8#;NMIhXop_i_I+qRJ~>z!n8tm-EXJ>wGC!76FyJyD$(+}VbZv%czzr42ioke'
    'Lem#;B=_V8zM^G@nmq1>h)<m{a1Vkwvw!EF8dz_9D(`-QVk^n_bJ?m41o6+v1_=-G%2*>AEqrth$GwYEi|8x|<0f!Jn>9U!1C;X{'
    'q+Z!;cBxGO##1vbsPY_|Aph{uC6_;EUbK$Z$4W;H#rBERTu{JnY<?C7O?%^q|5SuW-_RIou0}92hY(0ygf>Aot^y^>0`|i8H`Arl'
    '0bypwfQh7G&B+JbKj1Ambq6_O|=JuYqviGv>x8&7ZvkBx2o^a{RvH^;bLY_p_4S9&gEY~P%SOI12In=5SR6J3@is4Ph%1=%EXs}X'
    'zHdIPwZ)QN<1Sv2J&WeMRXng_2U&KWzn3%316`#$ek*Y0*cQ>*4VnI2#`+OH#oFiT^If0nC0-clSY2nBWLJnLulaAd3uxe1qLAtL'
    'Vj2u9^g6ozp464G0P=&$rYM-Sy55#U%E*K430)J8PHR`M$axs1JusOm;jt^@FyvP$dRt8gdAxU?>S-p`T_eNkm`aI6<uoMQ^eVQO'
    '{Zj^s;+_$L+ODgSfMiZmu(=XZT3NZ_2211-EtAL^JErsB%tlVlmG3?9xL<h&(@Rny>q+M8lDwgf;oD%Pk%7ZaIs!6%wkgdCTfzv;'
    'ra(Y9XQ|xQ3d;Yxg2tTa8n2%@RnIZ+Fax*$x7ZvRdv5^rivshxGfNS#*#EuIm-}FA0|Hu#tmSd2Tw-i+buK^P}7%e^3o&e+CUK<&'
    'ytiQm7=K+R5oWkgEN{FN2sFnDwGs<AttM)*CHMehFwe9=AR6M)Qv=Ur66b<|%HcfUd$E>qAQjkSL>mZ0{22k|^9srH3pAClnhE%P'
    'i&e7*{vDRE@^vD*WV$J(h3bWB0%cImi_d=P>WxhwRZ`oTTti4U_>Kx@j?ye(Sym3&SDgu`AU`*B;m16oBEO+lI`n0^>mR&=Gh!os'
    '7%$ni#ABtNf?~1C;lTll$wHI<QxjeWPIJpS(**19j+-mvsi4r)DYE496^~smwV~GCb9ptwNqMYPh0R@X5#`vL2Ir_fov-_dwx1!B'
    '8v9DGPU93)u21LY~MGVCS+lqu}!D<4d?xNUTX4sesKPI~b`K+LaxPEBd8El{oX{RuXMuShVw=F}9dO96GBIz*=h_k+jNBa=0(D<v'
    'aY-i?^?vBp;XcA7##M)*(8}NjWH37w>jQ;fu*`M$^Kg>-c^`l4?kO%0lMlsFBz9y*06U@oa-f#Tb4>USDDqE;LdEn}Q4ZTP-h|fB'
    'P=nCL}^kVd{6q7^)W-96_u68i9)>*jEZ(vX5dL4e`PfJ(U6ac6}@m+F@S44(bxn}9J<5}pLp)uLizSL0-w$pgm%5#0F*(&lBsKq|'
    'x(ZEZv057lby^JVj4^=lciH@tX{i1ltXbbr8ys<g>k$+2A1h|7BNS^K@PczabOv_>>h%oYGOC(1`PlT73#TOpGrD(#S?NL1QOn3U'
    'WXL3|58!F16`*el^kb>f6eC8(%$Xhc3ElyVik5W)@olX}mT}B5+vzc}~oj6}Es^JZBvdQy(yd(0&73BdD9f%HXL&i*lp(vR^GZ#f'
    'GUww6~p@>~wEOhztfQO-9Qy`1W_a69+uP+_<5r<SpwJ;dvUdZ+4vME6j+|vD^WOj6uReAJORKHwM4-f-y-l8rcp01<_p}L3<&Sm;'
    'lB4bfCSM<o5R*+C|-?_IzX)kQO;*yUO#1B^(v+~R0+gpVWGOOU=kTYhg+fyVeM6~g;j`7a?CwjuXo^chlsqA1f0~fvVK`B)|eD;_'
    'K|EtT0b=P7HYP~5X7b;ei?CLpL%b3gnI`3$^ytN`9+8Fe_;^{#^pwYKdBQrR`<9rQ7>gEfG%AbLVk~t$fu`n-7ML%CII&DE$moe-'
    'w7mdZkGo6`BS)B6RxrY1DoBMdWfhyd6oJ3H5g%J1)Lu%j{&;k_-G$2TP&fKmKBqR;Az#6l3ju$%Es`i(}LP?!}_-ML*`o$P{t#u*'
    '!VJ(BMdUW-<-E>}4D}ynM={{*1rlvq3pPuT|AlIga^P>uJS1J@O<V>a`X<Jz5Nc#kD(*8JI3C&0xl@-cUgH$?4ltMa&AvOLUB=us'
    '#JJ<yKKGjZ6f~azv+G9uzQKd=+VMoP&(GN;NB8>`0vzLYqqCdTOP+finbSlGP+QG|>S+|Xq^Qws(BIB^-)VA?K+OXkmsukxSt**1'
    '6l$XC0UBtdCPHX$b6ipSnv6lU{24WXap=o?>$&uB-O`b#x&(JjVrcS?cAOv*^z7~U=I=-2li)IH^8Su|knI}f3=`Si=t@mMr0cfI'
    'N0Nx<1?re))XPTvnybhU$A7#*qPHj!|Yt^j87e?B_T*c;@Ekj_d;v$63`cGZC%>?Z%y=}dDijVzp!fFD&(bGPJgyh1Jxu&G7AF@Z'
    'hY4wcZa1~dg(+A#w#qJy$7Xg5Ce1#P&AOG^BpZv7(e}3}!f7|%cKm3oMe)5lvpZwyZ4}S?D8*HlG4eYmzHQAJnGGhLPbMkndbcB_'
    'ICsF<|p49^UB6w8fG)Mc#0E@bo37pwL#V_nt`^LqZfUz`u67P-3-v*<#WWDzp^kDjYFTj!{2~0Y_X}d9<tg5KY$#DaOEEQ$_s`EK'
    'wBI6a9+^`|f4w4Q<ycM}u^+Eh3W0jHElqA@<?CYX7tyY+hYhug0q7$qf;TNOvup)$d0m=$$G(T<km6?~vQ)1TfI~2wI`c37Szxm#'
    'qzEvU?ZRgE#I}f{<)PedySa42EhQNVi|5w*GEXSZwjc0|jF@=^Jzp;HzO%sHA>TCOIiuts)0gDttW#D?xPOz#AscwxUIpN13pao('
    '2(3eBoP-*cS+I2A?AJ1)pv2Yf=-v;>9RHYjr!#e8=%9#I#5a(~c_l7UOpQ_0ZHuBsmQ2cx6EZR!d#<9AuIy59chp+Loz8_(YpBN@'
    'A^DC6%;dAZ%h8n*{>VL~)59F9*GwGtFH(VOi3$$}IKE#{^AW}mI%!tv%MznRgR~e<QDgsouxu*QDw(w6p5qd%-jqn25YGVMnGYSZ'
    '+j3eZOomL43HrDDOa>}B%bSWI))3%K(h+}O4?@X3=P!O@GK{+LqXAj%Dk$y09{D`4w&Z&G_G@^aw(N(7z$_6%|mfo@0%VIoAIBzw'
    '0s#>F$z2umHMXI0}=RJF~PBo(GAs-l*lhwCaonDZ4y(}GBH#W^o=-;S3H7uBB85%3S&p~$lnDuNBPe@`|->(^^ykKBc{c@BAj?c*'
    'ddb%A9{^WJ^WC*eK++Z!y<`q?|PZp|Z-s{R*owZGl(s+C&+IZ;`Doo@+#yxooltSNyj83!J%(S1CjJ!#wTucGLnVc!hw^dL8P>~i'
    '{7=Im&56Q&2(sSLdh6i;0B$?vzwVIH(Y$@)lvk@eH-p?JwoVW4M4eWYxje-u)ro4b9cv@6Rt~~Tiivs$;RFhuiO$d++Q>Sv}M?cP'
    'l50Yy{>Jg8XIy8UgY$k3;)pL&H#r6kk>z~G7kA|YznVuA>+~w1Sc&yL!p`@-$g))@^CB>)d>jQkl3@8lhqNpz~=1XGCQwu2Z>y9Q'
    '+`xA2mVKQ1Qy{Du|H@udM2O6<Dy0>hKFk`oMkz$rj*7!HyMuTx-kTgA8EE~vtGx#_Y))%mRfc!f_bpgY`56-ZQHx}hmUm==^*$1y'
    '7`P{em8ek{34-?8QE|(GpAg`+T;e+cV3T(09IA^Y!*RfQCj9?`*`g4x@4dtm;5U8_FIy(w$m$e?Q-y_zmp0zhhgX4mCeblRHCY+b'
    'A_T^o57)C&eVFVk-25>eAGRoK609$bFNUd{n$jX{1Hw0Co>csqeI};l?YMS+R7?5080&m5)Hh#8zm<Wvu^QUy2e>fd>Y*_(grcMZ'
    'EjDhvB*>G~qa92}X%N>(*!_M7u=oCTS8=a5J`P49?9e_qLIfxAL%Yb;Tib+BR(p?m^tolO3>&n{5-as@?<PMf_zor&50Y~foWmk*'
    'nO%m1=y$(nr67%xx!b+hA22_-wZ<YbLtUVv#r@)@B9;-S06s~Q$H9)er@;lWhtKor)r_WI`_j`-KVsaBs%7+%YRoM$g$6$#D?kGq'
    'puCds4Vp+ynFPXLGN}E$@$6{aq9c`eO3=g0`-Ej#~c6wjdJhP5CG0D<v!zF7rtmW>;src*bXbOJwz3aaDJ}4WRv(S1^P2~gA;?NW'
    '68gfbzcH7%nAu*>u`Kqd>-+b??Prv`CMcb249g`0lW^|=7m<czrMr~a=?n5y?43UWQG>L9((ZDIt;d5K0^5PCN8N)PO-Wo|K5O7u'
    '{XreEvHL_zgI35pQ#G?b0a`^V~n8zmv=JnVx<BH^lFk@DkNG<xSpKB}>dyfQXyr51{huMY%Togv%>S5^&mDSK2Q9@}1G9g4v>KN+'
    'EAn50?03bzU<;o*`aJ{}#kB|81$Bn*}fhK~h+1RcwA=(_DEsGQA>l*;yTz%x(_~`!AV|HL6)g0+UhBtIWzpjP|Q6N`CL|!7^`Bxt'
    '``bq{4*u^=HWKv!yjByUg+1>GZw%r#<z!h|L5f%WUu1(i7)Zn#zDNADlh*ei8M8<m4gUBbMqe7ZQITi8xzLnKlJdHaSVPqg-*I(G'
    'C^y~rpRD}#}*+!&Sq-Tj`K)~W@8J-mbS&sw6`ooB4h@I!+`Q%jE$50QF)+1|LfdU~8Q0-;P<{GK2r4)+hRSOp<vCjx{YnlmM0Ww@'
    'GU1tlkq8&l7<L6YhYJ8m{r9cWSfXGNYrq#B|ST!7I)%M_CMXM+UBlp#0BmI`)e()V}Sl#Jg%+Ri4;g=3W3qLg1X{fW-Q#=sdO>Z7'
    'vAJ!EpJJRtn_ctY@NiB~9CQ}t`UGWz+rDK9_*`!f*Xp9MCOn7d-JhKUfW;8Dd469d)k`1dsddkv0&~sxeoK7P?CFb13CVHG02}Mq'
    '~&ICdugRedDlA`EddO;k$oB{tujYncsn7vyec<&0TN@t~9odBhAmM^gVqfaAV0rh5pk|Cx<L#KeY4H<GzATY7A$+}Ut8o}p#Ad|Q'
    'TIIBM<nX?A!Ep(^}bqhc<Rv=p)u4oEC2RFo)Y{@#B%7PIBqq-`AG})#HSb5oANMqK2YLvZ}YEP9j51h&$1RReiW#!|M7u975IN7F'
    '^^9Shc;Zr7TCBR^}PhW{H!j5tUC$8X&^nrL|Q6ZBP7IkI;Nk5?p>6(!+P!p!I=!j#UbQ6aAY6B!xssxh`7wDN-J0|W(4`D-duV24'
    '`7eNWCznwne`^M*O@+Nub;Dz1O-pH;HKJSeerk)tM$$WcA!j0mkIu~+0m8HkXEU4??W)p{gHihB^`j4*dSlDTTI)fzx+>aSmo0%H'
    '+ivWbE5Gq8ECeWMS<4?@gBdFR@-<Xs9Xe2s$ZSmgXOnF<I)bD*s&<MDgQ2oAZ{OzL`0BSimTVC3zZ3yFXavToX#fn^MkS_|Pxga5'
    '6f>g^S4JWaGT)9}L5Ya*jqfSvzXjrYvghNFEk=o)1^zVJ;t;b?1And(2=5uhpaB7VDWYN*3Ca@P@UuYUj93{=dILUPMQbw2j-W72'
    'D>X$#OCtN`qX7ahek+@+f5ngzhGz8>(X&oi*Xg2i5mWX85NoRiW!C%868lQ=Bb0nlG7oTVT<_GWH`yJBJBu;u!@E#xfUCK=hCC(8'
    'Mkd9eMRSg?&+R2<Rz)c;<Svm?q7G;OSB=BF86Py4BpnY^W+Bk^vN7lDUd_?tk<K7A22;B9WCFV@AlfgNYx1QvNe?V`lSgu)Iu4&)'
    '}=)J0P0NCanr0bf@%{2Y6tLN_B=Fa;+YRZJXHN*|#;OM>zLqP=EX(`$B_`v|XL&i%7;#TtSpIYWKK~2h09v*cp1=q6Rq~7>QmS;8'
    '7gdRXmXtklXJ!u8B>-a-MfXlI*UP*42K`)yB`srJrb$0aJ`}8fjxABY>AIGzs9s<UK4LBXU8<zgtSOk3Z;Ue3ivgspdm4>D`2i$2'
    'Jv+hhK{Js_&)MH7J;d<bK4n(<Y$x2zd*cClsg@U5^i__s-R~PfZvra3snRc%7{6YMu*-efp3#qcD1F?y?9qNkY#0pv?&*b2OY4>3'
    'z7g8V8UnKM31F3Jn%>W}w)<74dHUK&0YLImyevX|!5!ZI;I)}TXBn0Q;{sCah08u?g%-8hR5+7?DSpg1}gKZ9u<O~jBS7Ur6@i@u'
    '}Z{N~DPlNBmuCRtf(a@07IsWM^&bgRZOz5x^+DZwk<e0LVGJpO}@6=zQI0#K4jAY<g%esqxur;XG+A#(IN^d^FlG}g{X#dmzot%9'
    'Uo!lh`wbVKzM25A*A&d+ICG<wrEFyRYn4%aZ=26j(;=*5^tT5rkRVSsm*4@5jj@M56g8`tZ)nw%-+yn?@X~GSnQ3IODcIS^w5?qu'
    'jg-1ZA6RoLTQLynfz@=$B1KP{xRK(&AZx!a#3>xFIYLu<k6i=)JlM3{5Ri0r@tqPKX6AjR^8hL!JJUqn8V~}d9XJv$(nziD%J@=L'
    '(EDXVJZP~4}@t>R(O%(I6tN3%}Dp)h^Apoe6dZY|N7+_oteHQl+C9WlQP-@sf3cKbQEk4Q35uB|=TEN6ptJn&VNS+olrzvfkv3H#'
    'u%J~JtZ|7n3GS5wF-LO{&Ws}lZ5N*n24bFS$+gL*prT&81B|>m=OdhXXtYe@W92h6BQ019S#!!?ytoE)}78awvq07_x%Au<|Di_z'
    '$TTy*Bwcjq#c5oVN#a(bM%^O>su#Esp4IK3e<pK{S=Pqf}pd#00=-A(n{iRqF_VpM-+PPVK^0u~?bOjLqFLCew9o3a)3H~d0(Q8d'
    'gqR9YkFzGeUS}s>sm8;#EIqA-+sxh8MfNWEV5e+yq-ILQx5=aUOJ$VU`gd`9k9(n)*Ng*Vy<@rx+MJV)B_Mb4{-upWzPJ|wikM8b'
    'Ookmi`z2}~L&Ue1Y{`STPMq8W?O?pM5Fl8HDZPf-o4c%FP8%~-?tbwjh*C{6bGxMOLev$^_pFlZ()qH1HZ?+S}9NxW|%#7L=Yokq'
    'fq(`O{Rk{X_In`<rQhg*Aw}ciS??h$2s(sWsbxHRWk=o<}bc4f!bfC1XgqK*Tq;`(}ZxzO$6cc2m3w<H(%|yv{M`qialRBj|J{O('
    '~%MwY+((_NO+;+|6xXYy*MaO99_(=a!b3hbVt{|Pd^eWxbv72Mp$Qh-Fk*UzffegX0ZQN;p9X7=Fywk!ZuOKpjEj-u6N3({-k%Vg'
    'sq<jGmufclK2}>IHB>}swlZv%NibWk-(P5F(;gXd}z5q2meUbKH%ex!stGqjbTLNP2*s<e{=f667=1nYvXB#hkmAlZKGe_j?Hy0Q'
    '~^4kpNFTKKZk4$;7@MXWb!sr<0J-1~bjLuJtFrz>1o-@tc&Mc0_{3r;;Qx?bQYF4p((C{GhM)Bh+{dVl%smGu_FWhCKv30X`rqna'
    'xR0_9N^kotfv$x7lpR`FUCBk6C2u*6FX}}`~dzi>m+f7FvYe~e#5P`VqOAV)NVE_^;w9lH+r~;qzzJ>ND`52z5&8Ko&+jJG4J=gr'
    '@xu)~yp$u^H)cF&qo6mo9u4x}rJm=3gop8mk2$D?Mpp^st^GZG2RgJvJQ-CELz60=NkWs7BRC5uXLf_Fnh=A6fD4vHpM~#Xly_KV'
    'T<kl$Ejv0gU%ejyoY!d@<n6k?xV{<lkC(2T&5h6c<ECa)WlU=!lh{IWi<=8l=BvH*(HS~|K^SdBh(voUbS1|pLKfdk)rXc@H@n4l'
    'RELp5`zdV?MduX!YZ9JVsT(ZZ^N&KMo*Bjv+ad7F)FlbgOQ*NK^*jLD1oxjk0_E?3)VRZ<IHXclob|TfJLt4T$7HBd3QYV_vd~qt'
    'slbmb%FW;EYMm2?$2vnDKdU(DDS0W1xW7)CBlfON6zWLm@TfR!zn;Jh8gSb3K^<4CnNR&F38#MSpC=@05kT2}&b-k+Ov6RLfi|~f'
    's)cVv-{-CXNXT*m{o)q^?^c7x|=c&bG6U<?u8;n9$FI{I~7*sp)XtB`2j{-pm&8f0g$XQZSMDNaP)I&2Oc5~AUCx2yJg<hOXi#<@'
    '}Cf2xS3&oM?#-zxgKm-w!K=LP}{Nw8}phl2I8!gW+2u=VKA~XqqU&;@nccG^%1%|6C73#T_(c7ytzloDgGAgywNDixJ`t402eA1%'
    'pf2?RT=E&q;MtVS{9kI;s4sATY!u=uIeu5phkh!8{5s0;;ZmBC2{$t~rlg(dzk^Qpq#BZ7|WKs7S`kl>4&73?&*5_kqn$I-t^M%h'
    '}O4aK@s~Gspvv<?x-G7&93r4!!$_h>2PyBPSbp-vGBhEyuFJo75;<WIzmBQ4vDr6Kn9S{)qGHt%t<{%u71N^;7kq^%*s|VL|_6GX'
    'c6wk8(Jjz7<xng?bi4#p{FEsf%^4QfzU1SFP)N_Z&&Ncn^RMYQJ@;?^w_h2fM1{Tvd*)M<fcO)xy)~J|ld%orer+E;)tzv_yIzF6'
    '>_Lm=i^dCO_ho9~H_~-xWSHG|`CyQT0%*t<4E|$8O$kL$bW*erV;g|cpS*xMp2at#U@_=L1!p{etGDLhT_^mS@{yP=yk#}P920!u'
    '!S;G2}io(gfqg2ccrL71%FO-iLvxciLs;`=vD?1e4sG|*S>{R#Bezb?OF$C>^DA*Wz+RAgSQK4>k!8%;q+sXksexrEZ53!R3Y4&0'
    'J`q4dbS7w(sSEx|1h<fW*Exqht2nfdDvVYCOY1;FDWlW&@VDR#T=&%bQqla(EY}3&_D#{;Z8yHdYM5lV5&87r@DbGA|ObjV=eHbt'
    '2T%tu2wssSh2TG<WfkBo<c<H*ZSKO}np|pAT65zWa{#g~648fwE;cSpL+s!$Uv*HS93sZt)t1m<O0)bJ9Kyz&gxH8EoRPrxfe1V('
    '|bC)QkaH-1ritow3juq<D@s7ssu<((&aH)K8U{=LVuCNRm8N*KT6fx?djW;6NtJal}M}bX7QyD`|o0`p*Ymvz%RiUeJeDShaQ36y'
    'w@Rg$y;`(AYgsUYi)MAmw9ib7!Y~san2<vRhw)lNxWw1uU2jiN(1lwUQQRg^lRRi@C4p*LB+YYdjvE>*s<94)>N6G$b%PoCeQq$k'
    'EGgkuytcpu0K2Yg$FVFS3NZ;M@t>j0|mY83Id#%jS{)X4nQ{{T{y=Q@LC$7Hos~1Qn3_Y?X=>R(R)M7~r*H4&_yUQJHSs)5O`-78'
    'TyZjBYX;CCG<q+4F=0I&OAmUjyvpo`KER79N?QqD8Zd~K#8<)ICUuDVsptFc9JS!n1<P(Rwd{3904~G>7&4y$W4`DyE-5};VZ7GE'
    '2f;`3mfs);)PdPGeGcO2K@9Sb~|Hgym;-tlGBepzHVegyM>#Lp!uzJ`;JnVH1r+f$Eb52d16qKW%EekD!X`iIJwmECIOfJ6ADA+~'
    'X!f(Y#J<Jwi_66CYx$rFdao~_oaF+r5&S&0V^UR16lGq2`Tj&uiIQ@L*V~atvKV(&4M=ISY!m1ItsZqD#F;Nl3NpZn;;HQvVV0N&'
    '(0mbDEqUXu>ogM=^#D3c!Z3Q6zNK1sZTl3*Mew2cPe+08*ua@x;p&gW0UTs$uIIb?wdJjVk$RBF%8Cq9@woWqf?-6f(D}s4-KWx<'
    'gUJPlH*pPIWRt1R2-c$#OvY=jh=C^Gfuqp|hw8x_ro8IawbLv?n7EB64*;`|G(-sQOH>m3h9S)JY(v#j(n+L`(kXwMVa%4*Caca)'
    'N#0}&ryD*GHja#nLvAi<wrZMQrB(r&Br`b$JT6`)GQZ~NgcVT9CfFMV=$`xN!01eqU+oGdzj07)}ojAH@^WutJ5-i-eQ&ZbXoQ9K'
    '{-ZXkM-v5UCx|8#-nlzgqzbP*s;(zZ|wmA%*2<A%DlAP&3A;DW-icfIDT>Bue;e}AWD>yx}acC--yd)lO_z@yCTx=0dN5r0{a4WW'
    '2d)hSlc5(u1<Yb<}u@YWS7fWwF{yr|Q(BelD!eHe&h+r67_?5U+4q%%&Z_(1Lu!AcRQL;+BvDRZnDycJ@v(?>`+bwn)6_UjUnwWE'
    'sU)u9{zVQW_=TrsK{5eUN$WH4)?I4p@$!6QV_)E`ZIMF;5OX52`dS;g_6a<V8WP+N-6qNE$zH^+i5M_61n52J|ZMHpud{F-tR4_t'
    '9%MZKmZZo<gt;MyA_TR`W4<z7#ZI;Q~=A<TnNDARZ+X`#robRD0C6P%_BNMOxjW3|GGdza?mYo`DOQQK%^x7`3zkbbjsAuI_E=Oj'
    '~ot1iOg6uo2>vwjpuYsBbaO~(qkv(6A01#k@hPK#oESsi#K_PkEX&bf`b=!K>(OUa-#?uaW_smS?)WWHx2+9wk9%X@Kup<+p;;6J'
    '6LuVnNCKG{KJrRGd5+AB!m(2buO{6I`T!3p%sRx!VD&$g2RGl6BJbBw4Ma>mE7uOfBRd`Wt*Q*zl-cCFYDioDuJG0FVhID>C9(QV'
    'zkZ2ZSyp9*}ZKfak@Lu28Y#C3lW{ybl{*Z1LctI*Egh~`z{E)>QCp-P^B#xN`+KRb25A2u;8MdWY2uOlPPh^O#I74|?nuQsZ?gR^'
    '*JB=h62G^GE6#ax)l!)Dp*y*$kaVa2kx%A4LfRp?z*+d={=lcCXbykxIhU`mwYS_&9B2dVi(K!sGW0rl3LuppQoMQXLd-_D`{LoT'
    '(z)iR|TS~SkZ1}ux``_1R(b>_^(9^J`$qre$@V;RA$fO|8vV!e%#CVT5R$y=j@|!JGq9g&TeYfUN@P=PKv~A(Qvl(}>tY+#K7klR'
    '&Z@Z-l?$4{5?4swb;z=U?5>=m&w<POw1$OJyN{IxF1S+=5ikr>cSedcUM_Q-AIDqP0?A3_O&dy%0yxyYI=2x*Pi4+5%uI};ZvTj^'
    '^X4VarYgU$a#e%9a1zE7bwxS-K&8w?+ZIMNb?g%@s6|G}>QV(YBI1s7HKrhPcc~AAC4BkC#My5P56=uevu{683@9qwk#+Qo2<0&!'
    'X(E8%4y;Z?oY-exY?)NL*y#q4u$!DeO`A`FQXPU?#^i>D~xA<7Y#d2i(yZ5{hOX?7V&JJ7Cfk0H$knz@$QoFZPnxVQJ9Ooc=sjpx'
    'r$6w>dlea6kw7I<8q5e7)g~DsBZrsRE7V}R6T1`%gB!$q#{SvYY*Opu<Z?4~qJ@^_H7F}G|K89BpsRno}xb3q`2`4-5px{UVxCJn'
    'Q;Z<^R+7t4^sO0GaviXXUoxa?h&>)Q9%%?Dx2$r>@Q}&f9Iag6SN*Pi;++=TgZO)-Nb^s9&Br;<ZPnMp+Zd`p#9=FkoAXI7fQfaY'
    'WS5Vm{L_La5u|8cRq}3rsosWSfE1(SQXsU|FCPke#hSAoe33)jO8WMW5ig_Yanw}bS%tNZC-Aaj)N;!lxgVYxbFPS$pwYjE~1zqM'
    '&xo#9V9;gO&wRHVnBs!?buBshP%Z~CHo9(?7T_%yT>r%{m3Z5vs5fG4cj8(XSEUq-0720gKMc=6I1jc`d;lRK7Gx{R4h;>m%UdfK'
    'j$%n;$^Fi;#<puH;8U49QbF*<mTPROXWQ`-ruW5m%-KpT<A?1R-p+r4u=C-URXT-K69I075uX`vI+JdwMEkHm!F%uv5D+ByqB45~'
    '2*A0a>al-^eiQS^Jpa?~`Fq0>JRJHlj-SiZ+&Erb1+!whlPIpdQ!V4bZ1zT?m))FpQ<8G=W2|1TOCf&7X0@aiE&pC>%2f(JuOYq)'
    'kG_ZgI5^v+-vNTRz?TK^}9ul4T2}i;ZLcwm(5%ZOoXQuxOuP*^ru5}d*0ihfl@GW8Hvv3^%o2!p2XhxLVXm=!Z5CwMha=8Y0go<N'
    'R5caq{XYQ2pkGC$;j8J<=kU|uu|3+kdiAwEAj96rG@dbc~P~);#^>V4d-;56sYr|_vK@bjgLe{_-kx`5?rx8};R(bkvd7?#z$bzh'
    'RYF}tP&NA9F59?{AV>1()XZzL{pIaFJN13ibTNGh?-iROU4dbm|ylfhk0CHQ-lS`)8UV>JQj${95a5kbLax)V17{I>F_S-B5!CMy'
    '%DqVZEG2G2UE}Z_zn}|zr-73O`FG7fl0%s(8CqO_P9?@KZ$AZ^}rU?><@H0ANvX4Im(wA*=*%@;}zsk;EXgo)|)aM`MJflT#8SuV'
    'h`-rV9CKgF6$-bBn{Rvu(gCMlqR#;rM5q;m=sK*z~X#~e{0_cnO5K7HTK&TMNywQ3AnbVr{o6FbR1ru-@E24Jr_YZ)2I@!u*w_UR'
    '~NYzI1+8WJTSDeVdf{b3Wzi~QLafGppQovDQy+XgAV@GKOltV<X$?z(X28k?dak3Nreq;Abulp;qcX*igyq$`0)MxLD&I-ZMFw^O'
    '3%4nyCfZAL|Glz2!5;Dc%VYIfYI>t*^SWVjRZ#;p*h!TB5J*Yvs*g1_hp=sycliL|pn*z|av!L&*4HDm99Jlx(YG|PtZ-4466#JH'
    'IzpUUxe2Q!}0`@@KYyaGI{3}Rx;`U18*yvwJfZWt$`b4)qQ%D6Z?vOSRw6MNq{|K!$B)wPc<EJnuVY8)w^ZH1otBU<9zA)@S6WWI'
    'iLk#9RL`+7eCwA}hEkwOE+;wGMG``OCMXn6<my$QEL$>hP+hojYu-C<0B8%Qd{~d)C0?3t?1237hmcD5U*Kp{LOr;ziHF7Z3j2+V'
    'wx0D=;?YTe$UX9LWlYQP(Zi!R{ZtuMV+z73=D<B;E2QWphToFOo3=tNcaaX1=22@BTgieT9T1vaFt1*N$Vc5>*zuG|)8cZ?RAn+1'
    '9deyEXhcWFRPa4_8enBU~cL8mJ=aF=Z2K%gi6b6#C@Z-^B_2~aaCVV!nPtK?3=*HNi&6|-gGPL^xg<X-{Aq6E|l;pUpvG5f-H<>s'
    '##8gZXHLo5hOQcl^GVMy=ZlK%_Cr(utOYGGSCy^ki-igT6%3ldxNj@}P;<MV`+Ry81e*<m}h(s!keoL6=sm6ULPB+>>zHnW$=m+o'
    'nUGur$d~v$@cmJc1p8sZJIn(s*zEfu|G@WZak&3GQsj{)#uxi`MnbLwF#tNLIu74A>4P{!<F_9lqmO?GUo}75r7C8AOFy)L;_5mW'
    'pD}M%b3=vifw0A{&oANGu2R1jZ^3_qS9CEVDeackB`jCraXTEJY_DHSX7H&uvjYPU0;6}C!DKY9FmHbCgbaa~1w51}b_w*{kl_-9'
    '>05lR-7U70!7{<b96x*y{<#co7$x~;(v@bP%efGk)`0u%M&1h9S|IG<o0O##rw)O$*I%)qr+jQ>hQ|HkJot<ntbE@ei4m4+$C67Y'
    'f`%dd&gOH^6`igt~ijBd*Jo89%Le%~=UFU}&w1|Z_lE7^t>E?oq0l(~TB1w#w#Hikk5q9U|gN@M^2M&l<;YMeq&<&{_3(*NQ+9GY'
    '7W)BmFk6A=iOxu!Q5^0Oj?LbLs`<p^7^;ATOytQ^{u2YL7z9(lLx#Bp#(EVVs64#xw29(RNiGo979#S`0yPbMJ{HUdgM-'
    'xr3h{Rn%V%URuEn8j_z~WhY@M~sP$@v~&g{hLL7AAE@r=zM-AmbVKpcvqZ*DcBsR5YL^;?-Jy)sCnMNgTXrD$GC;!!xicaXkVZf+'
    '#(qZY}}CzxBmy6?$>0LWi&cE}`ZTK!VxL(Q)yjN%dXtTYfr-b!@WKwmLBtLhdc(*m3dlNUU(uq@>O*4pLN#nf0XjLL;TM(^1HLB%'
    '*xbLbgE{7uBsmx|s3u%1WyJ7?j9SyxRJ{D{RmyYqSz>E~IUyWM<V|@EWtCcPrb>&;ukR=89KXxod=xQ@SCMI#dW_SU6U1ypwydcP'
    '*XTpy^xfnqm5aKCR?xqm#`Lm1FF?k7TSGEZ1&PMZn!LD9=ixR+R0SkswwZV@=VUWS{=xm(;=<D{M@(*p!rRtVCJYs>^yJ3*&1m&L'
    'TR{<f^jciE--Krc~oDuAQ(@1!_@lG3f&XC310UW94~B@NY*%?(<_lSy*J|xw{S8A`pg_TiYNN*|z9*P2Ys&Cji*Fj0J+D<>$gAN1'
    'v*$f}ry;k=x|T4=eO`n+qNH57=X;n>wz(DrE+=p+m~qzn}89xXuMtE8?jg2OHG_DopdX?=%=M%wKyJ#U7mk39Vo)oR_Ie+hMgJhL'
    'XU4E?3G<xkvgxIN1vWj!q1g0xrCT4a2LoEGYtgpd@cD#S>e&f+^VBV{I*918=7_7i~3{s@dqG0BuquQg{UW7kDV3f28p&_Z{7XfL'
    '9gXi!X|u<LIL47%R1PN&XlGzMBLCpzA;!xbhpio&Ye?+M6a<kM2>Wd-KUnA?!V6&1~yNU#EO34?Me{;$x!98=5LT9EK}H#y-!9j-'
    'hhGFz<0K{Gig&tO@f&K`>N%n$@B86)-QtN>~iVM<IfVI^rnMbqRl`nG$aXyb$Kv9hPp9-#~8yuOsPuf49)3n-6Z71zlgdT%5dtv>'
    'zkFqkH1Ogc)%G@;yvKBO+xSU9|+>OkPOB!pLf`x!RV$a2N7I-NN3YU@xR2Ji4cf90xV3m3jQ!(BRnQm3jFmql5$|uyW@%jD=4Mn>'
    'gQjpa$kq;Z5kkMzT+Opby4q;DId3(LE6@Ws9ccikh_W+o*Ev1RiuyxV*G_HlDs#UM8TaJwnjqjW5J!GiQbiG(L+;<kdxicv-cxYP'
    '|%$_BN!}En<4=9MD16YH+iq%X{C~+L6Nqh@EXE<YtSMt?7+`Ex5QMTONc(Gdtc<cj2nUH1>@ZhsU=d{fV>)z-G_apyD7z|APISz)'
    ';qo`tQjv(V-g1PqXiV!sd{aEf~6AT!R?fubNIbHJ)$Ee%^ec39kG{Up1cjvgvg5mxO@cSJ(x;*0n)fM?fS;rR%WVg`A4$C9_}JAa'
    'GcNd|i;;<6PUuRDY4<=J<F)h0?rXrhtKijFjzv|Ka~pc|x<_dN!htut}F5*u{f_Y3AyLWGdjRMZY$S#`u8EIKX{&`Xx0UJKv*-OU'
    'fMYE9><&>2C*7q}Sz#`KWBFj!_*%0;sDd1ke>x(t30HF&2{oX;;6EhqNhTkmXcRa<O>5qgWWq`440>R`HtfjZ4DXx;HSp6p55c<%'
    'FFSC2o*Vq@jp)y;AqHQp=QResS6`5?x=uys_Nt(3+9U5ijp!;xSrofh+dmFF%g1XHZ_vDwJ#?t?H_+w)SZ@;@#D`kwuPT0U+rtDZ'
    '7g|Dsqr60!r;{%Fo%N@i#QNYNIO8Oo<W%gB%^^R<Kvzi@;#|T4iPwq78WAs5mfCdbkpobzD**V~E??;z;ugvMSK$&^(C2{UzoHem'
    'P+$%DsXN=?Tz-#5ACLo5=(uJj77ri+-rp$&Gm+ks<+OfL}YcCg;fSMTRCty;yea4J`Ir{6yD%X01GzkB=bK(~gIbaGho_cL2(}DT'
    'P02n_X>TgdEH>rXGZm(i`w5%S-4$Rd?RKmW}zlcBXk7ma@tbZ!IY-o}hiv9Ls|0#03WH;P)+8-_152_R3V+<tdRpB?e;{*m1M@x2'
    'OY71!<>W54WxuaY79$OprV(N&_S6j09;Iu??<~BDUuK$Hj>!6^U^T*k<@31{4#PDU*o~TetYh3aV*4iEcwcAhtkm$O9aNe35)wyA'
    '5CG>SmF#vYhQCPjVcZL*6^k{p1~BdF@qkj{Fiz8@eW0SEO_I5mS|+`V5pauLL*IY3S$J=5sxj^_2>)I-M{bb?6VSp(iQw8p{trCx'
    '~2E`>T0eB*1eza61vGnStN9SC(9tdT$fx4<IeM`oYsGYAu<0b)`1RZdL<sQ#_yg6{@GT8pGe+4dfG0IfcOX|4LD<!fsXj?D)11m='
    'i-Dq2T)<gye_p7`FdQZ<8{FdGfsaqTA5V>puR{StfEHk7d6q7gIG5au@W&8Q|<frvR9WKO3GW{sU#+V|qoqF>)6Kur_MbwgYQk86'
    'b+X<SS2|57P!UZVq5%I=6r3Z{X)z34!1XqA{J*?RJ3d*XG}NwrB2{pxO~PWpCq6vIVJMtg9lo+P=W0bNRlf`TAyycQ0Z;QBn#K!N'
    'g0|Xt0I(qf+%z6B%bXwV1KggC`f=o75*ud)3e-aQS|`k&L-O&|2fg!d1sT*_)BR)vc)*A3&38Aa6Ul%H>c;TmfRYdNu_L&IiqL+Q'
    '@6{SPb1ZTLxsu05?%tiX*A$RI(FRR|e38@LuE<%o-&Vh20s5$sK?^KW<jk-)w6qG)xzsqkO$OBz%zX9X3NqX5%kGJ;NWNcZ$fI)H'
    'y0rZYQHdRJpCsjZ3dKSzq2}qro;2uAt5un=IRTt3!;n95dv9Hva<@UQ`L>dQ(Uy`5Z)*RC}(1wR3z9ZYMtGkHi?G-X<hiD&52WzV'
    'iG$oPk8M$HwKtGk=;ukEY!#!0ZP?%93xnqK4vnC;6?Vsbk=?fa`S$9pEu>(tvu@pI31TA3EOjRpW0@HJ{rTh*xWv<mL4uSJ|>$UL'
    'BMhTFJVo-~*ta+^fPhIEEqT62%n|aB>%HUSIQgXMBO7JlN?Rn9|c;y8IMb_|Vd5SCBHbUUMXjPW^P1cq+hKRsDx7+A5?x>>_8+tu'
    'M|CF<|kG?f=~7?Ey5p1Qz$`Yp5M8)-S5iHpnGDxPjquDRC|mVK`k3yPdgiXFj@nhdkcHgs9(wB6Dc&l}xi}-KuzIk**V0YZtb%Pc'
    's)IFf><sC@WGCk^*Ejk>A)wqsoUHR0N{})i&Bw1DBkRWMs<U8yWW27cYmtH5Z=RwxcqNh|~ypgfhgIt`vuvZ`aoXzl@HMc-Jr^>~'
    '7f^g_|hI%3(o(O=o2L+(3|SqEHs}oLoI*@(~aR{Ui}!0S5?MwmEFxUKL`OX=32=DuJ75H41C%i{3`zt*k*53Zn|G>#$VhaP$V5&|'
    ';&xPrKp$Qr;TYCp{_3hG0mdrrGFviMF)-6SHzz<--+Zuj-`;0Hy~5%K<K%ic%p2o4y7#!B_#w8+x@-i#IBYsL2~@in;=|pI|Mxfx'
    'IW<?p)drh_jjffSEL0lHN+GRjH4xss%F@iG{>CfFABwYGw7lKwT=}G2fCl2qOts_J*{VbGmHGSjxbgt~;<7H-X%6zKm3*f+ffxO`'
    'OG#ZM)P`3rAXu1v6$rP2?ex*{rOP?#zOxHd`*``LSXPvK4aHTmsTOg}G<tg)v^o7g=g7qmZt1ppfGkngLwjrB`{R6nO;Kyn86<05'
    'HMI{qktq@9APU!3M`P0pN`Ulc8x&wqm4ZW9kL=$&;Jwujl+@7A^AyCs&Ywa>bBi03>!(iCJvP7Tc3$g6)ozxAkKdzc~3AO6=EGyg'
    'PvD82Qk#`Vmx~D@R0ZA7+yVw1Oc^!CTPzxLWE$e|oe@(Hfcg2|KnT6ry8-y=1$bHsv{&4Z#PyyY(T_k*ZWsnp?DQ!(-95su;KaDj'
    '0qYyHtHixk;Sf0-c->Qz>r;^O2y}`EDxASm?c2?yG4gQG8{GdVu}F{fg;JkHgn4mTncI$aVnaC%uCpj<2%k{WrWJbP-OLPBp4O_K'
    'Hv4T&#ey=NwTs&aENpo(RWSa1cM2!h)K<xPYzqN2orUB%dBMq;Il7(5(X+PQ#5Q`1exh<tP1Utzg0qgNFH5+VIUPT}3P_0L_)&Pf'
    '=4q1tcy^RFjE0$BI%+%|i0dV6$5lkL1XYvlxSK6p-HHVs0tEeg>m&Vb+!45`;6lG{1rhGEda1klrzFJzY_T7h@%zqL?hzwxK?W1i'
    'm`gzb(lz+FT~4q#=T(N*3N+7-U;RgX~H}gF8B8%1jx1F)8Lw_uO!un*dbHzHUD88x}pcD4f8dA=?PVs2;Ss>?yO>v34GrOaYx;xW'
    '75H7@MqI2TwGEVrJ}mRD3-i*@3+)dihl?AiipErnMd>ksoagcPmw={4dSUaHI>0Vz$Z=#}hQ+f<7pU&xOGhip&O2cD7Py(B6vt^y'
    'nF<?lSV`q53Q2nr9bpUvjS0po$i@a15UGg3|g}R7EBU3H6~~<;(L+-t4ku2l8BLVA>W4_QjnxJ7BZFJ@~gkGNmp~+~rJo;*46ooa'
    '&)g1Vzj}<5DR0TTDL3Mjk{{T5mN`TVg>D(W=SWMP+2!&d$qjCh~Jm^aVlzhf|=K^w8CX6q4v*R@Dl{!@h?VP*Fe6>;w-Jfh7?fp}'
    'tVGxp@Yc0R~S>fYy0&Kd6LT$NG?gNd=~{3AiVKKV%w8KiU|J15Y$fo7Zl;7Z}-G8EK1oR)|xuoZcCUysCU`cMB=^ojzNXu0o^e*n'
    'OZ0dqJok!y^^G9V#^4rBxDcF5Beb_r(X=*R{xZ;Te(05|9AE)1Eg1;X|hjsDcvH78iR&tyUXkH%?i#Bvp=#ZTG@ftEFQv*{dB@m~'
    'mkLkDcH`GZ4E}7@1XEq;1+|+_KW5An&k6#wavP67G-&lxF%66mKa_3noILAvcl|#)~4tItDy_M-T%j+ZnAzzTqAAfuGE?m(2G=HN'
    'gCp?t1}xS9_8M3U(ICXYKItP^A&*-3!^)^D{CJhof988B0Ty{KPSodoGqQ_N*^G2(Y^JVDN&*=!C8Pt*hQ#EacFqCl#%F2wS}aB1'
    'iE~E7Qy8s2ov6jYkghTx`GK*Rg?WBipJahb@wvhc4>EH#+RQ!+BTKUE^8;;Y6cH(E)Xm8nWs1q7^9~b5x1-hsW)KNUfqNVLJ%C=J'
    ';gdtV>X@sdJxt_Nvb!6)AjF5(&tCiR^r_7ehx{WoMHk%{QQ{_QBmzkj=VMt3>!xUmW~fJ+@D$J-!T?8irVKs#Cs3V$<9Rd%H6q#2'
    '(g*1#_)lzYkh{yt_MB0L#vfV&v?@z&e_Lpm15(H{O@iNH;7C{{VP71S;Mcc%{dY&LU%=*PMkkgUo7eeU<PtH@#*^0s_qkOpg$L3v'
    'nN!e89b;r^w$kVnk|FNtINWlzjuz9mLyrMVSt=`ST1yC>+uQRROn+Gw3%4A;8SbT2bGO9W->{(a)3OJcQ!|_sa5(3XYHZX%R*bNg'
    'wss{-FveYA!-i4NZ|FSc}Q^<#k?~IpP_}wga9Xv!1LZjdgM9d9kxa{wdwaHt%te=8~E)Efh#)1pw=N;k4xD4f69yw<O{i9-tBshv'
    'd~L0P||g(YVk=H$4eY&0@Q?m*00>v3u#?SYuc2t`}H)pC2vuzbf6BRUZ==NzI#^TXczsp@-f|37argy7MaL&PWpTN#lS0_CKCFa}'
    'rHaY8wts5@*jf{~HqbjVBw=UT8XZK6lza`n7$OS^eGqT2CGz=trcA$LtKM#1B|bQhrfS0ad=`W`~I4@_ns<^4dzNFzdwbePhLkmn'
    'As^$8ndYkTi$=RpYrcP3O<=JKuESo3npW(tF3JX3jfKr=C3fP#<)795S*A(d%}vz`@1noIst2SJ~)VD$R7;j*q!;wUecczEv}atW'
    ')fR;+%(eRbI|ktmv8hpJWXU;r0M$^~B6^>BgM;Z{YHhScBvI)rbEO`WpJ?0HEj9k)40YWD<P{@~RKpzX2*Zj~$y6Tf_S5Ft##?OM'
    'C1}8DV5k1r^W-D}4#YhifHTmh#;v*+-`vzd6~Iebjui$*%v4vrT90H@^c=>YH=to6oV!RtBQ+%ce6INOcr+7E9fCHC_HUJFH86SL'
    'kjGSDLU;N`d|na9iLPn!6aEf(_IDbfDM3$ct-Fa^f~|=q5LCagOwB>|{kRR#%ny9X5e{IWV-S&AHe);c_~fY&)}t@0hKE-4KdCjA'
    'HZNo$|^|tmC62^W~i!{<HYVR?)__XO(mcwZ&m0uCIZ4GSUYL?!Z*4@WwEMcIm4uM@cw(g4G0xEzVg;bxmn)=fUpj@+aWZRqt<cnE'
    'ci=7kQ9}PN8IP$8}{<4f1ot2!_crF{`5`b_j&IqUf;f1b!8FNX?rej;obewKg{uNmqhxr&v*q{s22gA)5$J56PkN1oQ@REX8g(OB'
    'Pyp7Ht01fPi>+xfdA>Ry;j$RKsy-BUJQLRq6S2?8|SP&NSM;gF%twM)VTO1CDaVffixx$eR_etuL>r7c%=t**elH{hWer2jDcIxL'
    '^mo1VZ`;v3Yyi(;h9gpcSvpQpE=5L=>W!7csN_V{`LwV$+r<!e_e5_uA7YM~p<GDw3y_V=3wr9Q=0FcC_36*=T<lDVwu62XHRPo*'
    '#gO+t4l3k=w4gXkY%*PXc^t*J9?eh^w^IrZQ4dVqn?vcv8YENF2vH(KZA6=G4A(O+K1!8wBw!`_NZSjlcaig|q)z11Ya8?=q18^3'
    'ACezll#9CMOw0^#}gE>7c@B4NcOv1A5B_N_=-0lBPd>fKoS2)Kqs`NN?;j#TRRPN&nRGKvx9219PRbNx4)4ow85=@xy%w4;?nw|C'
    'x=kR!8P+<B8wcG56!M-yVbVmF+GvJl--J(a=yH96}5>GS<+5;CpQp8+3evdONpa&2IK38?k(4aq~exG8Ae`X&ow=$&_^T#M98hnY'
    'XP@KVX7RNNb$8vv_sqeycZhy6NPXP3P47+C}jI+*M*LqP4Hw*P&Q;8rdP*KWh#zVKumm;&VYEj(z$cKK|qrPOnts)%znDxR9&prc'
    'ax8?YyIP(nDyH1<prpCmDf=LwY(vK<u!!R-G@>aPp~9T95Pcg93d4X88b4GUx9Wm{T3}s+|CDWh3GcP<khV-'
    'cQ{isQ})Kuxy;)@>yF25uug^ULjS5t2EVGd@-|vQm4g+l@~Vbi))!cO};h~hGU#?(P{pxgvFiP&DP$rof>V90sR;lr-X=$0DsTz-'
    'Vpx;P$;%Vwh^YmH6o>)sOFgG=n|k5d;olV>G|fwjdU(OD&%>hr}mN?BZm04{Xi}BsiQyuNFl~W)E%!cyl{Y2q#SEnKkWP`OmGszi'
    'cSixiG&1@R42^{UPk-<>{!$98^1n#+D`go8Mv<c+bCzBhb)M1#9>FM-'
    'Skz18r*e|$x4?X_5XuVNQ6r9Md?{w3OJA*gpSEc^jK4~zVx8Y0?8^S83BnR5l7lMF6AUFvgc!VbLqU>>~F3N$n_0S(I|hu*cXF-y'
    'eRh4<`n)1YGHTvr^}b075jU@PQXl1vHfC1K}ab~i&APYQG$()Y-^*%cH1#?<#`0(Qh~Vw$3}DtDo<4LaX96X9!707TnIH~%XnNlI'
    'F3W!D2&@6+$DPbm;n}6LtHXdAXlVrtK+w7UpCPFD2Bo&41TS*BQqp+s^^tns`=~|fF6ss%yD77c_pIsirh4jVpv-0mcYD`@+44}Y'
    '3X`T-<2N8%$Ba-D$h(i^QGM(oKSiXdINTCCa_54Q*mW|zW8fzveUHOzNB@WI(${EG-kJL)+&vu<=F=$wA}TG`Mhq|Ki5;~W<)JQd'
    'LFZ>F!mj`T(2@KO=sF=X`KYEcyCUGBT9!$9M{XeD)NjxRx%=DS)G=M(HAO>Badyp1#HTnlYQ9rxug#tOxKp(5hs=BbevI~F~hHPh'
    '5;1D<wI7<%bE`-1Ly!b(#Dg^?0l?DPrRWV{%B-FpB{_q$%I9?r<h$`cwXW#6D?*fSd)MdsdPSZSk$IeeCflBuqnU$WS3bdQ_1sUV'
    'XXMNGSr$^QOP7eosbVi4&*kEu{3)-x=)%<)VS#e=>kIh#<qaO<8ze@Y#==!_au^TGmqjKjTQ~3dhx#a(yP1}7IZuLO~R;d=Q<I^{'
    '&ubt_Mm(W(Lmgs4aC~at0hD4+3IDPClBi#dSL11<9!A_F0rR<^}^gdB})d6#(%Ku2w)~q8xTBDc{+Pv<(a$o%&>}P#W@$!1H=`_3'
    'M}5Yra8mZ@$yW?5WMKp*!|6$?J8!(<%-#xnDQ5?9*wZ+gXnNu`SSgA@l;I^o{1w<30#-cvohE&kaWs<*ps&nKyx5!s6f1f|L96`e'
    'i(PHl`gmAAY+V;4C_sZ*@s$jN;OpNt=LQ+ds8Irk@`dryAEmBd#~GRj2Z{)ZaJiVR%W(^q@i=?2+>r2dPklig8q111U8Dw*^uzd`'
    'wHQtMA)5Nl1LrIgGyc1@v0!}m|c#ldyb*nn{BxX+M5nQrvy=Pur{T>E1S0_OG6K{?+3@fADpN~ro_ZT&CQN&-<@&H?{ygW;&cq4g'
    'b?e;<~RZI=fYa8XV0Dbx+xPv-onLgo=J=ji9vB;rTu7>I+!Zg2<8|-5v{5UZnm_MBoyox5%IdsZMeRZluLH-T{L+e3DDQxV*68Zo'
    'fU_NH<ssP4PPvdDuvq^a}g1m6PR-Az1A0(U1&XvQHl%k;Gy27pn?!0+PC6wvHe+rMAlwYF0ENa=oG={t$fktX>jR7xU^S3SC-A~c'
    'NfDIDqFpwXt6I=<5OIa9gkaYoW2>=6NB6Vm11z$!<D<LNjwOkwQjB9|EV{454-NYL#ZH5X@12$;hb9cDs)`|VTB^o&_h*&w%)P&n'
    '6-^WTdv!^hfPlXo9UbO=6pv+pOKBH@DmBey_5ao7rzvKrQCWg_Ndm_g0Gs-U&y7-;&AFPpzG%0z0#e5SlElXwTfMPV?ynJj$un|S'
    '&h%4d{@oHx>3qP0X*=-*S?SV!0G-!fbDtk0ISazK|c~WN4;Z+CX8f5w<FF9e-#Rgs0c9%Yek@)>WM=L-f{#7-+_VH?+w^!J*s7eQ'
    '+7*o+k_sHn~UhTD#QtqCGi1jq(I(gDDSW#_1)MD?vmaF=)o#dCxwBQgY~#5^L9)-h_9npquj=@C{9#$2Y?=2K_DEzH#gsGN3rlgy'
    'pAADe)rw8zt0^x`}@rOkDzb0?M|!c3YiHAO>zp1oD3l#oZoqmXncfYy0GX>?D_2XRa<E5QVV-W>ENopvvUskf9}4)k$E_72P`0BM'
    'g4fG4$tj3Y893y6^er2TsUpEDEAM|&0n5w^8CxT3rJH?wVRIMTGW9P2Ts5YZo70U>t>+uZPtzNmqWP6VWCx!?2EjJL<3azOW2d8J'
    'FQR!vmd*M-tsvP;yK=dNfCh}L9-EYD+E}^&TYsRU!uKOevOUE9qLeqXcP+9(NRaz=&b{ghrh$Q#LZZ4y}fbiffItTA7dv=QIivS<'
    'C&y;9NuO(OhPXu@ORX>fZPHff0$Jk|6A4@{^xH42t^i`UYIRV-OL$=g46oXUwxbV$L8N{ou}i?-<&zwc<$R=@J{`rhr;^yqb5>u2'
    '1;)@rNP5<kxuu~w%o&Ja2tR0a4^9-kMy!jBLz|FV>u@rru0Xhur#V$=(JKRZWY%kN!?;=#M_MK9gOB(X}hs$ed6gx;Vyfrpmhi6D'
    '-*}tIj87nu5wDrif}mWDIEfK%aqM^``wYVvFQ>=f?r#@H3PyX0?1=laO=0L-`*iCp+g7#X(lR&Y;kRK6X)IOCowjFit;;%Bvfn2T'
    'Ta~}I2MNvMFleP(DI-'
    'GV{=Z#%Q^9U=0u1rTI0990er|q6rX$08aaofd2&YKKp9Y;?cK?^`t)*F>(!)z?i(w0|7*@Ro6aO>255CE_-*?dFHwMy(BiYR-AxZ'
    'Kxq@AQdWH(-o4zOy?vT2ON?qKQEmt->2a%SUxK_bJci$}bkK;$`7=;#=)`RaKiI~|M_brr8xOpdDIV!au9fvBL*l%$6Lm8yKpDn+'
    '|Xy3uQc^8JU`E1jfOg<PR>PfKfb=(5*jpy?Q6?u_TL_U2^zmXh_EvFyUel<g<lM2b&lsWCktt0W;YBNG1Md}&**L`mv3g)3ApRw>'
    '98K9Xv63*zsc&IwC`$iX~OA`B}<W*RtOi67)<Q@xY91noZp*wY+b+xaXPd1%qPJ*sdCCB0m)JqCm>fGM2f3nHu8KXPZ#QyQ&H>6D'
    'f2qi`(msUMORR)}o7W$5Mru*Vp<N4q0JKg-{sWbZ;zq#;L^SM+1wb7}IHRuEH{-uMiNjDc~x@-%^^Us!~!&rKp2&8s|zdLv8!l^S'
    '~?mN-^^;wz}I0@ezKX>Xx9OR(`f9W9C3)fJQqsBP(AJ8YH3^CIZJ-|VS1^-3U@Alzx;DE9>(tgd>*ZT5g?Z8nOI@kE+zO&8ePhn2'
    '&Avj_|3RG2;VLEsyjaa=8HNmOjtV+OsFu>r#kU&-Hm)TzqzQ<I@GMLtb;$}haSy~3t^(y%$)g~66Ti7RhOIulvR3iRa<xBazwv2>'
    'T{=Q{IRwD6hon3?8txDyheo;n8nypR}%GgTOe*C1$ib-}T-bJ~ft({`JLG1Q&QaRMb@ctZupYJHXZmGJuvOw|b$O38LcC;qBpvs`'
    'Mf%thv4LMn2B+G*__WXXw6_xSqAByIqVNT6$jSVCYu2OV~wXLdxE^uxU#l768n!5rVR#6IGtyo-CH%wB<t1g!-GTXkU4q3Y+2Qg1'
    'o)%C^4HAQu=9Z)2pn4e4Q>Mjykc!7F*0L!Sj?qIj&r=p&4Lb9ZMONcV~#$4Hyxzw7-Jgs0lP3F|Z`tn+=X8O#c1qCeT!H<oz(LY<'
    'fH)m0fYDi8g>m*qG1G;;vYmpT^P(T6+GZ57ZitVp_T%&h39u;D_Ve{e&31ly+X{I!fR^=*EdzmfPh(q-b+Z(i<s!(zNiDy#n-U-K'
    'qt${FN6}D<>ajL?tFO5akD{|kXe&UOQJtOFwkQH`0bbQ7uAB-2s^mZMc>Z-3vW0rriCq#2H>C1&V$6IC-0V3BogQRFyHJxJq2FjC'
    'j>_p(R%cY*q%_~$z(8O>`{-P4@?nlDTr{bRX_t?3A^vs#YubbY_cKF;;yO5sQet18VDxIogIt{T2R|e_E6SIm&OJZf^eU!RZ1EN('
    'jr1|p9BU@p9l;&?lP2&jcHAfM?BFV@IG=7YYK($f<OOKxUy6J))6Bioa&yJqSvNPtJ{O1ebp0%g=y6NlYbKl~Z`uU5drjy6*4dFN'
    'TO!j!6>fHVK<ont2cfL4$_?_eL?0e_P{^R@JJ@U>w`x+0v*SPPU{U`SyI?;5b>Ey|G&1_+gY*VdVrSSb@hl3?k0IZQ15W)<oau_E'
    'l`{$<P&H)MQY7aNRRJ?mDl4x#BccGk1_6qT_YYHJE$9}nLS|v?oLxZy?1<^}H#4r2H5A)`mZgx6Rr?6zHk|++-{9v)e)k#a;S8bQ'
    '&)KV4YjRNNxvW@c=<uBv_x|!|R7;i1#eX;>kW7|RLo6?QY=YM%kFG~mK#*6Oa>q~&<^({vdSBp*FZ)ot2qwL`RgNOI+KOD&Fc%p)'
    'Db&ntY>eU#Ts#$jEaA>&|mzh13OT5lKlLeG0GfLawthr5QY9?2mW{q=fU(=%YzJOf$Sx2#_JqH5D{8)UW=qDBPsl7L_T!d%7wuGZ'
    ')?0(s<%*V#k*ZWxPDUA%<^<5Jlz0~*cbQ~qvFUWdV%}?qRgoMn6=B)AT+0&dURmbB9H1vQRpD!)8AKjDAj%YS)QwAEALWLwD@V8<'
    'SR8-U1{<7fI_F->^Jv$ueGr{tYL}ge!STD=wUku3=E*7raVIVe8m~lKhz~BM)bd~jbETUXxVd<(wCbmY<k>AjQ9}Xc0V;SDNI^%4'
    'G>wrMC92Rfs#gr{M7f9pN+ulTjL+g{`vuApx*>9UqpJ+N`rl2V+j*S6DXu*cgw#0)kU4Br?KL#e1%=-4iv&Q4i-&}bA`02(ozxj8'
    '^PdA_VP18x)EoU8D8Us<uT02ER9!GjJEiY^;(R(p85OXxL?Vo*yaG>eJDHLt1>*$|<{y*?wcw?wneLn2|@tR}8Y3**zg|FqDagl%'
    'trP)!U0!|21WSfBwx%MSL3O9~DF%}bg(;10ca~2@}`h3&5>{E-Pzs<}Vfn&*n31~`pna{g<3r*qXup&SxbVwx*{6oB}e73*V3G&7'
    'M1MeQ+-*j-_p`RT3$-Z~@??1fn$f0-aENME>c>KKsO()+uaUh-`niQc)ZEA2X`0QjkFv9{56lRIWf16pU`|Pt_3zVOKj*^yLkDuG'
    'V7-OHYn53SF=*o*g$JQ`8FtAejhpcAm!*FeSt6#!b6_;1TY-rft)YrMG-?#rry{x^N2?hNisVLof1?HU2-dI0xXmB-MdeVwQ8XD>'
    '}s@M@ms^ZSx^2Ah5B@UH&k`dygAOHOS{Mo1fDfj6wKmNO4<$m??M?cH`^QZsx_n?3vfBgy+zAoJco#mZZ6uliJSJ-`r(Ad!&cpsw'
    '%9PocNZwRy+{k>Y&Wd2XP=h;AG&N$MTW@u(!`7drcN}K^%wl`Dp#Qx?Tpsb?U?_sHuu1}h6odQ_$VT1}esNp-SI1<P2{S}QIJVGz'
    '7?|9NAn>H)nAHo9EgQ>({CoU1hh9j5t3~{hd!7DPaP$*6x-##M}3AN4dRqa^4s0n{dQqR$oV<M`b99K$8TJ_xG9kvE?wzQFzpSZU'
    'z>7DS*H7s`x4Q3v&-TJf?O9M|qc3J303&-gFIyJM&`_mur>@OFPO$)TjX8h3=7-x$(uj%qsi%?ualBcKC(^i2DVfi4M;e)}Ee){z'
    'L!Mir=pMAC)yz2AMg~|h;<n*L-NG^lEPs^?Z8G=b*>W0UQt^FGhmh04YS-x>e(*Vb%yW5^tk5inuQyjii56?~x0HMioiTDOZN~O@'
    '3Rkm=ZbO?#~Kl<duU;o|D?9|BMdfIM_wxh;iV`MWgm1{*TPKCr6BiZvILw5eh|8~Cl3@)V#i+}2c#lt;-0Gc=OaM^Ax-C8)l^bxh'
    '<aut#^8ddeDmS4`*8q>|Td#GyOAF2bsbgTdd$(f57{F~;VFK)6E(e%hvcI?09etbgC<9`kx#F6pM*?pL-{fGA-$sN-=BY>}Bw}AF'
    'Fm!WsjB4#sd@TID+$B!uy0kxT-@pzzeMm8TkGj9cpfASLed54}`Y>v%9Wb^KhMXMbV_FDFx$7|Wv@1Wd5C^BWgHTxc_OyX6oSo5D'
    '`>B6a(CRE3*I9O=$fLCnsK6seSH+!(`9Hh{)SpA`8ASQfap_p)2hJq;WK}7Lm0}`vu*}o#@+XcSK4Oj;ja#vMuRZ@+Li@pAvk*6+'
    'c>Et@C*c8(gzf4M7b}r4@c;ch-?xc)by=+5G5y2j@&McM|7R*#sj>oo;>vT#q1~a%r$SLOZDByM@61q4r^vBm@U`NJJFo=XR;pB<'
    'GdAMv#7(VVWTK(<qzD2>=j{1%6S(19+whf<sh^FNndXA~Jakx17&?ar~L6zR@{+zzZW>lF(`!^SY3ocCDNuC$WEm#gf-#aaC6zRR'
    'WUvd2)<riBQ_9!ugQW4*EU2%9g>beU0ve%{JxdiGZ9)|Emullf!nPbhxG1g;-Y*e3p7P8elPf)VJJy+WGNJRy$Y%bt%3Zk3ZcC5;'
    'RW>J=3dB?k*jx-dzmIpuo9O(h_s|x*)GY@0)Uf;&Rd`_h@oT7^l^pTthIo?;9?E9|#!S|1-%PkoxEbId{#?NW~LM{MqZYL7r*(V2'
    'bpB&5r^HeJsjQy_SH$j;7x<%*_b5oFj7}m9H{Rd$gsT8L=Ez7r*kA`0p+JV3{@u;A>WA@*2(cL`Jc<$uB3r%02J>7Vr>BpFm|AEo'
    'WuBDagNM`4c)<iM#qmWsg9>VEN{&%gnI%Hmn52+^|IuhOhs2*?nqWN5tZP&&xh)GRqG3LIh_>$>nb(<{%cC`KS!%siW{r!g@e^PH'
    'B2;~^a!~t=%H~aA8a{IN-<w2P-yrg*2aV^wgS!z}0<j~}7i`dZW&8ygWdJPO@Yn{?|`fEi!jR)R6boj*aL;K!6apb_hci(AxZ(rk'
    '~_YUoQukqc+rpCi3j{M~0kr?&-G_#dU8XB7{?khz=np{$56>Lq>>|>&Bw<O_2y6fn)$YpEQGuqCO?}T#g#T9$d^4cximU>e^5Uvb'
    'H+PB%I*`|d#tCx@b(9%<C8MWv~3ZCD0jSCeYI+}XPmzCEo_)CgBcJ#8`hE_GZ-I>O7;wRtN^!uh0-|%1Oo6a`smwx)5zwqtprhT?'
    'v_Wh>Omb(A8>G!r@PTB5hw#9$;!Z(el(~pqjr!e4&g|>Ue&T&9epa){UMfM-?DO9@c(2;uA$kXumblNr5&Ww*YWKo(;d^pb!9H~0'
    'bZJH&vWI=0J-YZCUnk4Tj$|vN~$;%GBf57IofJ1D$YxDXVI3#G<{`h+IT$4TMw^=DaC=~!yP)PSrcjhrD>LwqTuEPzL%|UkSHoHo'
    'y=H8zm^Z}+10d<0>6EzPp^3*pVwQ^=Apt<SWS6+HUgKmJ-QGUGGF$C$z+1{KT;5rs_sC&%zQkJz#uY!TIU5sCVQDg+{;EO;6rZQA'
    'c8q^7lVG`_~&+gbjX6}^dxk-@vMJ4urMRo%5x*37|c&U$1g2CAVYcsjNXr9H@^~Kv{b-`ib`p?g#)K!5lT)(AT;NL9X;koU9SFX@'
    'ZfkGC7GOd5oj>&|}AYP(UnDQz8ZXvaSY$4BYv_DjjGB_s-5A07=G@-O>obm98)OPa*<<g~oTV4#UdYO5<{e$AU#YKewTpvokZ$7y'
    'R5G_c6I_M^XRoJE{kc0G^iMH?R_wkozUh&J3Df5c}AG<y$K`L`SJRwQ?>Gj2K1R*V}=CW+IbP3o}xhB6DnZV*-18t`H)XX)+<-{i'
    'iiRAQ94i(Aift>eSOuQ-$uYq=IW+{DQjBcqN^pd@urR#aJwEE3aKVB}FnS`p;a-T#UEM&tw+PpGW?1Q%PMw=9ME@$s#8xOBg9x^<'
    ';bZJ-f#kD8#q6hcy|N49eS}Yfh?G22a_Pz#swG~R2JM3@T8GItS(;T-;+2#Z$M~>$EmIwA)a!5ea1*trn#q)tv2F2V$hjLGq>E(~'
    '`EWNEajGWiT=VzBZ-y9^e%4;j-#mDgq`Z4`X<s$uqY}z2EmKt_mi3M09Ofi4IzA_%>fx5lOL)x>W(QG*g0rP#}z}mR>%=J`e`%Aa'
    'HJ}IfCc-fsk5RN<_q3Aqa^Tj6i?i2Bo)?7!w45G5VfqT@fO5%xXi;Z0-A>#Dr&^(+R{vB(})(K(Kww2@CaiPgV2TI8(Fd)FkyCm?'
    'pG<qM}V@l$*-UjAxb`<8&xnF&RwrF<zNE=dxBp~wU&~Ov;dG#5<DZ{rgUNdRaH%r{{HjwbFE@=fTNF(GZ80tfKExPdF=ot~F1vj='
    ';B9h^=x0rXd+d5q&?dmP5%bL}-$KWpA>uB=n`|1&5A{ES3)cPte=J{C_MfU2HQhIcc-^k*i9xy_MQcTS#b-<(-EYCd0aZXZm3Ywd'
    '9WiI>8+4a?#^6E1Zl=?XN(T~nGljhORHW1k1lN+t8o3}wpixn{V8mu|nI3!tR5c$#K{iQfmez7a|2PR&vNIa0TiH@y}2me8u(;)}'
    'Mnd}vLDz9_w*s-H$K1<i;=UH5RPDQVj7Xd~3phe7e>4(Y}d+c@O%-<;9d16aVPPL8@5sl(C&Ah}8U3zY@HyQJWco|->Jk*ce?A&V'
    'jvW-cH(dX<*w!3sap$idOZ+UIh(s(ctYI8FjPtgCRX>H4n?$IHYEA}Flo-5sHEw;bP#nU8*4A$5H#M0~q7as6eqWhkmKe{LT>3$m'
    '#WqK@3ALj!9OlOC^BF1~RYSy0QO6_-ZcKqaubAve@61mdN)$-s_&US~L6b$r0Jh*z%c11i`z#=l#YD+Udm`)>*knlXRhtcnSVi55'
    'I^Gy91vTEYk?!WIN;~AjT)aMyw=&FoA%YECO0rsHrG%>%{d?dTCo;p2TFrl)xcE>uq{M{!xvln(X3yqHMsjvBJG|3vA@422O3k_`'
    'Y_=+3?Lf|-@Pdh-`A8y&6@TYH!X>xt}27HpvwmJ!uz%{gy)x*aN9{~S{eE{wkKT{v>f7>SF^DIs^>Q*n!GiztF?qzu}_)~Xxsh=I'
    'mH;_igD?sE~D0Yu;-WtHB=d5Ek;<XTl&)?a&IBjl=%}i;n1tzIbuq~4V3CbiA8M)2TN5#PvreQ329rJgJ^c3~7IL^|@6MJWJm!V-'
    'e(gG!&YfBO`gOtYy*?+eG=UbO{;P0!0S2#8Nhb=gGudXohFOoi<AH&kJF|7{Sij|FXVm@JUT*0KLv)DTX=Ixi4X({$)IEKvoN_?O'
    'oqu7rM+7^EZ?4gv1R^mg<@lcw2Co4`q0(!_+7X2ci87CiY4oz?L;n4J(!6Ui$YIC?l;=QSBQd)QhBs&s_a7qG?U9G1A%A~HP=&$&'
    '7H<tUUy?PD&lPwp~!p5RJ_*zCRy2<Mt*zD|tt3t($5975#F&lo>rUTO~pbkJg*63H;xf5$c*q@y(6r5-1^4i`ZuwH_jSwv8}G#0Z'
    'w<~-E$X9ye`^AIRe2`CEZz(#rtnYZ)bp1;uawJpadW<$ZdGtdjTa$gtU+#mcRz?QGgpcqz*J~ks}7J23B`f|5fv(1(<xMR;8>ao6'
    'j&mPY{!lBE^11g&zk60u0>(Y>Ce!0yDH!M`QuL08bbOI)V=K%iEVw=0iHrD#mWxHtmlX4p%)o{w`4aj^I=lX?e1W<|h*u0guSSs8'
    'AH1?}QLLDeJ%>_MS>{b0rQk@(pHc|L+;6`wXSa^OjFY$a~pQ=iQe?g(?HR7IJ`Q>F>{JbJ)o$~{3gzZbzk6^CxmNv4@dKjlYtvzR'
    'C?~=Wh{S_Oq7L#pFo_}$?$g7Or6~e?0V8pn#7F&=E(WRTdZvMAZIa@r%{v}9;jCX8|Q*(q|yt(zo`{lNa@{`bgH~dNf-DL6HJ|>!'
    '47}w<0A~VhN9MI9Xo9A5hJB6ai#1k+&&GzadoLQe%pHrXE)FuMy^QaIH$2zbEFI8q$Kic%vWBUw^%N4iXE9co}PxHefSDRikn`vr'
    'xV%xF5Mk@5}n$D{8pKtM<nnWn;lJ}7B_LPrB^@%2Z-Nzr+=hXLwYUdpX0Z^<1*cqokT6&iAv~vDRuHr+rKSf)J#O<&2DC?iob;|u'
    'CC`Zh`F6SRZ_F-iP8q`Wwn9s7-Qkqwv74l7c)zGAsyw?!|Y@>ju2?*FgpK~n_ul}`Cp@$k9-`)R{rbGKqoP6)Seea%pZ~wmI2bvo'
    '99Y1vVixXcQI{5C%ru{J$YEeM#L?X(mnMr^_lDSL^mWr#HVSED$MCHAm5g`2g?ln&D83dt&NP!6x*=&7TTzzZ<*c}gqst2Nkq*#n'
    '2*I9pY`Vlc#Dh%v(dYaW?Bp$Bg_(Vp`77ibu+OIc@{Q#>2WsjU2VtqQMH$ejMC)RuZ`KxbLp5z?oe7$Ln`RctnYwq&q-9fnuJQk@'
    '@`E){<kO-oPWiQI4lX_f?HmXUP8_N;_?_G_w&=5p<qb^Fh;nJq(%Pzm9glcuqVT$Qb2>3;M|G#B{i%Gw*TLjqXJf(VvwI7ib^c`u'
    '7%`?3tm*vvhZz`gR`78G0j$74Sf$1T9-rG0O9H6Xo9*TtN9{z4YGyL5`+{bX6xRoP~Cm+Z;q9~+f5Af@c(+%)}VDLFLhL!prt}nk'
    '*dl(yEDh$?Pe|_Lx63)PWqnz(0%qh<D2kG|PIwVHw_6`sT^v@Ri$Ibmt5)9RS<nVY!wl-H_)MQ?dX1csGZ>!thZbJj|tLT%>m0Nq'
    't^Y@PKX=tbe;86+zS69mmc9`^(x@JnRuPMf_kB*sNK!>ZOwR3t4xC|1`s+mqcv*lMBUn&lde*lmN6pj)4>(6x`+T;DL{r`{b!kf4'
    'I)qMeA$aMhui}R1_GoWCC(v`+*OR(5Eh{t6ELV32^0uumQXIqfqdk92u^?i=+0d6O>I(T=m?Fs%7W(D8T1xpJH76s@d{F*(fezM4'
    '~N>edc=_Y0q%*rx0Qtx#f4Cc7a^^5re7GK8*UcmCDl+Q*3P`d*TWQ!M-9JLor{X~MYgz)v&C9+B=uaX`3ZwI|S&%EHu$uie3$y{<'
    'Db~5R?FlD34X#?0Ka4?-egaIHtn0{y;Nz`XdRS^-#NBSEVR>ZJ?vb{f4b>i)f?avyPMw^m_<HO-h&fBM5r0#V;m*{@xqzUViS)zb'
    'jWc_GpaF7KZdV6C_&*W=r&4K&^>!f>%U7u~9#}`q6uGjx~b7)4YZ)Vg0W@p4y?C+}6+scWowA}gF;uwouaski|zfst(Cw2+6q%fN'
    '<5CB8vkW*J{IPcfcP+q&EhH?An%Q@f=7~xCt$_!u~(lPyyQN)(<Q>=3PlD#jKVM|?C+>B5nrEasm7dy5%V#eo6&bAwhK$7dJPg3E'
    '_D1vhcHHM+owQ4iMo^>gx<N~({%n}U1;-bjuajsmyhmqVKfRGZ;Mhr<qlw?dL>#SGpPaT(mUC_ISEJ*Ha18#7j2Ud*+vR+M1Xqls'
    'Br9E`{39cUuP6Ru9fBmaZn9i)o7AJ~6b&|`oeP1O;T#sE(YA7YGAd5qUZY2qgoD1DFugD?s0(!HV+Z$7Bb!H5}<2c*9UO=2{6Nw4'
    '1Z?U0Y>}28Vcv;n&H+#3J-W?7zMbFPC%M6T`h+3+U4eS#aUu8=ZfhdTXZG}20#j#RkPk2o!?7EHRHKj2ztH=>fLcA<<^W%Vzjfcz'
    'YE4?|9h31qc43bw^tSffeT*wUT(8k`1d<qt#*>mFRWG_%!8wY_B4t4fYj_&yvB*w8RWj!JJz%zs)9xjx8|CTOMpW28jHv?g0;%UT'
    '|2Cc$Mwa(GO$>PxigeK)&st<3cbZK}E$#I)_;^UFRl6<@PoNT#eK}9MS%lM|f!Hg>)+(L}JvIRI!)VX<VeZ>V!EvPI{w3vT_&It<'
    '!yC={_orC_TJ|L!pW6p%&B2E+cVC40I?-okeUTq9_o7ci9*^UZ}o3#kcqhSXtc2@!)tAn~bQ?ma8pj0oOE3pxk#TDjE>#urwg3O>'
    'W8}Jarpcm@8qU9Pyo48)}UF_!sGP@VA(3T~o3HM4LN}kokeWI=J>HJX>PdKs>`eQcgfa48EHA39)2PflP>->~bV{RMG;~Fg0(KE8'
    'UDTw3G1WnnS2>2xd2<#VIz*DF-`v4><5b;r1bZ-YyQrJ@UJT_`!&5oXtCGd_N?jiWc2^q;=S!nGOL~`+HPU6vxu}7OXU)I68*3-X'
    's`^TkPiDBzpcNf+5dkhPM;AC7yzy3HboVvJ{c+FjmB0Tm)v8zsJD%LoHhVPu7xPEUc;#rqUc;)~nFFeo@sqW##lze}C{Ev(M+v7%'
    '+E5z2b2%dW$SrbC;XjA~sh~V?LgN6bT8K9vAt3?zjrlA@I%E_)mfnrv-LxCRMgKpPdk)SCrvhbiV#BUjn*6)BFbr|2k0|;jH-qmB'
    '(ZCrb4k#Vlrv%GO*DEIN-{jA=69hAjxJ>DF9@fLW~KMQD@!h1n>`qubS61=<_KUx~SpF&3?=)68)NZJ?4TPx$7|M<g95vB8$PuwG'
    'afUOz}apeA^8GiXvUFlA%9Rg;cv4WPe3yo;L?DtS#u?^2>Jax}wyNY=-)3EhRxXb`fYA|wvVBCCEi^)oT_q}mj4bRt};VO6K&}Sc'
    'iSZ7CyeZL2cDfp%N26Xy!{$U`|xXJ9+0<3+v0HA;C?d(kRxeH%q=Pxv#!>`80xx+VFS&X&_LFc6|@rft44(pso-<JHaxem6E&HCi'
    '$Byv|D_;s<a0Tr&`k}GW3#mP>H?vh*<ajTn2vc3C>8lzX(n)dw0qlMz!N_qCa7A4%i+0Ee&7W3?1ln}KsBAE`BABU)ojz=ngIjbo'
    '6bQZiNt8;o|c-{hfpix@^W{93RfNcyk{cR`6;12{ARu4F;FwZCC|B_V5oL{XiyU6>hx#VP<b9Os(E$XxH7UYBK)53fd`(OgzSF?A'
    'nv^c)mdNn8HhkrpVML_8j%_wX6zN+sz=?vz6*K{1X{O}F#3j0Rs`Lg+GIaj>1ze%AkSDw9O|EVYYbc>{3?I}z1cRtXB=!uHG-'
    'DZ+e6|~5jqejakM`N3hjfC86!3xGCRkVa3q@rIoJJqz-aaAOMYZz+(2LV=&KJ8-a-cHudmhnipB>xj_%I)_d@P%R{YbfQHzy;>eV'
    '`3xZUs!S+mb|WKcP*-!SVj)QR%%1T_g(i7f_p=YCCI5(d_<eou2t0PNauuQL|duKM4XFw9LNHp;>9O;<3#-B8TmKxB3Gy4cl+=bF'
    'mffkrK~_Dhn$a%L*Ff=%*Vp*NPS*MelE>~r8#t|BBTw0A5^E_5HqV0s6Gt{V^&3<MesqDQys5$D3DODwVwT9uFZ;T0X5Qo5x?HeS'
    'Ak!zq>p)0=2GrOD4Bl}5<qXA#CNHKzr2a_r<qD<KeY7NjBoc={xMivm@!~FEAJyLVeGCeJ=?Y;O)|UFB0YNl7PTGWG+lmbN3<?NN'
    'sVXOfBe~h{Kc>S6>V1=^LLA{uPeI*E;rz<pJhAIbi+#h`21JL*i+ShUzoPg0P5x3*wTdocd_FM;if&(P7BKG6RaUKQA<n}wPEZqy'
    '54S9(yv6$YUOu6h-^Xs^p4HyhaY46BXt5oS39G-EZ$1BW?R^O5v2(C!Ip1Xyx9jk&MpV}S8JnH19<GR#Jsq6t_#Z7bkf>2tNP)z7'
    '#5zZ-kSEn)^sonmHT#8m%wkNeoRvDu?{Vgfz9h{8^enc9zOF@m1H}(llNMw0nFSM@+JQSNd2{2&LSQfM7FfFdRXj@t(CsbB;-)nE'
    'aGhSOXSoop*5q3CJxR%)zF~0%jwgZ22J?XLvkmT{G;qG+0xC4nO)j-&6X~&;YD?JP<Xd3WmOM;1qHdU5TnfuYNZ;9@Me8!EIaX4;'
    '{_<BL+HR_ir(wLJzt!>Z4QL_5qv4F4Glg8G0~IPm#!_riIMWU=sw64ve$KebFL5k+w;-}j#r}t0vnDzCx}%Zv<hXT-OOkbz^C7yk'
    'Aj8Be$Wv$H!&=ghK65O6UQqBk+kiKJy3fYgg|q7Aso}DW&O1{-l6ikurILQTUu~Mp=S=m(6~2h0-s%J$n~y-B$lku(nse6fKMX6Z'
    'Ji`F#+t4LmRyN006q??ydhO-)?njduPz#!r)Dmio%Ky)F0Y+dt({oSg$^4nkXp-TO4v!*rM6n_p_{X|jK8!q<;%==V)kFYX*!Q18'
    '(tlmgg#&syC0XlI%hbZoSU7UX6|iK+2XL*O1IXhe_^Khx{dt+&K==c-&Qs1Bl)UP<*IYAOxhL)F4=aJ7&SFVRL;@)EU1}nTBN5(T'
    'I>~LR)t7&eRWWAAmvU@82exQFq<gwV4=VtA50IST|aVJ31a?a56>Gi8LXkycm@p(;e!M}!ExQ{C?LkLt4hT^`AW6#5R-BGJ(6+%$'
    '`f?S?)`t&J1qfH$@4&~P?j3O0S^ph=aV!S%Sq3a?2^q12`}w7F^zG9AoA09Y(rkZ=RFuBV-T5=)DaIsE<$j8k!gglOClZmo5e#rk'
    '09L@@`1bx273fWl-m}x+j)dY|K=<UP{^l@FNuj)Ws#Xl3uj8**TH7?eSS29D8aQ`>&y4nmlv}CZwL|!P!gU&BME-i)9Im#g$I$<;'
    'SXlJ=j|8SA5<zM!=3*iLb`2<PVErPBmisI&sE*r{@68npg8#m+$k2EqsySx!*IZY+F#^QM5A28=IvG0=}^>LYmM?=Dx#5?w>$G2P'
    'SidFZO7B%*cc*#kuGASGIhSxVMk8h*4(czdxfyx{*KxTzF(&u<ZlPKRs5)BjWy{vy_;z$fEjt|?hl!U??$xiCBS9&!Y3&`vZeaxW'
    'cxMsKfnCF>i1+Xg8{qH#Inh_=;{!HZ}P#5S;{`|m*^fs?tbDaVyBK5@2{_cl_Vz(jvNm1hnMg)yw6>4WzjUFho}9%f0Q$0A3#3<v'
    'toMp*xGiK+gq?e-6AZX8M$gw_K;&sGw6yzT0&Sr=u@+)-~y8`>q-~-p<?d~>6q0i>u4AM_pJRc=`j5Fcp*zKild$Nyc8a^^s4LV9'
    '%uD2zm}n1ZgcdO-B;XAgm0|c<XDu^xjEb+xtLrOoj12>;wf5(I12Z!8X5pk%!~WL_Ab|QtR%-pY%_Q*s}!DfnsQn3FI(sL=$^2ns'
    '1m%a5=?1%qWtPb*j{l6vI8(0VWDh1zruYAf6dk@eV)zE9(#m`bLF|K@$APf+op2sE8|D^e4v}zBnAHgNFBN+nl^bgx<Z^n`(D*hS'
    'mxKcCcaD3=b`e#{4x6b)|L_6m!3{AFFpw32JOxES2*jq!<dgnN0L^UmYb}vMfD>Ez5ehXWDO(R12{&JuVN<4;j`w)qWB!xuk5HR-'
    'Mnf;DX%;rN}Rw{eHn&8e5EY#;K%AuZ)?=zticzyEknVn?5AEq+6$V^(Kcku=f{dIg}=d7pA%2xDof@GIeFYjSE;K7nEwZYn`^To4'
    'Ma9C6$P-f_2WnjB(-Ti#if{91>I*tCj)9bqXa<rCX8RYd|VRR?n>h!cwD~a9VR0!8&fZEz0D^#*I)Z;g*(}YroQC+9Btw&)3Bl@3'
    '2Rp65dRH%vHMDkLz^xA`pO4dtQ*r^>xDiHbQ<j$x@hX@a+vUHbJ3|qMHO}PuDQRFolOtW?apt%YT}J!sC2S(^0Bc}s6zltXa6bBw'
    'aN+p8xdUVQ^;!1E!wxJP_vCiiEOn0eQfNmACp*_bN%i;tUd9h!FLOpGG4n!oK6EWd#yrWYuf?&f(iM%Kh3KC2reG-_&Txm*qAHF-'
    '+Ycj)zG5om+Z$lIZW(tP4CFRgLxX9h>dk-GdO)Yt%96h6cA1x<=NI=U%9o>{?NX=G2WZNLkKs4yC$%SlR)OB02O<6rzSRDbPI+@n'
    '2Fan^d(v>_=&!to!+nmi#!2_)Ic#VcWBC)sfhIw-7iMBD)&}6^8`m(yI8sfZMxExr|7HjzlPE-oG%Ad<m3E(w~)>)C)^(`nc<8{&'
    'vc%*I{dr3`*8Mm@E+mkvp8A-jid=Wdjrwg*0|-A+qi@09Y*XflsTl`-KE+7jk!*2^ZcBkdLquzrHlPHEzYY`mRH`<2SDKO5O~y6G'
    'YqL}1pwuN6^!ZXV~hUl<o0Lo_g5e!TOI#2!GKM+)^0W|4BpL@v~#uw3F)|L?w=wr$*7^&|3Gm0`lz6$dwdX0pRap|aMV?Y>-ABZJ'
    '3EjSUylR(TFvhDLrZTJ<rR@+(A%n@SE}S&_Ezb0iBcgc)q-b2EpbW7HvUpyRkk4re6>}0P&8Q+uQo4Eq059jFKE8>GPv80nXJynT'
    'wn7FXym5ieZ}~d(-32Ftkt3t$w(0t_4)=nhV@BFI+4;Xl)b-hKJlAe%9&kp0{;8hwRsOc(192tgq#*_E_f5$+1lN*fEA>R3|2H9)'
    'piPLgO@!zm-P_>{U2=%cMEe?ZfUPW_5l>2gF5+xyKNuXY+KgphXyj$@VMjcx5EJq$W&>?s-YfN&A)~vZ}wtgusTnp0Xj)m$k{1}f'
    'dtILbG79uBbG~&L&I<#ANL>&!pqi0@=<&FpMACiU9c+Kk+aXfXY*|S@oKw2I}45;%nA`xof?5HJe;Kja=yU3;NGpZD?L(Y9#46GX'
    '#>?I^Y{DbN(0ljAalh#=(zaXgMV93KZ>%O%%Q+SZZW91?`}2~aG=o%b1j5P((m_bVHW$_%wxx8lR}lbJAknjuGbpdos%Dc_9e?c`'
    'xQh0esu=FPUO{Wcj(lJc6Zo9jkzjwo0?QVFlI0LU2vW(E`p%0q2V7I!G44A{^K)WG@WZae(Ln83*Yh}xLEFP!<DB803l@axGz>)!'
    'y7M_0T3=c$jM2xH7zsp!TJgqUhQYvI`eK9T96?Q7FthMXWr7k*xLIrXaD$D`^VqbJK}0|!s0|hgY2faElSRbG9zbh7nbexq#hKc5'
    'leZS$ebS(m+uR118iwapPieu(V8*hEH&L=U)30X{`1_IS>U4vv+s8c&O=YyC4|$tOlcDH*UP;NNSJb;+6Brz7x`C&KcUMWb)V!^s'
    '<Dnh?C9;vfRQL=a=max`LmpT)(+|nb`4gYP%XY^mm+vv>_O5J@Vmm@4-}T<HkQ{u5a!TVPW)<JO!a$?o_DFQ93%0l-wK;d$tC3ry'
    '(tH$aCGN$Re@}BA_V9fPX(c8bE5a>NjvTsM_M`!WN&KhdG5hhl}5))qaAfB@nz>veAV=IW3F@wr>2aj&#MIp^%a<<0s-x!S6wl@{'
    'DBg=F)R|#f|Ayf9IH-UdlQK#xsGH}Y=O1P8qlO{FSA~gw@ZZqg}e6rbue-{SrtF%aw)P_&YtW|P6ozIi+UG{U&-ERR*;2y`+O?1N'
    ';L+ju4eP#LzCMYtGc*<@tOPEtoqu0ffeu2MEk~rUEylAN!-2Zn&Oheiu!)=;jXJ^uM9$>;+Dc;D()0OF=X+FH{5!~UKvuf6fpzm3'
    'x4c^cKm%`7gu@$Mgi9-_M=Ns8J^<6(BIfaVs#UzOxIQBqR=p7uY6;qm5>Nn=iV3Vt7~YQ8JdB_!Rk;Yye%yb*caG+0Ez)Fux<ccu'
    '06tO19C&KF|f@#o|>e?x~1dZj<n%<^H^$ujX{zkZ_x?TMP%>h^J!aWAHZe=E0m%*foVxiSUr%uOV5j)t~iJ_zEPN!S5Ys7xqymm?'
    'G~s-Jav6s5<pVd+xQblSVate4LT?y`l9Y<6!9w#^nTFL5T=;<X;yr|bSr2w`7Wj>i(S3IQmwrd*{uGZ+q`mjy->)N=SPeEuSz#&0'
    'pmf-E8L#NqkEk3cC+msdaDP=5w{G!usFItX2Km6fWkD#2YH+2`BFDxS%4F~XWbs38n?2nOn!bq6gx`!ZprKg*H-iE`8*YBRY@G9s'
    'sL#+)MqTTm!O1?2)BZYE^n0Zh@#%VBQ_;~0qRbC^>y>fZ13;u$!WeK%#4DYx-`#K@e^~(-sGzDJGnGtlS_-5ITba{sN@tTsa~N_>'
    'HC%ksHL~AnXf3Q321SLZ_-f^PJu-4rNNsvj=kvp9T<$$h{ZB8l~psy9z&)5m*<+lK6~NQZ;pR`>cTN+k*)I^gvvV>#d5o?6c6^|Y'
    '}%<GPGy_Vu+;W__;Exj?2{=_evTmGV|D)o0U;n4D$sdmC%}er3xor+ODroADVAQ>S%;=?Y+S#;Psfa3vU27uzmj%MGRVb8#nD04n'
    '!=%jwwumQb$(!*g(O6sxU{p6n*VE4?!!~3zs>#PY}1*KPB;E8gZ>GVYc_CP91}$1V1WJFHrgNl`eS>5Kq9OVIobz){;r_G8wC&#Z'
    '>1O}k@I6=B7XfbzkzO8?JY9j#Iv?I*;!n>sV%6chHFc~1f_bPc8ST_>Mkl^j4AZB7-H<zu_+z%<h0~f?mIShyaUT9ZaQ3I;3?RUh'
    '`w=TQRWRY0d?c=0YVEa*H!I<V70k94@+HZVn`Od#YfGcxELBot%rYf?u)p|0qwPmUw*B|aqe9F5)wGvR@{aNZNQgIe&DRs)oO7N%'
    '8&!SQ5%PH&9T$?gA_gF<K9~wxMc5-?8<J?6tCKF|2i$kZ^EnaL))l}`CoR7GXHvDy*Ft)ZUOA=`h^<Mo~zd@w1qUGq;x}<0y1Vi+'
    '$FQ<eb$UL$fE@0D>@(8L=kcE?axR#4rpK6B0;S;R{Mg)Vr-cZ-FHp5MC91t+Ai_Gs5{<;UUr`|o0w`~;#;(`^CNFbmpt7CD_D4#x'
    ';r-6k@8mzqv>l)`EPYf?9yK%9`M+Tp72%HkZ6bSLGm>fDpWFKx}x(^tKO{MI}FEQx7mR|z8<w-!kGg7Io!IbHT!Ahs&lSl5_`<bL'
    'a8gnx~0qQJGH5A-|T$!j7*7NlMEc@=J4eau_7zDc?*SGJE1s4dMW8WZK$GILbxh998q!IeNtX~BETWF&75QdmYTqi?N>hYtcvk2u'
    'Q`?7NXy39ba`Pm!u0fej96`A7ILhOi59WgxhxP^r7f-q27tUkpB7MM$G<U)lev%yV+v_?1ejwDMKZCII2=AXkd@{Z%WES_HQ0kYS'
    'Iyq6j-ZIHdZcPcUgM~Gh`Pdo{a|N=$jwZTpD>>sWFsgv07o%PP|V4@c!K9l)RvT!J6eGQe)3LMT6h-8SH08o*T4ECr$8zPO09th='
    '2lmpUi_XR0lLM2gp3qe{Ez+b=fC;->&A26{`6SpI)LPB%Putjrm69Fjo$(>2Gm!1_JJM3ISWWYRQ5BMEHz(y_?36!yL@cSbS5gYO'
    '18F#&ai<#P$zY_DUY-{@zVa+ehi&EF~b;{uM1a7H|~cPODyASV>a@WX6sJbAqorsf$ful9`-r^l<I$hBil>i*IrSXP?VK<@Y(#+r'
    '-7f_onqUCBJXx(8?f$H?()-2Pzg4ZjAzH7KYJ`IKD#4Kx;7cI3QJ>%^;RzzC%K(==H|U!T6|s_yDF^`3$DTyGzuTov+MRG)a*ib$'
    'QJYH1j@rR`Sq3lNEwScHGkN=pHB|h9V=r#MiH&a8?Kdv)r%Z2cveTpb#19*=$`ftY$#?KW93QAJ=sT}ej4N<j`_7e!vuW(|CsCl{'
    '~lw@7obp;o**uE(i;-YzrddLU|RHOuUnFAt8!VnOaL#TL~KxIs{^OGHU|1@{X*dMSG}W6{}Aj=W3St*?U>~Fsu<d{@69DY`2G=fN'
    'i#6pcsyhg(MI7x_LGDA&;A|-X|sSy5{~;;Y#CueYwxN`4Q(xU7V@WozOa)4^AfcXiVFjMKJVA(@h)3NY2msm`7TjpXoG-n3$mKMN'
    'F0#b)826PsybYI_+Vj;4TvcortjL4FDsI6MBbFunSjzFz9}{qkfr6KckE5%#i<9ybUrEUCEMt3%;6crs<8{$>o6;q`{W(hI-b6ZX'
    'lZg@{K3#9>v~jtJx+7V$>5Qa7}v+<QkPd&0P^Z3eV!OOyl^wD2@z+AEnWbF$8~?3#;_)^s=KGcWVb1-kc5Kmq3NO0%*()Hkq=qA-'
    'f_@cK79alzXvjyqeE(Qvxv%>pZfFm*3k}aAxU4CxV6ygpH$ggz-8#}29#sE0SvAhzs39zP}I;iZ}%gA{&YeQRqDPWnnQI1s-A6s6'
    '}f_F{d@1~dQxIVG<s8iNPepdt;^kT6(L16hNXyen(xhBOj~S6xbJpmOlNI+JTRfj%S8RBHDDsOB5;eXHcm1&VNLdI;almd5^6|!$'
    'b&irL;<IYv#&7#4v%h1d2k4M1Um%TT^~(KAf;D>J;2~A9po+qgkj*Rt^nI%4@qim)W0pD?RsQ^s;yG~DR8r|qij`S<|ed!vY2lv<'
    '~!+CWm$%pk@;aVXaka<#9UV|0$Qpsq?iE}OI*qr9afPcp}2CzE}&cg&@#ZZolP{pHY$eoC@@BM#fBchS_z{{7Kj>JnWqqtH2C8$='
    'NuZ{(JP_`zC}%mr+f1^j_x^PlaE8RSE>{FL6|Ksp7!br{2~P^Dq0vICS}vOA`tZ2LeXy^B}E@~C0#zcIMS~RL>MEQ2u4q-*XvTE_'
    '4@6I*n^E?7eQ-vtAZ=ltJOGpYZF;Yn=VW4L-ho}7v}Xl{eAXx<hVtGugybSBkZp|#}+d7Kfb;kF6=fzq~ZAikr3z`JQWtzsNn8oE'
    '=wOB-2=(Pp?;O9XyL=03eALiSx{pH1Crn0RygRAT4W(qIcA-)i*_6<YkDBKjd61BX6tLC=36AZ^r)E!ZBH+oCj%8S+U}IRDiNb!n'
    '=SRUQpxeM{RIa}+mdTmN7Y!k-nI?%L&f_md=RhQhSSD;)~a{TD|<r@NGEbt#SawylwNjROc(bqo&<}K*92PS{%wp&6F6f3SHMf-_'
    '&1^BdMgbK%zvF5bd9|onf(>T<a9~T=yFP<MHk~RCcSV?J>cA9a&1Z%UpT{_^Dm&XAmtpGKh6m10yB>kp_mhHKDSfxJ8Yp%>j~@ZD'
    'uNU#ea8hC0*HKZ;7MTZO_vaqe`1tTSxwS3hjY1d1wwRG4flSLzOmxN%Tj*eSzD#WpeZW$KQIHFefHVT(k+qU4XJpR?*gqrUL^nDE'
    'da{dJsUIfZcMsZ__+tQ2NABXuRat8jylnpLl4Ahnmr01=*zx5*L1ex*MIhZ|Mc^QqeqX!owfg%FUtjOuhwq0Kem{N@r??gH6C;7s'
    '8iMfQyiUnO(r0heO)nV=;+lmAf{G)8X|!t45$tOuyWWe2kpATfWU~M78}KbFS7G23TgAZWEpv$B}cTP=}L%+=>L|_4?D&wJOkXJo'
    'nhK>J58{cNpUW@lmtKT0u%axsD#LDHK5ZC*<>&v59YuULE9@v12Hw|H#kLikh+LU_dpnN-|p2~R_Z$o${;?R+ohhaH>^RqAPF5hi'
    'umaA?inoR3#p(;u0{kRS0$uClHOd6ra-PrMatHK6Y4^QM9A<ULBlzx9*(Ufyp~>b2nJU8Zq#{io~%{~B(GGT5hp{%vC|&eMRH0_f'
    'vz`obPo@79_{3twZYn!OEMlg1wP+-PzO-Z%EpuNH;YqQ?1>VFPQgT?Dww@pRH_n*D&^;(8f^BiFpOIeVhl+`DcZc4GLKu(v?X&4p'
    'Xg~r`|*yR5zf??bKd4#>mk{R@4l5Q;Ff1cOCz(pNAz9Mg;dU|#(Q&K^8Uvt#;No)^0ZudLOQzH(v`tVTOD^m&{N1Oh!G&zhSs)Je'
    't9SSaTLMp_yYBUU>Q`E=4pf116(??YvG}zH^}W<sY9*Zu}`y!6${vA-pq+2B)rElBp*1dH99?uU8$QdBOpD@kb&z8q@DH`yk)fX='
    '~6aG_%V7^JQ%#}XKg{3M}GjNVxA)E$dSkhSbVCqLKv?G=z>IdE?H0`CoM_md6F|I{CE&!Un$>f*RLhAiu>Z(d5DYD0>%B?10a%KT'
    'Q1M?rSc<ENI539s+?G=z#LY3zE+yJcdU-6%fJ9$TzXCubJ@vEYzW6nBL!%b)4>z95WfT`91VbRlkk;p-s%PQe||2l71YzM!&SWPW'
    '}r7aW(V-bWFcoq<Hr2moHx$Ew|S7y3BcfETU&-v7wUj$6rq<<&bx)<H5QKB*~2sWaHH`2=pGI|0#kC^15=LSL)$@4_=gn8oJ+BA`'
    'dT&S<X9ax5SJoQx%foNvEozaJr7itx4&V@ty~4q{hoRkij^alhfSMpU4Q*JF3s5`<@zWU#T4k~kcG7%Vq?f@W@q`8y*X`G;3{c<='
    't7f?;-*#-yg|{)&s>E2$WDX)K{R%SC4(D|9o^$5QP<<epz~^v*+`n6bc5$K?e?D=s3YoSsv-#t1}NcZg5Wt@$X0zjz>LDmg^H}yx'
    'TtO`O_ZoiBAWxW>9e-FfXpJqE5T&hOxfEOiK!?5&E7t{gCetIt@UfQ*D5)azY+3itvJ3&nq<eKxa!m!zw5!gtpH4Fy7bE6$Z{K#`'
    '&DNp>G-@f-8-?-)k)VH0V@xqKwN8HI&0)_(WOtJZ1N%HL`V{RRmd%<{wMA!XVHowF=bHG@}bk6aL6fLRftyQ4|A&@J>z=30+iW?W'
    'G)kN-OQcX^F2(M+3SL6`tT!tN-+_@CF`0mjb4QI&dMO#-z{>QUbQLs=<j}x?C{((CohC-2Cq!m9{5|xC26MvS?z2hgUDGGQ=qbb*'
    'zuskqchWMqp_e-qhU%OKVsws`@ey|QYCoDLiUyt@Q$CXsr?c()(^<WuRqSJ8CyIUnClnpJExqg*=5+_q~`_LgRWIaJ<9W;j3V9xi'
    'D|2Z$Ady8G4Ne~wHofh{f+OOIDT^9k;D6&_Pu-H$WQhidH2BKeMf$Bpy~LLLnq$-qOnrLjgQ1sj6YQ6`4P@1kH-vm%>zQx(R>RQS'
    '=m!lVLm5g)cqlQem%VN26Xmo7L@q3&-{^0vr=z>rAALoOj|ErEIw-~uFlwZa&Ty_%qZI<Rt4`#E_7_u${EgK+o9gb1%!ntHHxzxl'
    'AA;6O(z;2+`ppXz71)+!%O31#}^GZeY_W0<H_5A{PUQPAaPV3dS)Cy`>fw=y{HrvIHBCU-<t-Y!kfU6ytRrgQ@eLxiGQ;_pQfof8'
    '!ga8oo}V;k(ZtGbH&1Sq<XF`!86d2ismtI_6mnh==$mbCs^K_z)D?ICt(YhSPsk{C_>?{#lSIek-<%WOv(>Vfv*r&Bxf#TX4c^B`'
    'D|m}EajkiDyTbJ3<C045*4F2RSa4=A%nt6aA5nEF-?Ng+j!HMlA4-g<xsT7;^S}IM21DnJ~DBVA?F-EP?fE(ZZWHAgySPSzkpd!>'
    'K<wt<3Z=ytrO~}u`NySv}-kk2Stvpa2^EADEqPi7xM=Zw?Q7Z81BlXE5sn);`)m@9Id}3T_sX9EZs?vlnd}>xBtaA7fwUB92LO7Y'
    'y39%&rMCgIqCmxI&;#d_xr9qD6S_T<vipWx}RHrJ&3~a(0y&ve`s$0@^n-7QR8X*O5-`=<Za6>b?JWgiQnn6*@fmW@kuTQ3Y|^Cy'
    '(oZGAL1ut)2ADcHzkyxIB^D$rX&*Vy9FU|>?~D{E3(3)%GDW!>1@k^rPbqOJG!cayZ35>yPh{w4+$gb<XxQ;5mykI`W0Y=(wowxQ'
    ';#Y4MU$5CxpJlc0rTL^QOj*SD#-uJd6VSprH#i!IIypv7~oX*m?9Oo2I#_8)wP_*d~;&SUAdr0>5Q0MmRBo_EA5Nncmw4%rVE0~P'
    'tDhRZZ}`K8lW>h<~<eLUlH74h7>G!eUHnlcSM`pajQ}i?3^xL8Y@5Sve{1RU86A86okR~!A+Xe&a|<rf`hffHm%Bv=a0^}5{AW|y'
    '-u<M6%ZRgpFkV-Oi$&cAz7c^w;E++iO}80*+D9}WtlBPm!%8%LrX6}eP$4Y1#v6NTRVz;@-~Bocp1qJQCh8cFMi8V(yj(ab!-gd='
    'fy=*DeVkA4zYd~O>NANOBldQm|<NKP-wv#I2F6Z_J{|t(D(HX@~R`*$I{X?8t=P$GYiv8qZ8jP6x*L=?;OOxVYqn}ffN0=Hiq)rs'
    'NFC7hp!t?ozDF67ALW;UiZf<qibP$Qi2o^Zi1!;ac+n9v#Y|4>g=eE+#g)u_z?gY=2Xl)`w=+K^o4`}e*gZe@AUH22O$Bpo}|SU?'
    'pb|>%3ZfyB-|LXMYrr!YKcWR-awEKTk(26?L-8*!7tTzqUS3g!F-RIV)rAVrkns?G}vJqO_wh}LzBVWia9kvL-mc>T708zVr9NKc'
    '?mmk?0&iRnk@;^XLZ@X(Wpetw(?65oUX5pmU>!cVE(Fh3fE@%8{h!K2S7+LHssjD*h=EE$-^5V&UIi!BAl3d`+I*k=pgJjOI@K16'
    '0Msq%?NO)JTYaaNMMrk%2VkZM}vodCzcRju}J2{lth>9I*=2UGr}{k(pkQ0wycGHZ5-6{if47~W9E5HUILr*#eP0BWkk9(-#pfp@'
    'b{Uf$Li*aJhVvShJvGtG9rK}4L!66cW$QX`>8#H*_(mGrecH5m4w{&m7M)Y9GLFR4ZkYQTxR-v$Ne66x+atkTHIZ}kALpwTYJg25'
    'M6J~cy_wE@g$lD&DpRSTwhkk8CK~>sVVr8G}d78o==n)#x_P<DDqq(`?ZZ@ep1v+e+#i`0mS=>!s-Dnmu6B71LD+|2CBWam8&WsR'
    '`RGpBR&5F>bb8c(fiu|f(0vAMXP)Q6s%AT?FygRbqA7h(|i@mUk?^%?pcUo1L2#?>C~{RvY;R9AuKobU~cdmut1yFCSlClO-a)Bp'
    '5pjRvyuNld+*vD*L7tH{*`Ri#8|Wi!m`}mHHvXfuq3&PUDhKc+1(YE21pV~5iJm)@sLbQiU3Fg1W3F{@d@xPzQh+mi6TKHK}5{_6'
    'E_n`eCoe2d#$z4x#!-@1WA|ec1KTDSBuEZd+)jDv7c+NO=1N=)W^<<_O|};s3Ms6&!<TgZWbLc(EQM<PIpY)C^TmeQvhGF3DDi?R'
    'sl6i>eq{i3!VZ0u5dB+gGV`}2~xvfA`y-WOw)At?Xbkq1b08Nfy2brID-Nc0R#mlLISs7D(vEt7ECSHT$#@vb=~YK>T%bU0N)%5%'
    'H=zWQ18uVw(8kMCW<C;L~-Mdo0GOsPeyI*sldjPPKBZ&JE=^|)`l;5l;!IYSt21tD{O$YJ`iy>s;T=30kh6+Q$-8w@e2BqFav2z^'
    '>TSjNegMaC5Y`PJ>pVN-3M2U=>qg~xaGRo^Ef@-y_M3dKl?d~@<7NtcTgs&&4=yb^%ca6Uf!{#G_bR8Z-xE0q>`gDUSF-k?=pQw!'
    '3n|;o_0wG8&`D>ZuH@c^_3MM&Sn<YtJl}7cO))I6C$DS#a3J*NCmU$m_UyCNtLFEg^VwT@ZIv50+FRZPFyV6UbfTVnfu$9Vs=(ME'
    'TGn0J)=}21RiN(V9Y(dXAjdq;8fU@3|9IRjCG46Ya=zMCbSl~eW|u=mdQ~k;^EeSHf6E8QaLz;V^g|rbHzC)G}Qt{cY4EcdB}L$j'
    'H_z3-DCUnPoS2VPou@`bDJEU%;0CQ*xSb?Sm2sJ{En8R9*uN**bTC{X-JH~nHzneDUHRMfXba+MCS4Mqu{;(uz7mg%X<=o+5Qcpi'
    'E!+2OVU@$Qw?TO<Xjvb_nE$QOO8Z)JdV0r;65OOE?s42ZT<RGZTJ|Wksc-E4HV=?N7LD(u0bYN>kG@g=IQdhPqBiI3y<{Xl-ywVx'
    'G<~l&HII>uq~g=Ob{${0jpsX^P@P-AJvbYL3b*SA|iG$?D0j_YlMMH_=roDw28PmBDrU8v#*$HErX0wweQix^@Rz&kIEF)VB?gN#'
    'p-Ip+poenx_6!gnDYX59KYu?ab(KeC!Ei)!%{g^RQv>F;b%+NB*=8wF+^NAg0%oCLYx6xMtj>!s6y94!L66aq`P&n2w?+k`Y70mS'
    'ZgX}6qPQY6e(w2*ZMIzdqbmErGrx!++FhHuyjo$A%E3(DRTsyagi)I;UNX#2utie)F+^m;JK_009}Atdyg;Xxo5??V)KR2b-o6b$'
    'P3$oyxe0Rj6o;3<Ak53fsh3{3!eZ{VRI+Odo;ilUyRE7?J>=GTcYWa7Qr~Kay%Eqo1I4FY-BEr`C(NY(M&7N^lXAOrRr;p<7qCv&'
    '9h8mZc@m~TMP20{fUfod32Bc&%q+s3!}hW@%;G5sDivn_?Ydf+U&TlbeyJX*B}8S8Vh+qKb&Oim7#&VUS@e6+=TV&V{ly%OG0T}`'
    'b9~fNfzkd2#)G_@CgWxitL?TWx0&U5$Xf8qRTcaS9zrBq@sRMK{zLkvfR^G;RVhlj?Prj-cLY%XqI2na#Zja{$5dU-ZVs>;=3Sfx'
    'VmBvq`w1LlF@bgKKT8IuRH0fTHpHH&CEW1GM~PHN2HfeXvqGv?=ArqaZRi;Hv-@HxHn<=cG;mhwzb(BUGFcU5J+FO5w!=!jSw*PG'
    '+1KSi5PySE-0x7=Gv*tqRp*cU5TltNG$Bd;km-jk@U>Pa&Ok8X9eH>3S(zNYtb~A_n&v~d))>QEU{RLUtc^>TfV0FuR@)G444DGI'
    '72sOJPi=9Ux$q(-)!yFRbYl^zPFPLkRU_Hax{^?x_wC{M75cdYY(uv!ofQuoH~OtSRJw?t#UnTk<R>)8jS*6f8@4VOQ!W9jX=3|%'
    'PgQY3&hz@i?{IZfN`48wiomK$CJAfkB$*xU_GDJm;^1slT$z*Jt-zw{!E#+)=`CK*|yfdE@a$n+GHznm%(BD$m|0_azc!o$?lA-{'
    'MXx+{g!wW4~g&sxHctgLG6OJeyGnx^ChHxyc?-%3edM#;!)fF&K2<svn=4xm6O}?+OGfbA70z>TH9-X|I;09KmYsJUTZ7=>_3*<U'
    'i)d+PyhYS%HLPIx_+K?EN~WW6CBAY%AFw>$0nat<~VaJes3bgkCvC`teyH6hk%GqSwISDsWBW(kFhg4|4OO1E8@aqI;C>*tPe0xs'
    '>!W*M&g2zZa!jH(A?zQDU*lTp9deX^b4yfij&~0ol&8SFCZ!kv@|3{<nmC~aM3(Bw0sS!AngGg7BHS)^dj|qr0=hX-%0gCHaFWGr'
    'Y6W6qSNQut1D)BR-<gn@_Q@<%Cz>Yo~cU-$5Oa*EOrRFx&r@LmThh1Aj7LtUyCOPQ#EtiJWCiyW@Pb+v~Gqs4xxc4dTuU_!j4x{6'
    '-LTEm`MR<g2;CDODR<uAYO|jZl?vVGC15nI9-`97F`G%tdIvJZHA9?chw#$7(v9N>goUh826kY3C=Vr+IJfxhn|z83`ys}0yVyN?'
    'toYQR8Ipe%f7GV6g97#i)J#q_V{4J^r#)mOl(5A5>(*EnOT>s99*b3<lMlxVi*hR!2F1Wt_5%Jkh;(X>{iK11KLaVdt<f9QTxZ6m'
    'CD`^DwR)xycoGvyLZn_iTd~j`}0@by(S**AMckx`K3um``0^tc;Wx&;cqG?gL_ciY)k!S_pW`hz6MhXQ=XbQhO@&WD|~(b;@Y{{%'
    '-EH!g^<Di$8xBJ%}Tm|2&=oka;i3dDlU=wj+$`+HWah!7uuP#oJ*niyvK(_W|Eg6CfmAuKebK!e&0Z)cXwaU;2*q4#M-(2Paoa0Z'
    '$Ri}|JnYJZ<pRE_wVTIZQs^AXmbR8(Y|ev_1@)Pl$&UBqQF|ebupL<tm;$d+<gMuJ@N|VBj=klHgI#*RxiSr(^g5QuN7^VvSA59Q'
    'o{X}l?g_r6lu96*1Tl!hDo-P^rG`>Db!xS1awILHRxLi<h{OpJtf;RV^{YEc9ejuwTt88*Mji8w!f53XQ>mws`AdkZ9SjZSsL8Er'
    '?b8D!}5-vN@<|`52&0S*i-K5`RJw2qz=)Uw0>C3OE09%8`!m+`(<?MIeJ4xJ2WU`?Pu(}03?O&4RJ=Ch})e($dZXXF+u4cday>FN'
    'o`@4M#a#DyQ^F}ZA8_s4)$7h&)}?#1;m03Hdw-Uf53Uied-G+5UPE%Xkq|T6U9zvZ<_=*k69%F_RDjpLOj8B&8<lR#v}YcL)(XKD'
    'W9ZNTy(UpcNfJC8=DcD*hmsSxt@8r?wQz^3h4N6XTJAS%LlC?7B{_i`ic4lQdfh4sCp(|q56U;c^;E0VW!V<7}<`CV=1&eTKDV6s'
    '}b9?cBh(9!>c6*iG6|MC7?u(8(bw6vV4a{BEcgcZT1aVxC@6k&XWc%-`(~YO2!|V;5CWlQ8^#7u#^bP&Vmq;v)ir~G2yp}t|_bt2'
    '*`N-;RU817(QZMhshU|WHQa*W|3J9)fvY+jh_@0(cu&vI^+fQ#?$Jw_qRFZ5NsSqTjyhwLeI(3wC&)fNrVmp-U86*rH#|0u2c>o@'
    '0s~iOzCV~JIQ8={&a-zo?KtMID=pg8^Md$&;ChXq}sjn>l2SqhdzE~?c|;MFxtU=^wJwn79J+U^Z?s&1~4Vv9L~G__n0yukY#R}i'
    'N;I0a0GD7L_Vj+O!39tYFfIMy3w)V3!CA{7;kXJ<~cst<7U*Os35wATw!hYV3zKmSx5;yLo1JsTc_JK54F21=<sdAx&4omr~gGd)'
    '1Qj;)7TlX4IKbW%1hb%+BVjBiF$|u4iSQ)!9BVA^oG~=OJ%zNS^nC&{g819r#rH&Q!^njFH$4|*WB&BsQrm_;&nRp_UENZonY9@A'
    '+hYu)&0CS&z~_Z9I|NMAY7Ep4DZtPyTU8{jsIFenU=k`av+(%Wq3>mo%@sEF(Y#?29J3rHpb*$ZRTn_xH4W46%(riwS2X6M_&~5^'
    '4CJV#9|jFy#7j<lgR?+<d4JGHUW=>lk!~(8hIvU<XK=5fKnlDQ{#q|CIKnE+1dR|0!g0h9RD>yBq@BP033NHYDAEc+R{=4i2Pg8A'
    'q8m2`iV0sD5Mb!5`iGOg#IS@k5;&k=K*~rXpiTCdOV)teUTOtNshUIFAUj0p(pVg8>hc3Ks6#z!@eqDG&bGZe<DJoB@*K=0K<45C'
    '<PqqhE%X05zjro2wVbL#Rj;<reFziBZuPk)+mWhAQDY?W&s${0E#GJAqpsn@rZ(W`uJu8{s9M3@CVf{6|fF30Cd;{+>l@zngALm8'
    '=(vYF`RoAd|{LQ{I?5VXoXp5g;;ndUSV^vLL*cmg(oC<ga9h=c6pni5(GwwRk$JZe=YzHT0;#sffq26Jg0Mz%dIzs7r;AC0S0)>D'
    'df)@;RNs`1D3!Xiad&-h#zq9Kmj=bJGTjPU@jie=K&1FS84?oV1XP%?<fcu{T|B+Qja-#Unsx)`Oo+Mo-Hs=-LF49r?A$`e-8?+3'
    '(Mwv<EwvpZ+ofs@J4Ow5*n|rSI0~$qT9Gh3TzkA1C#0f<v$)-kWG&3>felRTwR2n7059)7Ss2hFI7C7gnlopwYmMGT^iA3^!gcg='
    'dk&;x1T*Kf$@{|TPGoL`SmZ%i?ETSY{>j#zIGC>YL$yr+c&e$+M_$Dr>BKQ%3a_LUzw|~cm@yf<s|5(*fLx39fpy@h}R}LL2$f0e'
    'vE8^!Z)FJQE<EwjJeVx^~Dt7bQN?gSEeL5=o@@*%TQ{;=W3rLepngoMvvJ>hR#1Fw`g|d?n?QyeK9kr^x@y(t<uyeTqP416XRsKJ'
    '&v0HSh|I6!~D9Y8hb@;i0|!JL7onw8a`li-a4&*jXrhCnc^7A!h3SA{=-S}{YwtzS}-!~0#T<<%nS`@g_@df{L#>JMr=)t5;n>9h'
    '?-!1{x00o@LFkBrZE=;=K3TT^i)N2GpEDdV)ll~7pdH&Aq(`&#MiaQ!|u1zr-A@ue-&YGFeFBu?H_5VdH`S0m`6k_gq>kqg!GLN4'
    'ry`*?rX@$Ky;5CtBsB-Y?&Z})Jn*f_WD$@e@rngLns!Qk{x+%w!zqifTNIbombw=3=vFr0G62a1cvGMC9R(3%QHV}QarzmWg~eyv'
    ';tT|_6+q5cDH#hJlU-uzufAZEzrw<96qb3c)!*E_f$#r4C+|;$Ki7}!K%<_;D1uc8}EFhX!W_-wUcKs<N4Ht8FA((0cCWZ4df<{1'
    'f`7%|3DAp5qY>NCZ1^AAT~F4VQoKIh{#2SNtu`=e<JeBYB9$k0zQ`{vIDYFJ*r7TS3t8bmXEVN{eP|4F)w$O_nPH1(BA3Gy=s$x)'
    'w4?~awXANmW9$rE5`C%n_#;$h8ML7xn4ZJ$9{w;<c>!^RUG(s_14<dL+@pH%#PX==$0OP*S@3)8FOIDeldO;Qdn~c;W93bkb%hhh'
    'WC?x;u86U5nxl>92iN2{J^^=8x1zz^aYq1!eUj=fOqKMk`%K)vOEs{2#K+hy<MqEYHa<^gwB%s@nl&krOD9Y;mH9%Sj#Fz^dn0dQ'
    'i#waK78N?bnEy71acfUr3PYY=QG+Lfxl8b0*m+7t2ec>>Ljkr7v)HlFNnIB<eEgvJI!j59U0<9U<~!&wM9WMq#%FPBqXCUO!HFCI'
    'dXC1%#}2HFM7EcKew$71p@@lT{){Up3ky*SpR@@2HIg^Y9d4`SEMf@05!`^V>rmrv#FMu!|+~Intv+np-^m3{so+RvYN3uiCnNtZ'
    'h=AADK#}_{_ClY6RUQKNtwnBmB|(`J}^fmy%U;Gl7x_)TDm)YB3bldD+hCrWE1)kRwg;Cu?{))5iqzXr_unX*(D($o`lz9Y~3`WD'
    'p3_)S5OG_W)E-ZH#(Y_v*|^-Kqf4);)vHT)mM+=sZWk1tzeR5LvAgUAUkVQjUE-gckNH)$R@?C8gpDkEZQ~8m+KSX#YAtwc}}iZS'
    'JTgx6ecyxL5W2rgZ(ZsPe#aJ)k%)bY*m8k?DE>>MI~aw1u-pXk}Ju&DCdGPGjgSzi(eBxIJG251GL!7qf<6u$yBE@J!=BzSSnm~5'
    'OczE;SS%64{)1m=B8-fuwg+9atb&%${kOz*y!x#m+sU?9@_s~dsqcM>&Zoj%bAhI!zkdaubPfP2|-3B{@R%K%hRrZ{PNbV?I!ao0'
    '-&}2;g*s~C=+T@JrZ=bk89t2ukG*n&-qm_$1E+Uc992OL?2>u)n!!NTEY2If1!=xnT-=?eRri6zfIxzybU7y9{5z9*7U00gq*hv('
    ';KuNyd|xPEtJ`;xEmFr%vrw;`x8YqgTMn^uaZJ>@Z01Y(YS?3(f%R3NhH})AUxY6oG&+h*guea(Ok9jM@sbCrY`B}wmTT|T$cAnV'
    'G92ZzP=L&^4g~>(;JtMx@P8;CZ|DBM(S|6cH#Bu-689wc)6Zq&R)XOA9i};zCj2j4xB$^?mn2S6JJjCy}poMZeZ`PRSbvPX&(9h>'
    'c>uxi1s7H*Jd`Rn+31U&V}-+FqFhwNQ`hf1|hBH5i#x>tw5s~jevRxGZvM36puEYy!0TVv}Kt(fGwU6t^kb;7CDIYFnuD{n3!6dJ'
    '&PV9bor75QDWEITi-dATy}R7k~PHZ?P3K((<mr@>M>B~pPUS=e;9Q7s)%~S{$y~)<N`w*dU#HnoA{Fk=Hk&hmN*UYojFZr6GROOg'
    '>%M=Rx-?8ka+TaWP{k|^sha5Zc}37WpE$<+uz^UkDe_<JI#586V%l`0Q^iB?38l{%t1-zXGp1O0)v+nEg44H@l%Aos<10Gpq#*sW'
    'VSE|x6#!_xB<&URwhQ0;LL_I7qsTu#mDvl*+%HLCG|71D05lORp~14H|G%ZKXcT4J~tu7{=I@i81JrlZ@(>qJ+eORQXWRd!-e(bR'
    'ftRSO9m_`TRtT5ky8)Q0b%B(e2bDh3OHOLuj<r${8g#*h4IFnL_ea56oKIMH0M{JR=<&S{F5US`Ha^<5}FXQTP9`_kw|!IFvkI@j'
    'ejrBM2|Wpt-(5;{#vVnr3_$K%ub$~CW~@}utsF5k(g(s73dzZeyDG*ucXqN<BQa>4FQ*rUvBp4mex@XmY>LJkjJ1nM6-_H)ONY1-'
    ')iK#cK)oipzW3Vbuew$79N{Ub6-AKR4K2F>Z8np+N?FW-AlvZDs0jPyd`goVkqha%se%X7C>imox-vHG`SmDSyU`zwy8Rl#Hd8v8'
    'E*WKyMrH$^Lb&3K=kJ9EU`K%sgH8H>@y)*S`C#ble$l~=fZ}oEiTs<mQvB4nRubkd+>(?petY{)k;CWpzW>t(NiA6qHm1;a9*?Iw'
    'KPOH(G<=1_-fJyI|+#CU1DjKtV61^LLn6$O9?e8Qq4Y<OC%Ri4i{&Gon_)%Yj2rcWsIOfGb<4%RJL1ng_>s`TpUC~N7Afw#Gl0Hf'
    'eO|pI%_I0$$(o*-jm=(z#l-XRn|kKqgw!LXE9*{D;Anvfx77nnLQHC0B&Uw2l~BYYC|an2?p3ahYw5jMjPPi<C|uVfhLgPUWpTkS'
    'Z>0!;?cd4V5-!oAKH0U#w|E~Y5pm~Xd2R53KqqD6hv9@XCMhxKx$td{T@UFA$?=+JZz2CL#bVq_~TxXJuRuK$^v{xZ#kFKHdonZ%'
    '|18nZ_bLhv65+|Z)Z_Vgu{I6NVGUSuRXb3yKo`JU%}`({T=8)nf?xzwBQB}mX>rnZ2V((g71I@iTgK)H{h`1eK$r<t)U=A_oabIz'
    'UHE31{g(xp=io8;ggkACsK*?*t--*nvYAb0#$~9Ja;?iN<meMiLlQICUwFawFQT7Qru0t<4^3gmR`%`=cdJmA+b4rGL{?G&K+XU-'
    'g(MsHeor_wA_&5lb<9`a?}obLM&KQv7v2r)fqNc81jK8q;<=P<pu1Kzg2BvG^cEjH53sd2yD7PhmxG9K#rw<DiTbe{&eZM;z=sFa'
    '78~lUSD{KHCql4UVvWH^1x|5KGq4w*=1?YJms`|Jr^IFhM?3!F`bMwX9uTY<?$GPTly`jKDsJB-JezZ_tB~-ev(=gCfFBeGP}O56'
    's?4`#5M2akb?|D)sYeNeqB~T?3&Om;i4YQ)E^b1bYD0{Y~YoPWqLjFd^S2&12@x4!R#&arb*@d;>cHLFqk-2zRu+6+L7C(XV9uWn'
    '==jJie{u~G$fzPAoq|q<yb5;1N(irFudsVTkS3RIR7#h``&@U{z`dITUX!bz5dUgeZ7PI<(-4kcvqBfZE30W0UB?X<kjH4)H=tkY'
    'k2a(>4DEb`rv8xr2kyP7CE7_xBa8F2jlhorp*qhQ}_DvwY75>lu&fs$dgeIg`0eso%BPAJlF$JIXE?J*0AodjSfal7!ShcqZ}ek+'
    'yme1Z*82Yi#&7aH9^zfbBMjPgFhK!`xqpD*ADG|_!6-{XLJ6eTnjj;)rTlEBXA-{guaVOP~puH{g_9KO2}f41GySTz2SD)bSef-t'
    '1jH-#F#xDr;{lrX#Ay%8zWz9`a&zy$9B-~sbjW1aN~5fcIi9;4m3)EIHL=}Xidz2iU%9hzw$NBLd>HV0-BLR`B=YnwKh7cC8C}<9'
    'JhohYwP052TKxd@}>PYnZdLf(dbnd3jaZlFax%l67%G3wVSMJz&A}p9@{LfOl8Z9cvpz2s#YiD+RMG=o_zz|1Dz$9?X*QCN3!Tg5'
    '}Cr?lRT+{yzx&=HP4!)rRcNJhCI_eGAd5o_c4-X&BPU=SHq*V@iBY5=zrGE%_0PDHyuB{e&Xu-6PwS2F*~Vm>nr!sSC?vEHHWx~L'
    'm$L9t}RMaAap5%vlBOB?aCp@XK&{+sn}1t>DitO@l7OF$8XU}#~IKL#<%oXltJ<sooRxZh1%V5cDK<8R&GZsbj^>97_P{kp@G4+J'
    '>|ijyGc*p)xC?dXRy0GSm7t-&-%K%_^;3Tt8kiT7tC~t2kc0U<Pn=7?TxbZ7~NSLziC#U*Qz7SKNZ0_IJ~CJ&#d^~%H$9Z1w~On*'
    ')Eql%R6^gOtyD*mY7!xhdLRR-3BS#y?q1tl^hQB7eI94$*8;D>{#WJ>&YpZ>!{FrJd*~T*wr1zNeo%p?5hQnj)iTL`hz32!>cAl>'
    'JI?cOiSzGVwsVBVq6XQqDe!9=NyFLl_{GA9MEKeq>sEKi$IpL2l;;W%eRn%KXix)Y1Eb2zQ#l!IksL!er#=S|N7&vWrBrP3JzD0j'
    'P|=Jf5Dz)S!I-cV(!!YeEr^~jWe?Xq|5JgjN$x66Rn9)XA5S=oXIYoFC9pgTFW7;PGJo~T0-GChbfHAIiY|J`r$qJOI%Y#znST^*'
    '%$qe{v?$HFc!J9YzLOq^pK*8!e}bhfnWwjO;4AnZM%7Xl&8&pgBHUy4eC=9a@&ww3^249pt18~1G9|>f%S(<TM%M>{R5q;G(6(cF'
    'dtkjZfI^s>d+|XeD5wivMJBGP$By2aWz-9^Ud7&;p^hJhRt{GA{)Dntc_fj6;)qFF-~Z6rGPeLr*gNWxoqc{w#&5CXGkL?v0et2X'
    '6v(83Ek18k0{LQ(O4o>W0|B)`uc^dF()>L4R-%R{r)$Z!>QQs^4BEiCbmIsnPO7=!t(m1VNhC}T*;6*tcs6b=rmFm9G3~|^(u7r2'
    'k*W|s3w}}(z=~8vtaGJDm(P)jV2EvZOe=lpK}DA9(iMGg7au4#LWt!%3ZHl4okqmGrk@_7H0uSMAo%w&fU#8Hi-^v<}N-yj?@oFk'
    '#>e+Xh?11?V~SCQs|{GOWDrRwAn|}?l}wYOS`76tu6i^Z^4n<HZ$o7O8hTNwX3H#uFQ&6K-g#k6Ig!|dRE7HQxLe*$}{0|J2};dS'
    'k@C<{mIe#H>2y-nYACLYj>`dl83SbkRZoj`ak04Muva%YLum+-u=3rRPA0QjD}%gtsT3vaeNpLzH_>^|3+LGQB<RS(GN!i>Nh)Oe'
    'g3H3Bprm-53rAwuQ8GA2&_N3FPHU1*;80xW=OpQo&BC&XV}}>w}KL5jCEt*Fe8fHkUmt4u6x=|{E!j@%MydfD9eb)o5vG&!2J1*;'
    'bHl9cr;H$x_{#C;#r<uuinQ)KkBU?xf(iC&;WdRBiN&pszZdhp%j8$d;goK)v7I<tGvg{c4w1zx<impqc=oyp7&MyE1z{&K5q*yO'
    'SylrdzX12?H~Nh_Fw&~fgPpAuN!z#Yz=F+MT6cmq3_+_gBr9y-+TW}en@th=?iQEcM?1YGe_MMnH=>BphNd1_M{v9-zE;(5X}C>X'
    '7&bs@Cs#Yu1!unUAhW`*o^e)V}z`;@`)1<$Plb4CMA%|^3K7^jRa!~Z-Jwv$dc^>{;AQ{e^>-k?^uGjXNuNt@@8MDw{NgCG*AH$c'
    'A(pw;K81KHhX9pVxR4<l)}`#0-S7r-)EK5j-i2WGHt{ZPN}b#zqR}H|7f7Jqq4i)v+I>oUw>(DrGHmn|DMudW#{hR?w#eH($2oFi'
    'Z9Pr5WhGX%iopKSHUOh&qjL}ZBMW|k7w*VyvxJylww!McIRlAcoNeck{A*H>3@a_V+D8=?q(xV2b;PLF>};@rVn8^F$Ch#dDGS_X'
    'W|OdgIY$Z%jqY`sIVTtK5U2b!N%~#wSzMzNRphZ(zA;P2nRTCt6R{^_s%2P#Y0x=+&j?KCQS6-x4rsmTQjev?Xy>*{K5Wz{YYeHL'
    'ad5_uu|s$?%UB{*;%m--x)!WGV<*a<(;3FKdIOcdMf1sH??=-5goj;<tb|TWrv~^{JgvOv%a0A6X`%xm)A>`-|y||-q}59Vx=Dqz'
    'hDm^n*_qKvbWq{>FNmMKw`Mk^?GTre+akQFJs=Ez}l08PphMj=(@X#+zjJ(%=Db!I5VnX2?Pv(95G>`w&($PusVl&Kke=Nytgyj+'
    'v}5OO@Jp#a22t6*oV9yeaAEy^IM;f5dB~@E{T*he!T^+iY|N0*X`==ox9rxE59FXLl+)9X`ChAWb4*;`+w=JTKyKmJ~<Nd6Lel=>'
    '(bD_tQOrgO(qeKKYK&qDdD1^V=kXJ$&1kc$wRfH<BkA(^Z+(DgXy}bB#mSSa6dYZ(hv%3FR>oz@yYs=qoudY{huO0Bw|Teu;UMc*'
    '}yH2XVAmm82O?0<fc!`Hs4ZqeQ)=!%D`Z$HZ@bf3#e!IiC#h`+5GvZkJ0pK{Y=%=I(Esai|C)nX9Py6Ni}MWl$f=9C(LKbp7EbPc'
    '=w(5f8F->uWZBq=f3_=2W$&gN*{QPt%Td(nSiCid8|$P(`x5VWt-)vTT5=9(>*q2?WU6g(v7R5;!KI&$Or^DjtMhv=k&+A9kJ@J8'
    'NB<E4UOhytbN8I2$=*~Qd+5CUST<GIwae)B}}#n&V-7*;j>RyE;_=;gx`{xsb(Fns#{yrA?eWscjm_S-ydJV-ebQLvj!9k!dc{_y'
    '${Ox(WmSesX^-g@+xGuqr>FzIYz1OOd!NJe;#otbozqZvT+>o5x<NEo$_`t>M8X!?-4_)L1PCI&Ee-n%L=Ckn7h#K9zm|)Q)csyT'
    'nMva8>eopU7v^M)z<yza&K4Pu3e?~Ong-aON5#pvRy*#_GjH)5Oj8Nsk67Q7am*huI~Ol{P5HRMZy$ft}me6A=_9;`!u{IO)Yv#('
    'Q7dmJX$a6c_r*SOj;4B9GlERW&Bt(xC7IXrA7)e#_-euVO&+LL8Ar%Hr+1^=>vNnCQ6Y-+%G^E1MpuSj;Gj<ZJfE1cAZRoc4kHN5'
    '<WEtR$3h*pd7dn5ClaxOMb=h0fHd3K?AVg<Bbw)ER`Sgz$RY@(vrVid-xD)T)A@d^p;n%#rT;m1`m}#>ES)w5}N<cp6*X}L#=ugM'
    'JGF?#_s#pq2>2<)da<5BA+=aoqM`_yY~$3Y1?J;QFoxd$UDT4ql_C6PVgitY8wxwN8FJv(mfHq$Gw2@<*GqGC-;iuYh|Un2|>>%w'
    'D#VgSz<E7VwgB3?vh)N9Gqxcm=Xp~Iz)$SGuLX>WlcleOloi(_iDP#PpeZ%(o)Z5i}Bjll8=$ELSbumAO8@t8R3-hf=Z(W5bU3zx'
    '`DQp=H$7;e&I$#J;$Lb&@Y%(I`Jfnq1b%q&j4j)c7SSQ->u&arxD9(w%F<@Xbu|UE-Gw|pnUBlLC&(!ODICSLlBKyxy+R>$gzX1%'
    'K%RO!Qm`NASh97eDNuJH?JSR;Dtf7kJ&Nlh5$vB8VpQP*nj}qPKr)t=3XRU*}dRA@kSvqOHl$e0VA=J8#tK{zQ^zw5tFfPH`<t+t'
    ')H3+;=%o8n&T!C0+e39P;k}1VQ*Ug+ibVPH+b${c6$?J2lCNg=O-leSdNu|zP*0FwdB}5T0R`Y<V30Sy`M6v{NAhj&(BPPo0m3zN'
    '+XNQZ@=q|`K9*SUGM<3Yx>*ePeY@zJRmg2ah;c-v@r1at=@R!wD~@F!YP06)lMOEYO4oi?WViMdr5}fB9VbNU%iVk9I23rTqQ1qn'
    '!tnzdS{$|uy*%{_>iA<dTAJ+?ew|)xvSg9a~o&uY)yj*=geZj(U~oIh<iTD7%imiA6kFGH`!V4?I?GBR<_ee0Z3*k+YN%2m2A$TJ'
    '8jOP`eVoN&Ryl60bDRIAtVjrqvUc3I>p}xKLYp@`zZ^Iq{>Y+*~^J5-_^<48$L&Ddk$J4&QUr$A$z7~(<Ti8-CD@jU-#znB*Th8X'
    'gx@`m6oM`ZJhnWV0pt+7i~)HCYTWWS|zO<aBz7h9k7xV>4zI`3=hL@rc}-*TQ?-}J@%yXWjdHZM;%{Sn;ePJ2HGF8M>Jo~M#YwNv'
    'Cwa2%$MclVzdujs(Ai!L=W?xy4;=&cqc@_!oH1;)bB1icF$bv`HKW`VF1XL@#KPXiv!4x@W0<$N<hurYJo;HKx%T%4PtkWkBB8^M'
    '9(zFWSFZv8sr*O5oyx&S<FvF35Qpu+(Fz$JBw2ma4qEBnNxYc&k6NdfT-Xouvk$B8gxr8_#i|{Jl7;znZl{}RLZ<q27`^*RLknaj'
    'BC~tBHSGs{KnT$XbWG7SP(rw+Ba$Kq}TH*y<}oKIG$dpDfjd6MQne~jH={KO%7kzZBYrg1Rtlibj{0vybsj8l!4dt(asKl38KkN6'
    'LBGs8`V58T;!(x$wl*dod{_j#A6yvZeMFkkept=<p4pdv{I*R1K`n#uaMKWI99N~1qLpr2P2_C^xLSj<B@T+gej)#H&Cq;k7|dKu'
    ')NMR?Da!qZuKWlL4*L*j<Y_63lx+*=gXs5XD2q<ol=_-kP}qr(sZK)WUvfgP%M;j<bpimSkSgMeFFmdSSSaxWqmvx26p!5#<??QQ'
    'aU9uah5PoO>b1cS({%CT`b~EJWmvOQ&Wxzl{CC4htucS3!0)y89*N~HGo;;A%tBVpcsXMA-&mxI&9UiAM>)Xyj>U9OBah$I-5jUj'
    '!dFnuvueaAmyukD*<_ASIS*C-Fr3oSu!MLY{fDk0tb&nl+gUjRv_A3`l)SYv5ACmP{6Ffue>wCeLbyEn|uZwem#U>x43z-t>QN}T'
    'Vr7ieJ-e7Qg_kO#%aMC0Bn;U)|Jhjt;*jKQVi3|89`xJD3+2(E66koG2M}k%Lnbvl}wBaS-{j}%4y^f%G5bH92ClsIJmznrHO%T0'
    'Dc%pzgH4ZYYnUV=t}MA4Vk^lbH|*MJgRmT?YWT{jkuI_JIha<8dZ7>oezSS5KHPbnVR#BQ+G1>97g@#`)_80^$bBMNR{)aN4u-eP'
    'aJH$a(iv+a`ZxCJ~$#O@G5*X)0^B@mmVdLmWQA~Dg(7jMW{x$TCE+v1c|CyWKp@;8KPmUn)}o-l5s5eCXPIHY6X7N=9e!EH`3J9@'
    '-<mq$?ytEoMcb&m?{jTqGpishOMvX3V;!+q(|yM92E3KXAobx4{ftIymtHvXJ$kxF!Mf;;^yO3$z3>6i3*rHfwE#5w}g(mxj9hzt'
    'kT~-xUchdx*nx=ItTpE&pH*L@Ibu%LQHu<?RlO^DwddBpiA0SCq<Mv0ff{Uyi*17EST!AJA6Qp5oYZn^ZBE0k|5(J3y<P)6c#Spf'
    'thO(TeMRT@do{soqc=u0EZbyO*pGuJDEECUEk-um3}<u+I~A!Ppi}3=NoLeU|R)!5m_HGo#SUv#Q5!Uc*5?=&QI;yXgS$Up01qGf'
    'zN_cZp(yRQB1$-#JN#Q%6>i7OxcYy4`ukE{(AH((C|-2bzkiS^E#4crIn)XE1c^TbHz9PG)!NJA`IaKDQiOFSqidPdwc>XX8wF_<'
    'rvIlhDxFtRNDS#q#VIp5A^kXRuP11FLY+Pr-wyJ*~h(ogV_fmZi$ZuD+7c4O+gb6>@M%EL`B@yZBvU?Ymtv_@#}_stl3oxPq?T(@'
    'I6tSBY@VQ_{MdX*@ugB5H|~tHdbcoMPZZG7bf68oVdR}I|i%@WE?G+6m}-g8aA(qx+Ke{idW*#q)-%NHAyG6f>nBS!AsiC-e?>fk'
    'm@Xma%iPA=!5TTS1w4^=M%QO`ua<I%KeBv4|M;byZ4h<O8tH1u07?wrM>;#AR>2K|5r*~mBDg%Po=9w7PT^`-YYs^fqEz*-OD@JJ'
    '+o9TD%QH~&%vSoN<LScCd}6^e{T~mKmRa%?E~M}M&^V{L=2GYLC_Xa-e_fTgH9!4HZmObZ^w)#GZL-N;%dnSUp_9#W3)S?{*DN{$'
    'Top_e|&TOyC+a_!uwphRljuA*(J;qO^cWQC(PBhIAQ<G=4#^%wC(8cuIwrXd>g<13*>6mBL#yT9u>k3mTe#@mg1MZ*OtgKw$n_dg'
    '^Vq3GE0!~vs1UIbP_4+-*)QOS2mxbeU9|13T{$?;1smaO0VW+$jJJwBOtmBf4<vmhsSnyKX}dcw7+z6HTMn;$<^BQSZ(Gz*=>J9W'
    ';MOJM*EEXDrMw_m~_*mrWsUeu87(b<2NG;ch(k<!wI>3YW=%o<lgWKNL?%K?1VeS-YK9Q@K%3?gsSUR$=#+oyr}M@qK}DE$40U+G'
    'WgtFX)~gOa!aSXRgzB`A0`N|FtM?q2%ygfbCD>Yn;o+SmSLkfo2M>fAqEW+J+YYllfeXJJFO_P7Ury(XhK0FA9g!N=9Dbi5Dw(YE'
    'tG(4Vi_U(N>d2&+nHG{fDQtz_$zZf7Zb>h-oIX37!%!IL|*}9eP9K5R!Jlkxpu7dWQb@}+Nt>rf0Ikqg6`qg5wAj6K2cky+BOHlt'
    'M|-u<}4$#2hy!u$l|2c9=668uKG@$IUKm&(v+L>ox}}beZn3I<w^5d(TIXzILX2MV~nJlEF_mOLX<PtIVP^XRCsBrzAy%Qvh5|@m'
    'BbPzE$wWr&CJwS7vYAeM9D27hq5_AoQfYpWwK6r{mdL>f{70EWN*Mh1IB#vq%t^g(B==Tem0kXRc)LG?g=sl*p)fU!t8~@DH#N72'
    'TX$<2r+gqyA0>8e*GHA6`1+JjGD7}b|RM4)VwhFwNSl@w5d2;Z2r6?#RCcqusfoiB3D_?SfJ&b{@7$gp%w%0w`F!VTK4&M{tsIn!'
    '7d*!#__e>BtEl!e?6B;$15wmeq|0KfTumJq!J>OSr~C{PcT<`Z0+P#(?7Ci#l7TH8_RH13P<MSIENY5bZjc+I!Lh*X`uq8`8CiF('
    'V>R3&d7jDJ?&VNIA?C{PPIwav>2TWnfE`z5EIT-8dj6)7C&DPQ$X#cOjZ5vw@rKo6>5<L16p`#xxT2pdXBjQB{1WQ`V(P!<uT{>O'
    'QWQ2Om;E@lOM=r1JG^`YFO2@0_igt2+37I-!c86Ess78EXYR%&dkaBxKowITY2n&#|yXOwcdMkc@;%LHaoN9&dC;I6P$K6@l%Txn'
    '&%RG%(|a?5CMd$HWrRmR^{4>aT~uF<`jsGZ@%pNTOnvQ=t_#5sG4KyBc^Cmxv2=Z?5gkym`pK6(1v56w&I?(ovw_CKP{FS9$4{xl'
    '|3q#{`2t3qX$_Yki>_N+|CXd?+|#-e8$GGxala;2_v|ONvvMN^wB(W+nonZ;I!u1BI*3+k0?Yns_H<Ih9jtMFM!7|>FiJH>M!pa3'
    '~yhk=V`Q$WALABjLe9Uo(Sxane0lTTTzf@ajb}7N+&CPMA4Gw0BneiF?41aJ*L(}MZtbAAZX!o<Q<1be<OlFWk2e|`YIMrxxRQSm'
    'z7VhV@nEadFbZ)!3SQ1=xNX_$n5Yp1_h`llDx*z(<V1VKf{ByrE5)KrO$^TZA|WMzE4suM{_&bHfic_6UBwJEJG%_s>xjBM0{Q}A'
    'Hcsp7U;(uxuQI6K0^|*V__%A_#oy;K~iaz#=43Ux$UxQs^^X}ZmK|3k)DL89KD}r{d6e2KSN+(ieLa;7I<7ub!b0&Pj6Z=YB-$gl'
    'XSV*9mbrtd9-OichxnF2Mq(wl1MO+X{E&~VxYtXWxj<7MH-?qifogrE2%6-r(Fz9Bm&=a-uhC(y1z~}w#df)Z(mCPbQ_E>h>cHCy'
    'K(ubS%qrQrQwBkTqIG_3&-Mk?N6~O(S+NWJG*|Fa4ng|iA5K)Tam^jnsmBN#-J3yO4IUNOf}VJ9wr?`V?Z{w=~RhazrMe=;8!TzB'
    '$TJSjWmSC^_>wa=?sYlDHw!`#bMF}zX8=p_~fkVf~$DeftC93f%=)F8Lg5|o^D0u9T^VOeA>p`?E3YQShycwBs(BN_GfkcB<0mcm'
    '1)SnSCPu<X>}A1oT=Ee6Q~lqb6uX92|uz2@(LQ3-qOqt2(1v_{QppY+MGSBBd=ZRzE_sxQmQ6O1>{Vye@;Ma&7WUCtI*x6KTYoIO'
    'u^HsF45h^gAlQhEIWL<yj<9VkV2#`P<A9qBBv@kW{^?zx^%>CW47p#LdQ`}wIz*=rrJE>Jb8qYBL?e1PPtCb!|&uL1$meV2B*WEI'
    '<daI;7Q@@->CO#XjZ1;*hIQx?gh=EDVg&!n;{cY7zllk!g3YFcm4uN{=<hA5I`hJU=GUh0=_kPHB7VR%@WM2vMJJ{>O8gZsA+h=x'
    'PY5w0+bR|vNoZ&$%R9T1O^m;1%*lifaox8sx^xcjl7kV91=-_xS0vJVjj_H2@1-MMRum#x>_X7;`hzcWNEMMf@1Y_n3DRz5)lGJ8'
    'GUlhx?zI+PlTCotjzkR46`9DOB7SWI%G$afQE=%h&8+!UVyQO$e5YbEiSTc)`%i#ycL3)YSPHf<`mmDM5iudD72wy5k-hyl~TDhF'
    'lgpuTY1lp?oWpLh6YM*G?b!!@Jgw>_p?gxp#2u%vg`+<Hr>_Vx2I&Y42lWWF7o@zb0x&mA$lsziP6o&BrlQ2Be-=C`(b5lEZiilI'
    'aHgoVAN|91=pbEVy_O9N#f9K#u$joby^^{D$p<kd*1xa{?D1@iYMZK*|e6ud&?q*!gqh6;=`q@;J_8$fSE1nI<~1|jKj1`vTOfW%'
    '4z*AmLme>V_T2T*7GIG3TY}`8uC-h;<w0B{bloI`GNeo5@o#Wb5$U=%#a;_P#a(LJQ?8kH@#UvKwHIBSp;0Q%9%y_G7tYGnX}j#`'
    '>&EP6Dv}v379Ts&RnW#-!P!<J2bIH5Yq+`SZ11tU`q6A5i3)$G@_N3(RHXiA@Dlqn9R})p7Xa+TE+yOgRaMCOCD_yX=%>XZmh-w;'
    '0!w_E?l%{TruC7kmg+*zApPVts(X5yCkk&%+e`u@U%MZNe(*sBJGhq<fM=?%@8_ECN*<5IH@X?lQo#BcL+UJS9nm^rf2n*sjtkLR'
    'b2JtVoaZep-yTOu_TiAgNSteHRn>IH_Qy<MU7ylz+}Yp!lbEpD&&1|5?NQKOoS;yllI_jp<PJ7FtFu{>p`_4O_F`CYUt3@e3_XA-'
    'O{560&ivk(X+R`>@&adQqL)u>C3jG(7BO2xsd`e+p2ND<iWtP5?AJT(Vu{wrxHu0a@5Kr7}db1U%2X>K95a$mmYH9#LfT{;tfoT4'
    'O19e>XgL%E^vZ=W>}X98-?jm{TV9;Vxa)Sz{3-9c@@q@PgB;Z<kEyvI?<@rB6+^hw9|{4F`*dP<*gd+&`;5wy}6fX-$Q*gV_9Zku'
    'y!WPi-lF@af@Ol^_jviLNT4=#TY7Y!hI!>a`2y{rxabFNP(3jY7DF}SbU+kIl54C8@h|xGy+q{YAmOJWH+a^Gs~n>1GySl)=d1e@'
    'KZNM{o2A5NlK^I&h2-UG-*=YhUK9)A(mmiFWta_rG^T-ds1x)(A49^H|!jB1BuaDvu5sueH7A}p$%CBbo|Pkj*@IOmIr3#L<%{1I'
    'gu)dLdFc-^VFbd=`CJK)y}YN$PX6(jh(yf1lM9lR3Q;^Q1eerCA+mc<9Pw41(o|ocUlF%0*YQ!kX8<Hna6D2pDulEL(1hooxLqze'
    'XKG;RCj>+{Q6>JO-Pgo6o9TTPzB>OcCe^P4K*hFL}Yxb14pfyr^zxcR2_p^ou#2-UJkI+062)*;;3}BU9ra%yd`Z^%q4o^B^lH+('
    '!$h@#Nfz?cgD$$#c_6I%vK=ls<HfabZ%3AHO2h#@abcSmIpdiwUUwhDU7`L&lq=ZU9|<u<^4<)nMs?=`!W0cLV^amP}Ss@Zg_;uO'
    'ueP0SdWnM(TDCgSqvAv?K4N6rC9xW@HI)q+M^gq`l>ag?J_Gp<H$4l7UL&jZ+f{6_l^2$&K%B>G^A-hycH{o^27}JKvj%p=LjJju'
    '^5Qh8dH23c`*!{U@r&|kJ`@WIZGT&Z7|w7qPRjT|KW}L$Rvw~Sdw?@L6bOa1TT2!v%BBe2}?^Uknl_X1iu((*$tnp=R}JvoC-TVR'
    '+ulBLDP(2KS)Tr$I~P(*rcW(B7o``g<?7bxeBsE)qmV9K0B9hNq%W-=GM{8IZBUcI>{o`D`dY`UQTJ4)M9&9DlUswwmw44yiq2oC'
    'Nh_C<K}6Sca!TTumNk^4><s@Auro16Tp~fYWgU{CeTR8*v>^05Ui7V9EgV%;-8^AVfaLOwV1C9=A!4GVusdpPhp3osj84Ki{-qD)'
    'j1dQNNG-~R()WqD}cfxYkk~EIFFP(Fv|If$Y9lC3iN$hZ5^;mm&a-sE{M4hk8EwTdNnC)r}AZNN@=-W6z=4jIH)Ws{$R|EL@Nvi<'
    'du8%`&VVNgcMfFWWnya&8oo0$IJktDLf4O)Lzi*zm%y;O+jS793b+`_uGE@(^oqI=v}`dnRGI&1QJn!@ZVdz1a8u~0DBpUB0MWY`'
    '*ykA<bHeY@WuMdN?_Nar4V@5$-sjr0CwutLesM0xlou6+?%xAM1O!bG6pnEOQQvjo&4e9`rXUz@P1F-34#IlMRj_Jsw=w*Kp^-|='
    '3ESuLN$8Mrbm4(l}rkG(3txanPidyebx55ZBI>WNP*173}vS8NG9pz8zNj*2_BhX!|oneCK7^)CH6G)ls|se4ul)Ol)uU1ZF?hIy'
    'kL+)zp~t0ORZa=<iDZfuAtnUx$??Mo0_yhF%;J&`zI~2(}OY1wBoXaj}1X@*PizS8@&vzw;CSh9go!02=vq^{Vb)PhJ;AY$0$@|#'
    '`BOHU}`XAFPzS{HaxuzX&D)r%$BP`RH1Kj=1eD6QC5FkyL78v)7S1$;ER`%j(Umdlpdcb7xHc0_+|pE!F6JBC8Q(WjbI$f(3+XG1'
    '5ER4Kd}3Vlfi+NYiIjUP-AVo=zX1BdoUi2GpIhF!Ew*ikbffCs*29vXM@_LR9t2DX~YWQ&0xV71Zb`_KXsFIO)4sLo2W53kgk0iA'
    'MiLQnarb==z<hKy>;3%z+x3TJK<H>zPw2pyJ&5rUy?IZT-OG8RE#O1#m~$v;6n`f<d8-o+%pohUMXFYtCWB`BB{8{kHppp#r}W;4'
    'fgHq>j?&jTrG_ukTD=?pO6TdT)s1#C%~ql0U+%mNVQ~_X#1uOO+l1W{sdV=*=rtpXJX=Mb)`8fjgq{6eWcXsomJz|V@uWlI>6ej{'
    'V@q(PPUo9K9OgaYiDkxeJy}#bA&hS5_`oQNs<hYY%n2p3RA+|ZIC<7PMU`f>I+cj&vl}SjAz02c&-G)VJ5{MmZn$W`?BdxNUGomG'
    '1cO=drL=fq7h)vk~L5=%ahp9qxaOq2rR#yVKO?L)c><e|A1Gj$&B5YA7hsXC##5|w^ZLEcgCe)_Z^#)6&tCY^tH$P*RNNT*!gwMR'
    'hGW71vPgf&1?;HmSRPKYGyTOnk{4={<#k;bbZB}CQz+sNWd!FN$JOd(nj4iP?dhlo4*tQn=t_kZOJ$Efc9tI1Km5idr;Y3QrlFKi'
    'eMAAv4FF;j3}~>qNr~VA5Jn>DzRab();Jm9W>1i!4M)^rT0Adou!-7?H%a=ndsE1oE&-jXw+{I12ux6FlVWt0X-TgrdzMxUpst7f'
    'Q>jjU%mN@-eqal?1a<x;Yn}bT|J|19wp6G?%g)el!*}`zJ<gd^Z`v=V1DM!kbF{Ko%iq^`v{Bh8L<}+Fpg}TIVb}Pry=s3p>xj)S'
    'O#4jFFb}VIyssR)g}u)U_+YEvuVkQR96q+_cUU+nqPBdkf`8FF`W$ZX4%1*<>ljOmZO!R$aivoHY<;KE@b}Ivn{6Y;~8+##`e91@'
    'a4_*vq#XoE=9v?iG$M=961<3@O<(<8N>^%en;th87-<2K$Rbu4II5sG~UMWL?M8nXL(IM5@1zNe<UK+I}C3en)J5poK=(;PaYDwA'
    'RZ<Mv{%1DM3WP)83ROEMygZ2?_XbD2y->PP`iA<8_9D{g-9evBqn`h?)dt(YQ{&Upo1e1&jEs;G!66B3ehU%@-&p>@Y7(@))eEu{'
    'tdo*1|)No`uM(cVCU}2o^nT!m*AzRo(qwmNvC^+xOjD|8PB>b6)0bBB2xV4sdxr~JY6UE2`?V1FF>OsZzLugCTFD%H-@XG571kC{'
    '1gHHV3Y|Q1Or2RZP;ix+wh#heS0f-QfC3lOXbkCT@QH-^1Z7D_EvWK=Uw6Z!9Ly^e>o|T$^E{5@mF_MKCATf?cIYZ*sVlr7@0k;h'
    'a-wn{unV%k3*Q=Y&nnszP2Be|5H9AS%d*oHA4e>O;-aW`KZ=NTG24l*;}b}4YUpI?FwCR;tY1hdlK>@{ELQrL0xu42b(i`bj9aEX'
    '8Pi;O$?iRm}vortx(n{y20spy~#RMT50>6e#=M#->F^^db~Qru)f7ZkSXX>Xu#C;i#OX_=>^kBH}{FN8nr7S8{Is$U5u1wPEVNLr'
    '_XNF@w*|D9bsfDarCec<BepQWom17dcArl2EF|jzZ)v!$aM7f4QecUu`F_a_GT=KP`eU{I1_-&-iQKxC_R-u!N}<7ub}UBWk8z%<'
    'Qgyz2L^n-cl7k_{M7%ApYCh>ynAqW8{VX?+swv+?3=Lum7eZTx^44x^j3a9*kL>D6Q4C2xI!~H)#Kd3z%iH!$Fvwj%^V<>66~!TB'
    'uOe^4k_Be*N0RqiYF&Ex1qR4sqUl@Xm0ZopxX80YZIrD{B2qWlnbib`(r|MTNn|oi3XkbjvA>zF=&1xE+h>_xN&m2gu(|WR*-TYU'
    '1f+TmP4V}jt95RL`g{Be2=qJkuw-O`&E;kP{rJevh^1?hL5FQh%Cs^AD07Ye4zXlv24234ZrEwv5&@n+DRgO3kpu#oDjGBqk||5R'
    ';v+!+G+7sSEZ-&iAkoewsLpcfk=fjarY=y>lCng`s&V4yL-F9UDRLs-H-|XfK{=D2*)N`xeYEuL3hxN3352Ds3fjEq5N67yC+K7J'
    '>3HX-Mydi-+e=akgws{fXMW8?;PyRL99J*K%O84FLQJuDf1fDYIs25o+Yoqr5MQ+LPBnuB}a<4Ovb4)QCVNvr8#Y(2S;y1=`=vo$'
    '9~|tw-!v=&%9%hM;RATBCf)Edptd|7`2te>KEC((Ez!+91l{8QOyM%JVSf;K!JH&S;bsxE61qJNSXU1i(XW&qv=$5o<E8c7z03AZ'
    'K8l`rUjg<di)TvvpnC4rpe$e+1sSynVFk%2~x+?y&ZmDbb-#^aKrrUt=i&~+7FYE)6H;xAv2<Z)9_7nvt}-Hk>H<d9I^uf*SROv8'
    'RW+Z%rl|h^XLZT^5OX)TcS-9&imWj{?ohfZ+(0FJMX^VSyElNVkHo2#nb59a=K`t#PWp}noAd|Bd`ZTzQ0i$15JPC^uq$l+y~jr>'
    '(vt|mR??7zgG>6Leb6+PDtitXIM}``WQS??wK8|7d&}L7e<x8+AXE#He)`vWUH#K>FRaOgB-~ZBUxPJ%8NzXar+^1&LZ$qQ1(24%'
    '}oNx3U=Z0*~pG>?!e-7FmS4R89y4Kr$X+yH;KFL9@<mxRhF->$Bgi<wp}Jqhx#j7_gBt*Y@wBwPqN2kmi7s9L)wnklH|sZf4sZg-'
    '_<rS*tb`uQVoSs_2pYnt1HX`K2q1glvUkR*i=}NBNrAQo2Ppzidaguk5Y!@AOG0Fkraq+K_h7(IH9*wR4oRjaummlj!0w#hjt{TM'
    'P`5&@}<y8!L>ER?D>|R(E8Ew01a&enl>xL{qc{>UFP2P_3u;R6kngXk?EKVNvT6pN>BKtGqW3GppR33FmXpm)6vh69g6zH@4-~e='
    '|k6cZZj2fl)?b)*Kq|)(P{zrUed}i*Z}iQ=i6<fz|noyBTtcxCqQ;JJfWW4h9pKeb`cI4=Z2+gP9W5(<yWrzNkhvo;i%Q^(br3Mu'
    'nGg5`sR47qe_v`jnHSG>CNbZ{(Q*i)UJu(!<3z>ITCv9?1ha}_n%1=B(LiEiGpMZgeL5am_)>LtJ)PGJ0~{RqQY6wlNSVDq&jM!G'
    '<K{2EsfJfuyPKt=<n(y$Hh18GBwbuqXhx8Lh;zI&F!y^oQ>z7;4Wxhl0AQ&p_IMykOr97>+(uDVBwL0gC^%EA4UEsO$T~9raG<J*'
    'HH!+|I%`3Au2oJ&@#ZqjZ*Z!xH(TYN=rAcWcf7dSdmVuGoMJ%B{)_|xybAkRxAHIy_~ZQAupWHj}mWmEp=JKX|Nc&M-&@v<i;7>g'
    'hp_i<1*+P0t79*i=utwv+K8xgf|S`{ru!JWZKAB-;5E6`$@)cj>JdI^|{{Ycw_dVX-Q+B+W&f_Lz_*oJYAYtzdjX|MWox2dn=eE;'
    'pBm3N3COFQ4Q~p3zRe*Afe8)QQ8c^@()iFt8J?&ts-v5R1gn;{KRVt1I?;P(xWja_M+HQq?p?xO)68v7rxy%9ipU6T_VasgQ6iy>'
    'b*H1E}-aV<u2e3U^7P|85gniCT)ccJA(a*naLa`F%Rjv*cm%IV?we?Vn<?i#bFfa^z`G>bZn#`CSOF35<M8Tyi>EK)dOFTLLyL>='
    '+0h;ni`lowy?>=eI3KSddsw&Q-vqJ5p|wygVh&KsJPNb&?u?&yu_<W9-~o&=Znb6+@af-w9!oXz?vX3Eej@n*<6$$Mo8Hgq~4@fB'
    'njquvzADmuNm_RQD<jW<%O0q8mq_l$4`0_;4@W3K+r`M8#-`cq4hVSbw2I$%to_m6p3hblSo%0e?#qKakf+g?LC#CqI^{2547LXS'
    'yM+<unR36Aly0IB-tC81YABrGM_o-k1nHPBUwPb9U6(;xtxBk)$?x?Z#t%D;&yVD{U&-eZ{+us|FCaQx7qgPuJYc&N`Elze`TM)Z'
    'J(F6>2r)Zex_iP!0E!2lsZExvpGhS1bt0kF!{o*wX3J^a|D^(9v()DmAS*TSp#I|*&89jjsk7uW>u>9?LF$tE48bqB6>R5dV0J|S'
    'Qg%S9WDW;H%l>LFwoaCM6<KYyijv=_qBJHl-pA<E_iY_dYfg2?cxiwE5sxHI(=1!RZz6;v8be6yVDC*bX#}WR?Y;9Z9Fj+I-{Ynk'
    'S=NGE1x5Ke+JbRI;!j%>S=SoT5&V{yREOcXJ5utfOyElqcAC9;9g4FnXJB2EdlB2FX7mQ7&1v^kPexX=-r*De}k63@1wT1zr+mR9'
    'Ta!+L72#~Q4c?){lnv|){mgaE2F5{l*08Ny;|Ca=mf;X_!;>H;cYm7dV*uh?NN4KDXcV$4stWQjbFuPt|or$JozY+4EW5#+Ubk6#'
    'e;Tev%#f_Z(!4pID4f=20*RMg!;l&jYES~#5PTk+ax5J>ZsuI$0OOg`lj{}G2*o!P>%z5tJBYCc4FH<_iKU1ZMntCEeDHS^{(0bb'
    '%x8g?kn%<DgC50u(Q%z?(gnv=Qi8AukfM&!`3MMxT_z}(XkK3>gug>HNHW%EwPDNh;7TvvJqJzG43U4icOd#`74#KXy6@|Pz|jnu'
    'xPkm9bN+Ci*B76Yl$oiIGGQ6`Uas!5gnO5m_rbSUL85mmW^TnficDpy*=}A90>4<k6|V%=~C+4)!kd}>HY(mz&aV_>e#uv+}+DSt'
    '4)d;w+E+qGWC>EwNizdtI=gc21M+KhdD~BlZ)D6$*X3MF0I`=v^HD~T1({y&d=&>JLcS(xDB-y>SmsABcs=&5Ei^dL(N7dR16}MN'
    't81ggqLukAaguf)O;LO{g4P+2V(W18M6=3#h~2P;XB)F{R86M?n@-0f~UH`&i(qu5n8%X#&DjdkE}obHoQZqNhfwS+Y*S79=-uY-'
    'a!Dxz2G(ICBOCA+XzCLNQvd$=R@s2Fdi%4<s}D4vUbs_9YN>0a8)8$b-oO|J@4rSh2!Kze!$^m31}Hxw8L?pUBK(8U@8Evoo;s29'
    'D;k9#M$=V_L9Q%r8ki>@Dzh!l|EdP-)x~7K@3hG$=@`SNx_PMOyTJ79zYdY3QjS9#LVN`=mFVg5$Be@VkQ(*?8MsqeE<y!xl9xW?'
    '0A($XL^kVzfo;P_?lv^Ix}V$>>J!|Ct3=7pnb=XX~B;0A{~`IJ1SjW$e<1NcJ)-Y?%mf}QvOgfOFP3RhzWOWv}}uwO|^K&XLc%(j'
    '>sMp=F4u+Pzu(wcIL)YCQq{&F<*V{;$u8&b{s{`ogE#!x_c@e9XJWtz1p`Lln~QyJaSM1$7RYV9$$%2Iasdam8SYKdp2dI8M|!El'
    'XJU*>-A>9Z<PKK_>CN-qeGAm`wYYqvYX$?upOoUz4X@3zJYxMgOxp{ZI1K64HEoEN5p^F7kF*mB|zEU6phOVdn-F}VUQTYhjb7hl'
    '6yMJRQS8D!sh`v;&*WrN$#2N6S!gj0h|QC6OyCD@g=$Yy_qEqV#WTKxm-d=hChkdC02G^B|L=MC!#?k3Nuaim^h7xEXfO1NjxRmi'
    'lCy+maY$vdVk{(zD^r3Wi7@CDvzEKlt*6P!;)FM=-d_&$CqHIS)7t?G&SDR=jlds!-whoMi5ljP(M<+9kfm`V^K;3-Mn`A1iVOd='
    'Y?a5^OwWx*pZI??Cmbx-A>hN)7CiW4qDm^YK3x7$KLYL03V-=rP7yXUTxeCU1lwi%_P-(D|dy!`n=4>8*MZW+R~^v*+cUN0kAaH<'
    's8Fic!EaPUm5J*XPa<fXb;C`r)h7AAKJ3^S3bAd<v;MfUqYk51B^MJ>UDxnDSa@sLniJ|o}q)kbix5I+oXE&)m8wX_A!!LiQ(+d9'
    'u=wJwGL6ewXnV)EXUD*ZsOTB@n2hV*3gRu_R}+DlgeAx7A8GCK+2h{QVk#R4+N7*O_Kqt^wX8gS!Y3JRZ?b~G~g}j-jtJ2eNR$Yv'
    ')U`x?(HwR_k;+Bh8k9an%jA^5{X)b$2qEvgsaa2!nuc+<uJ*Imm1Xxrh`Ct;kuKoHbLc_khBuQhpzOGG9@WCFeIZ>d^Jjo)UsgW>'
    ')PXC1RW3Ebm)3U??asRRRG6Y0MDa(kCE)`5i%?U6PJ^aOV1+-N9^|@6pNa5U7up$@9u%8)!U)X<h`fMx3bd2u-1{NGcK+OG15+pF'
    '%y>+yyV)`$k66ybPuF@H8WP&_mr6W<yn&>(L7#T`flyQ*I{nN7w~j>a_#md873RU7h!Qz<LAQL2!An*=4-_Op(vErCRW#uj7t6{<'
    '@(5+ls@>)KS}y0c9bH)O5Y?@O`(Js=7)%-Vg3sZjd)vCNUF$)Uxd%c&UPwfi7jeF)7A`G&p7JUH2E#SM=lkTX{g1q9I#)d93j}0$'
    '^7kaX36Dz1&{4EXiZ^Ul5xlO)G`eP0VuXX##vHSVERH<0Lz}6CX*aVn`o1?hBgD;G0Wyn#{%V6NGfWT$%!CphsYL=O_wku_*}738'
    'Jx1vj6r-fx@iKzPx_}i{5miq{Bigk{$x{CIhw#^kDtVcQNq$BK)SYYUnEAB$KV9aKZ%q9c;828LWilGK9;*iJ4rDe?V&=&bi`O>^'
    '`~kEkw0^}ev@8_PGF2elVVlybVKqjLhh`$&<`4H6KCs3HtTR`3JI|x$aREwr`+tNh6@$7pyNVjjZpilY>-|4cEv1&?k;oj&FI;=y'
    'WBtMc+gm;pO)aJ7tmySv%CCBe|b;aXFv1HGJ=jrN3dB;{>r@tJ2<KirN(kMs{C#UYS-@-o-fw=LzC#mcll^kWNVL)*H`D$>j%5{m'
    '}}cBq}uw0JDQ8QS;M3-4Wot=%uTTcbH*2v-tl)s<*xp6@8BEBd?;X^b|_}foV6UstM(^u5M|l?ll2Lf^-r)X;KC#D)aX7_U|?UrJ'
    'B*qOiXgktcBk1XDqYY^h#AFI%Hw5}#2l~MZ6maH{ktb-$e29vMDP3)Fq_!v-Tz2b8Em#Oq9jGCE=0xSnd5U;p&pZDxl=^9;vsMVK'
    'xlkc8-DC?If(;1QBrVY=>LghOYNe_u^wzEH-9hAsD`Pun4`o#{Hcxl!=Jnw0Wz4jI}^H>Sf#RqY_lD&%;o-<?s%p{C~anBAe!`4_'
    'Jhu9a=4D%sez$^q9~Iw-tFX@(T%H%&K7gvdpnuBQEc!ii5>e{suM#HImf);gb$Y5V!e8>6~hDZU0y?3j3L$@Ulb)xsE4~E`dVcJw'
    'W*>s!+RAP*{!U)Hl_Agb`)`KjjuWtYZX$c1js2>x|)&ZY8+<b5;>zNrihJmr2gT6X`6a)2|KV0cd{l=-1oIh=MnYfo{qDRo2DwoJ'
    'U)A^q`L{mffA@V-R@fY6yvO^$k$VELA3!ya$*&-B}bNGAE|N4kujD9dgUvElblc|VF`uHS=AK6Hj6WM{%SMkZr!$*$!Q!rH#T|5N'
    'OBVjkSU#za<8Ig(F%|PYnK;It8H9P`hAL`k~S54DNmTmt<}hvT*hKcFGEuNZQ*f!{3iC*;nTI5i|wXSi5D1g#j8Lg`?f;MI8J>82'
    'KCfpyOM==5VaFD2-vqgLcw^t7T^U!uljG|0HaOr0#0$)D<{ouP{dS@4=8{@CiF16NUpcuc=H`Nv^vDh-<E#;zRd_oRgnW*J9F2TB'
    '9_Ma+}q1}oh}VapDR>&kJd+y%O;(-|KCl~KqUKrvV!Ly<nZ+MRDSW%OWk`u`RJvP*y`^txAl~FR3gB9?b4*EAk0{<9ll{ss0`KEY'
    '6koA#!XNfE?;KRgLwxl+KAxS#!+HhTvOO07}Sreb6IP3r<-)H(y5KP+4`xO)UX9qTXfNA*)~>KUTt}_oUr{cv#_=_Yv)b-Au`T*N'
    '`LK#nfmqd+L;@YZAvD(Julgx!t?H5-`HPOftoF#iH?m!hl@a~r%$d+HaT`bb3)<0iDrR~Z)^eCgE?zz1NoS=vq}5c@K&h@3kV||?'
    '{849&bBtrP-a3LpvEcG*Nd)d{Pg;XtLsm$m>iB)UcC2z6CcUSRBiZ-KpYx%=teRZnkON>Ob>gcX%p}I>ImbdBdHM~(;(avUbfmQN'
    'c2Qm6S=Tcrm~bxTcDQzMi{>XOh{su-8uN}m}7F4_)yh}L!FsIRWxjkD*C-ShKZ>PI=xlW-Iz{@-g_veVI&}1Kq4=+fR0I~uYe~mT'
    '@#T6^e`tu6CQ3A;s}@s(NXbjop$Ne(#EM9>Dq{C<B!9~^$z%lXb7mm!@PtY_$v^6mfB1ITq%FHuOxd|)LBXETvKF>MXcYxZBB3!P'
    '7yn^Qqr&=d3nr4IugT4L`#JpY5qvO^ta1vmv|zlF50%@j$^X`K*i`_OfF|+jJ)M;T-$g{z0Hf=Qps_D6Jh{}=M0XGBjC=Uu33&;q'
    'Zfy*0=R2cok*illW*ps+%RQ<vo2+Qh0x{P)yA*b<DfHdq`cLv!A<MfvjB#S!+-ka+ojNtYQ*h76UMvXM|1@{BUKsDI5hrCZ+!3pg'
    'ue7ls+3aQkli~NjhT{w*srgcb3W5l1)50!yDs2sY*+btF@4|)D<bOJBH45?4uXtz17Ed6>umDQ-U!_gCv1)akM$i`H7I*KO1{EL`'
    'L<|jCXz&^7#&-ca@I=LE6VDXS?cL^VHR;YSuM{e>qFL<F(JHi5VlzF^Rq&`3N;YfGS)91U;p+&Xs?1mKty)L_^DIqhJb5~hU7rMq'
    'Ype7nh_io;<~mcyL&$gfm}?;xl^i+7fK*RR_K_otK(y56SUPols0aij)1@zM$?1sTTQhvft?Hl>mDi&B5iT$*W2wm7n#~uHecmv9'
    ';V-KN^h$4VR;9ehk~2VPBd%PNx$u(l94%Wx)i?drKN%6HuvP&X%A7FeigJ4B@D}H*~i-aeeWAOJQ)Cf@n8xFsdhM7kb7YUoqzb9G'
    'hPsbs~AOAqc>3LF+E@DQi)EdNYv`)i?SSC%aCA6+Z@&r$oN4t61ew0JZ%C7bjt&S-741xL4SZS?JD>5>?rU2v@?IR{z`d3mPYO9i'
    'i>d)DrNnVLUb&kD}!m#yQ>@3#7#!B+vKo6wx{p&tkAHB#qh932B^+frsJN0pOpYalRCqQ>&W`<<Vs%I<1S#$q3AE&V)u)H6Sn0Ix'
    'XPR884(Hf&pg2)TsSUDzc`Yl0589f6|-_gDCY>a66YuaIX!dKfSY9-ceRaG7uo+7Sl#q8?J^VEo%u>Z-dv8iGX-f%dN5Xg{^{}rg'
    'up$xEZ__Vh{A)=GV@X!PnKI|!im;(eqOd;AtxL{J!J5zEguI8YZ%>>>#MWcAu_w$WplO5SZbGX*8c15?W~>{_iM;9s^ly!MZY;4m'
    '1O-%yyx#p31l4Y_O$&+mQ?0s2-&o}DrGOt6KLX~s~|QGRo5OLXZveXj(DKHn1ANdhK3;`q2eroFT{z&X$-YvM7l+LtX9dA)P5%?8'
    'h<<tK+*Ms(w(tDP1mh0jn<~H4}=U-jUeunCrps$WJ3KXB~`6NG1u%RT+=ds?l^;RonEUj*pGT;SOm_rP$^+X-^g6)!)<T3e}Mmc_'
    'idW0`^}(IQ(NpC`}6EFnkoHo#1#**SrLf>BS0wD1jnyEnr=`p{^SOAy-K4@n;R+h@i9lOjV~6R8p;Vq&G*-b5BP0or=8UH!Ysm^+'
    '`zGg4jxB48(Jc?8TO)Dv+46Z>&bJoev3*u>siv)^0NWROY!8<lFT(j${(>b&x2|(&W`2<)nLaa?Zd+Hwa-mTYF^az$N6TcB-P*mX'
    '+i!VOz5@viI<^0{&xMsog5nb?1;I2S&M2ZSOlRcv3yUDFS<8w_6gfnsMNn*hX)A?JTTCNA93FLNZT2EdU?mL>J+^H(D+*xLf!?Q_'
    'Zzw28#-V>9f!WUaa~2Ri~`WRx!Z-6Q#^u>yQpfPE*)3a%5l@pYWd=pEEFhsPmQ#D0J{=NZ4d;7cA4lQpq2z?r2XJ(t7(I?aN7%B7'
    '{(F}S8M{(XJtLP`WP-$ef7NAl0qHI9C})vF8!C1+VGbC)lDRx$5^J9HH#FQJlalPFS~lYHh(^^h6$m1WSiRGp*n8+PSb~M*M&QBx'
    'y{#&JoaErXRQj_1Db=KCc)KeJMI__JLi6K{BdlhKaL&qaE~5m4+<;H?^4%3a8Zf3f#OHiFd~CC!89?Iu`VRH=xV%GkTav>Zo5m=F'
    'o&tr=|IA%yK8rfE!M)o)3eVHvaP8t6uZmY&TLWxRh_O~xu32y%Id-kM1&Y_-1<TOB5UJEGu=W2Gkg)vc09})besqN8I%X)C@t|M+'
    '%X9>_}KTryC&UlG<e7KaUpZ_S(qzqn@4E&f)S2Q$psH%F$=Ji0WloHkLj>&;1$~58e6EJ{>mq25BKjQJ$b`NTS~QW7BRu*wNd{@('
    '1If4Zd8t+)F!SCAKMrnW+)N!V?(qT*tldHc=hS(UHd&HGvE-a8?m!PuW}BXhRfv_n*Ly+PFji+kw_-1VL1>k72z?F7a>WnK70tLg'
    'O;c(ZGnhcod}5#R#93+ne`x{C%vk3bUXm6<03X`E}fR(Ig`WL8*vuADmM%<G*h21j!BK#mAKA8A}eD`eMK3@L^ZC0tt1)d0t`+a4'
    'gO3fQ}Coil@?^<L!q*hxLjV>(|@q@Q@xsgPXAA}2J>kP8TN}HRZSAPNsG(i9j5LYODfsVMfI?@8Bnmq8cq#A@OO9(gXw`hmj?q=2'
    'R!?uY6tE^_r1S<l7Jr)Un*k*@RA=s#{(S)5eBU<0Fo2iz$(C$7Vg!iE@h>m{KQikChl0!m$tyn74-o{Gz*kbZsJh@z+K@zy8~sFy'
    'r~>-NQ~GL%7h_#Og8PX;tNiHJoa1%pnvHwdWLDiRIk^(JztJjLJbpQ1E#d`QA#p_)}v05I~m%6F2r6OvDu=M6kaY0&cQiG2XR(fH'
    'AT{_08xK7hf<N&#6&nvNkE7uy^vzRqO3({?1hvPGf8*I6ZHl{B9RC-Px|0On<&x!#@-fcJrxb4uqNXVVw6)57#13P(`!F2^G(VwV'
    'ePVbK|c}^eY0@YP%pp@ZM*vh1{;X+-`AIdJHFvx<}in-Y>}FgxyVMkh&2j{DPqC;^>6CKhyesT+nXLRWi&7iq1LAN*G`PZc&>0LN'
    '+}X|_%-%2J3q4B<|9asw5UP7z#Pjtec5~{m9tMf!=c2J5|u1RsEv}JUa}$}`<bp`Us2*pLQmT}x}yS5VeH=68o{L}N9xzdSUc@Sm'
    '44d4EJet$=qC}`2;C-7SHODIrT}%*AI?YvI+adREwX?t>v_pyH6a#MM1~SlaXYHRqxMGJ7*HHuPDZtS=uTQLs#R?PwPgoHER6tn-'
    'iR|}>??&ry;zv{f1<?jAKH@=%SR95aSR1%NeONvSi1fYJquYqa1u>xRA8wRqYR!53b~u2Z*5h<<}G8DvY=gpUAKD9oXJgb))Ms0c'
    'Ca|`*raLf`rXU1T1UzSP^;=y)qP<9B+Vab!je;!0}Mn^;AsySsa8;Jn<{g-CmsR0L*oWk4j}>lEeT<<H7OQc+o-d3Z0pW$e_$KAB'
    'IZDtq%H8*lxKu!5Y&}bVe^>`Yn@+PUWldKY#coqIUI?3ownz%o%$9ELJ2x4R^bfOwJr}1mUr%EJwbkVduWuTws<C!_Aw|Z{qMigT'
    '@$3HQymLnqpS)ku@si^J}k#?&@SQ@Ih$3hw7<Kz(z|VYyF%4!c@6`K2Dxc$pc;6R!LY=x=hFGudjvas<o><>K2%=7TUEY;-s;BiE'
    'Od2&?FobjDwmCQlx<m!RhuHaRGLW>SEsx^yBq;K=!+cSps{3EPuFuLyP#w#c_96`vm%qc3(d(1(}3tEM4=SPkKt70%R6BLQyA2TC'
    'u<{zh!=z&=c~0f)cn$5e`w}RgG?juR{q?l7Obds<74Bi$LHkAh_Mu$;o@VUB?UKRxVs=FV33{|4`G_oad*AhZe6fMb@JZ0bvgq2^'
    '$&5Kz{;Y&Uw@3=P&w#y=n$Kj7#V7v_So0Juy}>bh=OAgiT}^rKm1im(L~xkS?`~G|2mO^vHyqCc~sNv?V9c!@m$2ZU-0;c3S!r5y'
    'g1|OP$fl}%a{8rJ=~EdqXu_xQTkxo#d-6p?O%WR%eKFFv^d@%_=cveo??T|uN^tIUOlHKKcRz)+TnCc^(dF~a!6pkQu1Ifn;=&PI'
    'ST0_x2ILP9rRM<6!HyxXV&4Oh*YTf>^qn3St0Oi;msof?aL_@?f<2Rx-K3D-Z*l~1OQ!Z{y=wV+PkH&v|g072_wMI?QsKTo7U`c1'
    'FpATK{IIOv|K^?!&mLRUfhJJQ2Z5%gZuBpLxOsHd5;6lUn#-zGeN8srFIP&_hOlBNq&Y%hg6OgnXGH$W9!$dp@9#HGVO|vpx9mpg'
    'XSxxKGF;f_(OlMhav@a>9#DBsO^eNCy5oJGxd?fwJYBy0`))gnb2h~n_0`P63BkTR@Hs&0g+D4BbR)Dt2xB-f{l{d7>Hh&XDN30d'
    '?(u=ICRid+%F1u=c}9Yz6c>K9DR-Y>Y`2@NuR1<oEbZ#V;mv+0S=X;e2>H#!lp$}GVQUJ>-!hM)^W8sWG!x|y8#`r@XZqNCMpF2)'
    'MC5yh^8_30L4~NdQ4oJU03P%d}*i{6@95G*m5_+T+Ss=aZnq69PU;5eP!oR?1Uae)zV~avmh>J2T<|lV`4L({3Qo<_(-;F;B`DU8'
    'CysTr6PD>kzt`dD`Gdp=@vR^Id^j!HY!Y>J+?_#?mRU>=#=gBc%neeb?peU!GT{-uG7FhQ>=LmyFh5!;5z2m?YSvXfd`w8dMy$}H'
    'b$dNG@8ZNt{k1$Rhym^VZGe;)s_0v&5(DWSF!<H`ul?$XTN(|HT!mw<wYQw*UMym4QN<7ijA&Tt|g*M+#yHEF%z)AQyQAnzYnx)6'
    'RA=gYrJ)5PkE@TLQask-*^w3%Tsmq7nKtfQKdur<cPBqg4Y1bw`P|Ro1?%T<2HtqpXw^=2;krqf6e)zBir8Fj@eg<HLW8g?0>!8^'
    'z*?`5FXl8IC3VT9FhMP0a)VfPh5K2tlXyIHU++orRiMdp#pACmnVrO8&=*>kRG>tW^SsM%5l%Ktj-;%-5BvF_%wLvLB)ltQB_Y@3'
    'FNpNz1%Q#cS_xRmw97nyu$<I1Wm#b4bf!AAtF^(F2oVJR`V387%Zb5k(8r;>9`4H5(_hxdSNyLHqg4%BGebIVpj6jgP3xn1M7C2d'
    '0V!hv~&rs#dkC6SY@lgOEYP4YatNuJMWn@RDGF`nSEJGi4Ea!%W4W0R4{A5ED0bfIo}X8DE^<E>ICml@<!(jS>eyahf@eezzWPFf'
    '+0S3CVdNi(vj~T*j?U>_KM!sAbmzdV+1_t^g`kFk-iU&2-T@D#2s>Qi6%fVOq|fRd2EJ!d}mEnTP%3cSYp3cUFumSB2`$sJFWyUh'
    'Ru5YKcK8x1L*4)_kGiz4*&h}II#~uNeVe97~?@mE_5vh2FAf>E;**X#wr%}ddQ{8tRcu1+SJEpik{@P`<M%QuPWalwj*#DNGVPJU'
    '{In&Pg=ak6ffCVzZM;b1BOEz&xDpBw5>oCv~B0Uo$5Eyw5dg0>`h+C*-RM%_OUy!K>?Y9a6MbaBR9#nL2x*s-U+k_vD;^7LXzO)X'
    'gbO`mcsqxa1tVg6a|CXys&KEe(XZZA$TS(Gz-hXB;@Ca=OlOA{6n;HKpJ~?xV~`N*4Z>iy8;bDVr=#<DTXJ*qLh5jI41l_xJp{Cs'
    'f<9V`yA0}v487$cwT1sdWLX`uaZW|3jIpr)O*e8<y+oDEwcQvS8_@l=_5~=B~tp@Qo#QR7o0L)Q#28rsw$Ubld%9v^Htef?ys~pZ'
    '=ceFB0CH}WeN?z?Zd(>mom^&){7#Fa+y30#Rs0R4&l)jA~cJaHbPtSH)tZT3Ks{7kiV|wp)Op_EtS7C>#AG)Y23>B3tH^|!sTJd='
    'C5tB;|kZtWh=g9%au=Wpp_F*uDP~LOYn{uATBOnn)7e+O}b9Sg=@Sthm2_QS(weR4oyDR;Yts4sWSl+&_+x)aCiWEAh&1hpkMR$V'
    'IsYG6`C-ZNz55ZOVIEkX~V$ew5S@1{W%8k*=1B<NYXQI3;ap7x^~bZ&N9RT)*zpMb@VVRqY8+D+RPN-9E`uyoCA`^Jzl2K;kt{`M'
    '0q#iWfZD5YdN-^ViuwZ5qLaYyMDw&=plbx>=c3s$GvJ`fKTNY`OH1%I6Li81(Jy6a)8bo>rMW&?IKdsRGa4?W9tTGtXgv1aui9kA'
    '+f6SfjQF>wm1O&Q)2E-S&y;lC)kv9>4<Wpk=HWD+0&U$GLzBZcHoz2`sG=NzNc!4;bD0pR~~#{yK=!{8ci~nS-<nVZxCZ+k;Pw~o'
    'f=vLVt9@H0(1Q;dA=FRf-M$10A{@_Z{Mzs-il#b!e=gEXHH#IAuKX>M9w#9o*4()*gZ4AOc+Jdq{w4Xoj@tn?>C^Gy>$B8{@U0Nj'
    'dpYjeT(!hvZ-T&8Kz@s;f+g3F75c%gu*)-i_tcZOd)EA48t*LgcS*w{8ltn;K?#s<JbYGLmN@KB$;MVNQIjd4I=1RD0bJKa&j&BE'
    's_7e(J2t^eJg7Gh+s}R@*{4Tcw?fU`6@|fu2cxL<l}22+R?%yis#LzA;~W=i<uQQ6zY^PwzO+czUScD9XF3d#|i*-ND>U6Fobi8?'
    'HwXy$iHQAoC~^8f2B24>+PhO7P%6aZ`Ra$AaaHW@Q3$yI5S>fT~vuPu{?;v#aeWaqM`GaOs3Is{WRB^%cBAg0wc|~7^bp5T#bZ|0'
    'iNf5W)!zb_;Ct-cR=RsUV0I<G6Gl)nnYzyE?5SSJW%$wNmp(!ieoOYHhW$KL<&I%sLk?)+T#QM&c`OvkBg}d_q|*Tp#wq;1xpWxL'
    'fc$SIm7RGy-T1fk3uY(?XeSFL^#RglzOh;zs5x;9%uNRozB{&^KiSOXl&BpHQfSD`<6BhaW*zHCDvm;wCo8{U+?m&h%_DLteQS5='
    'Gg2s6$FKrr-kOGM4H|45<xrg*N<ckSaTfsPoG?WS{?Noz?Qv4xkZ!yp3X%VLZ4h7_Ci%tSX{uOF8BSD0C(&)8{QcKh?w0#;7Qq6l'
    '2ZUC(7?o-Yc}4{2UN6WVi*>!c&-U(h`=2_42<g8o8I>|(A<dC9+nEL{E`1z7>k+iur<=wxgiP5@b}K4{(dI$hkCan?-Cn@CD73<i'
    'Qx5dEX^`w=<E$I8w>D2RW${gxv2iz2FhpxMgSIjd!#LEB@JOTDfGif=G&Keeb!KKZ)C5_hTwU?2D7PQI89ma=2B23f(f+TVBct<`'
    'KCLO!9LtPG%|{{$gvSb6x{?nWt{YCij-D9^i*=43-thT-skMtw1<1HIOWx?r4&L+w7*i#S?tjR)79y05laE*y4ixoMp)j1CGcPTE'
    'Odcrx`^rWIsd781cq#4$=o_IZI4YwxNTv5)h;66kHAUZrW=OdoYIiV*~WB9sG3F&v%7aF^spQFynArxZht<qM#?+rS+3G=Uurr~q'
    '-QI?SNJ6MX3OJkGYmm`4#CyD3nhxE4>Z}Y!+HD>)oHdna{bo}vzSZxB}k;uy)fhNOHykpnQZLR7`H&KL1W0%=8Th~H6qs!pkSI7='
    '0pY40vuqA$7{onGl}G$4U_rxl^gZdM-Adg%#WVb^t`s}L8<5*!A3wK&awHN;v;6;V48O*Y;E6|o8^CqiE;D*nU=-j8ypv5<IHT}p'
    'zXUHzdT+d>_T#n#5@LnUYj`_bCN8n%+iu@GSopri8LY(h0p~IuCsS2lIjoje%jmjd2f2^ZYV?K-N2`Bto;DAWPWIZYMXguF8lJdM'
    '&Lp*k%f*WPQZT-NeLO0R#_7#FfL|e0kB}hMxGIF*TMdwO0MC2)(R_Y(wWydVYhWi;A{=*Cn_GcmWxe0*{Ybm=0fw@C;)~AD*b_h^'
    '0V%)q?crGlnXjYY12|sU8+B6uCE~Wk7SylYui;26k0N^O{^lUul7|Fk7`dwQVPra?CmtIY#Yz5bi68Uk{$pTme(&0*Y7@AJGoM5b'
    'FVxrYzN{F-C8D>TeL@-7<Y~&nVZRX?%3Z6XST1u+`q50BoaZj57RER)dQQ+*$Z-1z41Uubh?DkbtXWk_-O2zL6+KH$gk4Vi;&L<*'
    '+hhisLjlXHrI=ctyx}OY$5@cvGR3HTFR;sJU1<>+qibp<g)2D0jXq-'
    'xSM7REhi<x?&La96QRJL#3X<iKP3?YqXk`Fv&Y1Q<Q`413H&Vu@(gY5lt<0#da|kJB&)NX6oRACj(N0e{m#kt6IT-x_JJ$*@sn^<'
    'r!KpHyZy~z$c`_H#H}`dapTMtN-@|VLaAqj5n55@)>vzuH3!Ww$>xlh0KZc;-)QZ`V#3WM0ZQG4kD9da$ri;-lC*bE&Jj&lBHOpJ'
    'DK<6cUfY`K*5F0ux}PE+Du_=;L@m#)0W=uR`CuhL4<*h-EF{!E_64T{n9+3-Nd<3Fy{%am5;o~6n}46)g!M%3Rp?fiROHv@FE(q4'
    'gmzt`R8PYUicIn>*_H~C3B}wRSl?q^z}|fby#2fOp@IJP9o@a{mEO-vqKbdb#_<yV_cwk~sbzP7QV^3Rb9hTJSVmW^6dpCORky?I'
    '?dtE_Q|jp0H8eQXU+L&5b?+gIdAZl*IPJ6n{3?9f|H<BR|3D>vfY4j~qd)t6VBdh>8d%1j?j7O2@7bUJjmdFS4B?Ayz5DQ>k9xPg'
    '|KavuZhPayjt~F!y|+Fn{i5{6N4+KcpO0QDWIR85>6P$JvmA2rb(6GS?%S^XZxy>wKFj6blFyqYKltre$y<Ez;kFNd{ei#8OKihz'
    'zlk>mFjs$v*o^*4TR7{JtS9+LFWCd$eCv(vA8dd3ox%e`5UANbL%Z}A_j~WHciw#Koj3lq<6pMF^QPY}X!dwX?8aTZC_jwYWLp<{'
    '6Kwqvx-aXm&=H&Wd;hI%Z*G6*tq=SzY1>-;+WookK25sdCSUQEHm-k)vmZ84cy!z~`at_b|JJT3Y>2pQ`gdG&O~r@*?9X8_R(SKQ'
    'a7v#bAE=l8bz$+sZj=9)?6Z~*V7f<Br>EJqjUHI?t88A=BSqgP?CAI3{q=`$b$syduit+o%xB<G3A2~bx%k_I&&6Nc>0J2gZ@l}?'
    'FSldgyw&VRU}Mq0dip;1eeuh;-p9{7KG^p5d%t?C>Aa<uX!0V_9&I)$uuAiXpSEf4^3*<!$NM+iw*P9|KiWv_jN2*94J5d&$z4*{'
    'HThUBY4U+w&79~N?BCZo!p8NtH!=CPt31>*7&9a30OHYYv&FCUcjE+Si)}mEHb-%Igqqr~+k)8AyTA9|`|ti{+pqp@uP)Kl7BIw('
    '-vmXL-s;oty_=l@xj=0W<xX!oWNNg(`wx}2{_cTK8(t*0seMb>RfCoCp0KrhDxW}RwUxWMA%FAM`xL(KZTs-Ux88rpuI#UD#gXam'
    'sl05L|KA^d)b*2(KH7@^{BIw<w8iAm8~^;)+uJ()Lc8FjmtNiaDs=GncW?_E#&1lZ|Ks*wZU69J`8DIZZQZ@(AnL&{Go``-chCpi'
    'R71XwS!oW0c&7TqwM{S(&(f=}H-3>pAc|@iKaQY>=2{p(X#sO+t)gGgJ}TlHo~6Gv{+8&5uzBA4)%Jhd4gv7aTmOYx{-2&<th|oR'
    'wW-Pps^zO^F3cCty0FE{eDR`st+-lWy!ds=LVoegpEoSypGj*sc~pzV{~|w~!Gh@c@cnJ?e6YPi;3b3mH!kpVt!w!9f10KA-!}Pv'
    '(>cfgnl>wSxI%w<PkArAh1W}6W-I=7V6guccnlxEQrgvB>FFAHy);na$M(tRyG=jX2ZQ}vN^Sp8>M?tS-@L9TSNi)+irE_e_G5jp'
    'tFK>oDRuXj25jF|x?a{@xA-OapYC1$BeN&)!!V%i7un6X+IN*+yURx}eZkRu^?J!oV86+azTkhq`Vn;lt~5nI)ZgnjNG1UG$DX}|'
    '`#S6u?E06@Zyd6>vzO=F?da?4c|CUrQ>VSAY)wJxx36d>;11%)`fw}mw)f>NTe2rbhcs3&*<WQoDV<ZPrYK9BPO;4uXDJ&AZuJV+'
    'E}c^!@o&?4>hH5F_Y4gTmUdKZ(51c||Fwb#eT;GHBAIyEDRkw(b9ZG=xudB3^(ERi?db059^6;>B1RRvyIOsd(=_^yjMBwNG<~oF'
    'ro|6cJIMfg;j6R|uJBbbl?EC<$7VB&sJl}93T{yc>%^K|_q(AoCd78wV8eyodxE3Kav``=-M!|A6@FGRPp2EDrM;Ek52`XK`^i^@'
    '^A^vtHbYoP-&|Yb*3kux+ax<0{zKg7w~Y(`ap~XvqLeqclAE<Yq51p7J@}(9^7l&4Y&M2;fARTEjJoF<M0TTO08MU|j3Ot$UM_Cw'
    'WVhxvY2!9**nI`@ha=q}j`;q3`o~+ITNXy?mmPGwdv6=>T+*G>NpAks<ZV8de8UI}miboLp62oF+}-4&=Ub6<KbUh+dVAY{diVXU'
    'Z*PC+-S<nqLwit+hc&Q=G}#yhDe`epANeTPa}8vu7fu}YQz>^_n@>LNN4Zab^l`FB?4V}nCAaL{txX+^-?n&#k6Vs5zy7(il{_;J'
    'H~kQ!Ep_!(1~@@nuo7IJ!VRDMy|XJDmL!Pe#<d7hg%@59-7<SI{+U~V?D4HdYaCDvgT3%TTHkz2A~>5U=ilb^i&;_7>CbmS;&rLo'
    'F8BAB_a)nJppx7R606%(*6*_#V!U>Rr^!r^W+N&}7jw~eb^qSfN;Z_O@%O*|g17(b<Kh--^74L7qjl2y&Gl>;b&Yn)mc|>zphz?E'
    'Xo?fJ&6Hyt&llMQWTL!pZ-}kYj&nioJNm0vd|I|_X?X4ISD5NJ?GT&ck7j41A<X<@6O``F_{{9Iga<b}G0E7&@3wwY8GJb#<d)Je'
    'evu1uw;tQ3vm9>Fv14BvHplj`3wCWXug%AoyWf^5WeU-zCWC#(WG463&I6sbNxpqhOXd(EURAQAm5)|6A98bL-t0ZHY1p#mPaku('
    '`pj(P6n?{Vf~aCt+6ESut*ay2y8G<p|FYaOP<f_MOO4|flxx|gf0}5EV{I<nawB^_`IcSsLLx2<<bSY`YrHBR$mSa>8F}*`*y#oD'
    'g&*6Z;aha!8VumzoOw8+hj!;zEuN(bY4T-ZHk!$=@EU%yH0CXtkj>}b{w*>#?m0YzGB)?@AK~L4ZD}QE3**crZR1G)910;0Hc<)r'
    ';ksgY-T@a@e9JS<?H3$!gZ)_;Zr&1YG3pkwx9}=)r*7E-p}x6q)A&NI?}y#qFsv7p34e-H^gIWG3O!5Wxp~rZSK7*cQOGVQ`Q#?A'
    '^bC#iVgFDiD4&p~Zt>G{@4jT#6KRVqw9DD-d%Op}*!*={{=Q)GWEu2=;;}1e-8I!P`t26X|MTieYPX<gn@1ZOLQG8}OD!WsO(G1%'
    'p((b|sJA!Q-5y|Qt+ty^Lh)UiJT}qq;fGDNd&8}sN5AJUdI1d|uK8PWVzTjkf!&}#qFN3gB#;hQyqmc%+3zsnaq>glr^#&mHoeH!'
    '65;O`oSSfcoFv?%QtsV+9~Jh0JWUuY<VI5kfWy0`*)cBO?fI<N+*KMrmauI1Er!|#Hh-JuN4Lq@=<a0>!GB^~+mk5+mBDA+YfGuE'
    'q!j9woIuFm@wrcbs<FcpOFpVE^7s5Ix7pJ$SwrN`X0BP%w=k-3ds|2u32_=4H{SD2OtXi!jLkjE6fF+#na82IEu4$(6(%;^`YRK;'
    '6`sww2H4##Vs=F#=fjWtax=}H*CGvJzJCXu=@6FZ-b3-^$9z+w{{6FoXt(n2d1LQ|B7R>Kplx~N+gE?)QTwCX)2Ed3u|j`?&5WRD'
    '%zE}_3Ft8oYkdCq3gg)Pz4)N^^ckgSIsFe_nCE+e=U<psLP~qR8MHyR^b5RrlIJS`G1IS#$ic7vgzNwaW=l;5UD{K|=R12KNC@d{'
    'Z;JU$r>IrnKUmTM^(y~C>4tYq6-Ps&X|k!=)z7DgvrD24fs!J)bh#K<U|$KIRfM@c3n38m_8Glt>%@Kh&0jZj|L4!!Z;~g^z5@KT'
    '@Fh6Y3m@(6@54Yl`fLb}XnCHrdw@|6w7?AvG{*;YY?7`IrGdrIlaj2zcy|5&&#nJ!(@_+6RjMIk@s`7}@RkFh{LO2K)+5W`JdQ5j'
    '7t$iVYm3Z(;ZVfw{x_4zZyuv>Jb)iJN}Se%C|<saLtC7%^lTT7bm1hoKEU~N`!^QRNJiG=iAgE)!0VYVNU(8*kVh<RZWi)LpY=S^'
    'j`;f*2y}#N{#F7V*?7LlCLqf{B(T+he~-AEfVqrnzGe6$U8eA2;j<9;P9NPQd{X?m53Dgc>6re1LxenR5k131MDE!?(#Ner<Arhh'
    'q{U%2^|)VPaJ*l`kof8Ij>y;UMbf%2I&*qP<1qR03ndi_gHLVB7d$)h(&v%%KBS&X@5|}l-2&x}4-xmseewKaFuANm1Vm<55A}Bc'
    'ZYVLAhk8xkxNOQ<P#?F_NA~TDD4yh|o5+?zf*2$&%}wE0$JNmUG@2H;1QPZpKS&#HxBOZyw3~dLwa9MrWkw!v3UF|Dv(aTuH(P%@'
    ')IZSI-{fn^g`|B#(X0=c@;o0wlb>Lf5GESzFZT{~4|X?w(O90?A#s$S>#rIXzbN*(QPP!sB~@&>&6Wz|Y;936G!$?a>5}J9P;x<l'
    'hW)xF6zBQkp~)?O^hNeZL8$zHtzA)X6EO__D+e$1#5lS)RPB(En8e%A;B8E&i593d+NswGM%DjL>^O<-B-dQmr|RyK_)B6Zj_tU1'
    'q2wSn>q(%tygp9bw?k`pVR)UOZE)kSg3MW84zG|2HNd=*hA%$4@#nW7kDCDAs+j`zxQ{G|@d70}<s`YbLH@;fcx|?zCzkQBB#1HP'
    'D}_YND(LZKpJ+70J<y|uk~R2h7ar6w;&LU>M@yNq4q^q3-o6cS5MMtXH~)&b4I<e7QlN1al>#VMSEHd1atfAnekZUst)9@sB&AWf'
    'o3Khb4>3H_y@b|0`!55FjZ?b%*v|r*fThXx0{i9}Frb4Qb40t_rYZN@=K*6tOSW0Y*Z249KbV(bRsCB&xPio<oAcRiN^gR@LB1Xz'
    'V18@thG^Ut2hq7Ml4FII)3C8sJ8E(dro5epAbnbP$4#*kZN*A{ZE?;06U|>(?95=Z{6*C+swsPV-?B*_J*Bn{oYRN3p;K+wpk6t4'
    '74o3mh8djDk!f|&2DFR^!-i$J(N4E5c3Tcy?o$ZehO#rTH@thdEZWf;<D`NkH?m0k8Qv^Z@${K_V3W{ThR@Fl$$Dn=U(|tY3?L8W'
    'O9cHnyAGT+?3?AvbQ1Cn<bwUu>RfYB0X-ZKXe%;3Q0LfEAwSVcPd4DM3}iAS6dm)DdWt{s(e!(*Q2<DsM(I0wzcc;Qk$SmqVk?ni'
    '$-W&Q;aAja9r4FV=MUloQb^sGELo?mf#c+};ce#agrlK)Svd_#YOV;Nl9g7Z=<pu9vLPOY+EI!5fx_3f75q)xwgQf1gi@X0r@nSL'
    'n+s=ds`8?Z^Oc++Xd?@P!}We?L0_&1gK-;Z`n3mgv6H0^>2fb~wV3434)HJ58Dksv^Bn<-y|r1Zabo8y+5HN3KsJ77`4VOWgoIih'
    'Gcj-1{K*@9LbPe$sZ2o5{6kr8DrHmN575u-l?9fV%odq>71)B<i1#{n<`0!UWKSN;Elp@1aFE8HyL=;&g}FM^2VU~zJ#dW|;7`k)'
    '*HV)VR_Eg{M?+1L$cAW+0nbF>lz@G+r69|OG{GXg1No4a%mo+Gl5{C01a$Pkgi&D2EbXU?81qqD1FhIT66V{%lMt0s<`8mFIsGxp'
    '=mmBGDr3G=8zVdw8l*Fj^wR5-?txYsRC+giL15sR>rUX+be47|_T(H<v)xCwB{rn;&cpEC2YrPhxEyWF1j`f_B?;TdM7W_UU_Igr'
    'i<_PW<kbQV<F0~KX&XBG2bIS=g5Pp*o_KLs7W{GV1hQbxF!^ON>}tE=(UdSPW_BRAW&>%Qd#v6-kXr};={zy&+8QLa{r2*4`{T{K'
    ';AL3+g{zd+<m$^M;5oC6K=RLz3sYx-Z_V8FP%;zG1;jvFF$HJ^05E&#tlF76d+t6<hl%0LM+ZC?&>j;_C!RrzHg>$O%LwWSodSw7'
    'WG*I|AC~3HsLej1YDM9fVfud?L7(7U8<8Xgm^u|KaW0K&^I`Mz5dt1R<Cn>NVY9;;L20{gzW&~IHLu#-&F5y6Y#mUe4I~uUm3i44'
    'Zg>q3fTcxNvvuK{Axcf)4>ZzGY92zCj{g9$11czXrcQ$-XE_I1%=Gm@<QX)MFEN}%f3;yFX7oU8FR!n!u7Lxgl(cWs9G%lZxf(82'
    '?!4NeAKHVj_hH%)W?wg2n5T9kA@xWHAyi#wSK+RMdF?uX1nZxm?@Rc%cbIR}%FF$KU?TI+'
)
# END EMBEDDED CONTRACT BUNDLE


@lru_cache(maxsize=1)
def _resource_files() -> dict[str, str]:
    if not RESOURCE_BUNDLE_B85:
        raise RuntimeError("Embedded product Skill contract bundle is empty")
    try:
        packed = base64.b85decode(RESOURCE_BUNDLE_B85.encode("ascii"))
        value = json.loads(zlib.decompress(packed).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, zlib.error) as exc:
        raise RuntimeError(f"Embedded product Skill contract bundle is invalid: {exc}") from exc
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(content, str)
        for key, content in value.items()
    ):
        raise RuntimeError("Embedded product Skill contract bundle must be a text mapping")
    return value


def _safe_read(relative: str) -> str:
    normalized = Path(relative).as_posix().lstrip("/")
    if normalized.startswith("../") or "/../" in normalized or normalized in {".", ".."}:
        raise ValueError(f"Resource path escapes the embedded Skill root: {relative}")
    try:
        return _resource_files()[normalized]
    except KeyError as exc:
        raise FileNotFoundError(f"Embedded Skill resource not found: {normalized}") from exc


def _digest(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_safe_read(relative).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def validate_product_execution_plan(value: dict[str, Any]) -> dict[str, Any]:
    """Validate a plan while authorizing exactly one stage for this Workflow session."""

    if not isinstance(value, dict):
        return {"valid": False, "errors": ["execution plan must be an object"]}
    requested = value.get("stage_chain") or value.get("requested_stages") or []
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        return {"valid": False, "errors": ["stage_chain must be an array"]}
    stages = [str(item or "").strip().lower() for item in requested]
    errors: list[str] = []
    selected = str(value.get("selected_stage") or (stages[0] if stages else "")).strip().lower()
    if not selected:
        errors.append("selected_stage is required")
    if selected and selected not in STAGE_SKILLS:
        errors.append(f"unsupported selected_stage: {selected}")
    unknown = [stage for stage in stages if stage not in STAGE_SKILLS]
    if unknown:
        errors.append("unsupported stages: " + ", ".join(unknown))
    if len(stages) != len(set(stages)):
        errors.append("stage_chain must not contain duplicate stages")
    known = [stage for stage in stages if stage in STAGE_SKILLS]
    positions = [STAGE_ORDER.index(stage) for stage in known]
    if positions != sorted(positions):
        errors.append("stage_chain must follow the canonical forward stage order")
    invalid_relays = [
        f"{current}->{following}"
        for current, following in zip(known, known[1:])
        if following not in STAGE_RELAYS[current]
    ]
    if invalid_relays:
        errors.append("unsupported stage relay: " + ", ".join(invalid_relays))
    if stages and selected and stages[0] != selected:
        errors.append("selected_stage must be the first planned stage")
    if len(stages) > 1 and value.get("stage_chain_authorized") is not True:
        errors.append("multi-stage plans require explicit stage_chain_authorized=true")
    if errors:
        return {"valid": False, "errors": errors}
    normalized = dict(value)
    normalized.update({
        "selected_stage": selected,
        "stage_chain": stages,
        "planned_stage_chain": stages or [selected],
        "execution_scope": [selected],
        "execution_mode": "single-stage",
        "stage_cursor": 0,
    })
    return {
        "valid": True,
        "errors": [],
        "execution_plan": normalized,
    }


def _normalize_stage(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace("_", "-")
    return next((key for key, aliases in STAGE_ALIASES.items() if value in aliases), value)


def _runtime_json_value(value: Any) -> Any:
    """Decode a trusted Workflow value/path without exposing it to the Router model."""

    current = value
    for _ in range(5):
        if isinstance(current, dict):
            nested = next((
                current[key] for key in ("data", "value", "text", "path") if key in current
            ), current)
            if nested is current:
                return current
            current = nested
            continue
        if isinstance(current, list):
            return current
        text = str(current or "").strip()
        if not text:
            return None
        if "\n" not in text and len(text) < 4096:
            try:
                candidate = Path(text).expanduser()
                if candidate.is_file():
                    current = candidate.read_text(encoding="utf-8")
                    continue
            except OSError:
                pass
        try:
            current = json.loads(text)
        except json.JSONDecodeError:
            return text
    return current


def _stage_intent_text(raw: Any) -> str:
    """Remove the selected-Workflow launcher paragraph from route intent.

    The desktop product inserts a short capability introduction before the
    user's business request.  That copy names every product stage and must not
    be treated as the user's stage choice.  Preserve the full value everywhere
    else; only stage-command extraction reads the business-request paragraph.
    """

    text = str(raw or "").strip()
    envelope = re.match(
        r"^(?:original workflow request|original request)\s*:\s*|"
        r"^(?:原始需求|原始请求)\s*[：:]\s*",
        text,
        flags=re.IGNORECASE,
    )
    if envelope:
        text = text[envelope.end():].lstrip()

    # The launcher may be separated from the real request by either one line
    # break or a blank line. Check the shortest prefix first, then the first
    # paragraph, so both desktop templates remain compatible.
    boundaries = [match.end() for match in re.finditer(r"\n", text)]
    for boundary in boundaries:
        launcher_text = text[:boundary].strip()
        launcher = re.sub(r"\s+", " ", launcher_text).lower()
        if (
            "产品方案交付" in launcher
            and "完整能力" in launcher
            and "功能包括" in launcher
        ):
            return text[boundary:].strip()
        # Once a non-launcher paragraph is complete, it is the business brief.
        if text[boundary - 1:boundary + 1] == "\n\n":
            break
    return text


def _explicit_stage_from_text(raw: Any, *, strong_only: bool = False) -> str:
    """Extract only a clearly commanded stage, never a merely mentioned artifact."""

    text = re.sub(r"\s+", " ", _stage_intent_text(raw).lower())
    if not text:
        return ""
    candidates: list[tuple[int, int, str]] = []
    prefix_control = re.compile(
        r"(?:直接从|必须进入|明确进入|切换到|切换至|选择|进入|转到|从|先做|先分析|"
        r"只做|本轮(?:执行|进入)?|当前(?:阶段|入口)(?:是|为)?|作为入口|开始(?:做|写)?|"
        r"请(?:执行|生成|编写|制作|做|给我)?|我要|我想要|希望|需要|给我|编写|写|生成|制作|做)"
        r"[^，。；;！？!?\n]{0,28}$"
    )
    suffix_control = re.compile(r"^(?:阶段)?(?:开始|作为入口|执行|产物|文档|报告|方案)")
    negative = re.compile(r"(?:不|不要|无需|不用|跳过|并非|不是)[^，。；;！？!?\n]{0,8}$")
    for stage, aliases in STAGE_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            pattern = re.compile(
                rf"(?<![0-9a-z]){re.escape(alias.lower())}(?![0-9a-z])"
                if alias.isascii() else re.escape(alias.lower())
            )
            for match in pattern.finditer(text):
                before = text[max(0, match.start() - 48):match.start()]
                after = text[match.end():match.end() + 16]
                if negative.search(before):
                    continue
                prefix = prefix_control.search(before)
                suffix = suffix_control.search(after)
                if not prefix and not suffix:
                    continue
                score = 3 if re.search(r"(?:直接|必须|明确|只做)", before) else 2
                if strong_only and score < 3:
                    continue
                candidates.append((-score, match.start(), stage))
    return min(candidates)[2] if candidates else ""


def _effective_explicit_stage(requested_stage: Any, product_goal: Any) -> tuple[str, str]:
    params: dict[str, Any] = {}
    try:
        current = require_context()
        if isinstance(getattr(current, "params", None), dict):
            params = current.params
    except RuntimeError:
        pass
    # A direct command in the current user message is newer and more explicit
    # than a prefilled or stale stage binding carried into the same run.
    direct_runtime_stage = _explicit_stage_from_text(
        params.get("user_input"), strong_only=True,
    )
    if direct_runtime_stage:
        return direct_runtime_stage, "original runtime request"
    requested = _normalize_stage(requested_stage)
    if requested in STAGE_SKILLS:
        return requested, "requested_stage"
    remote = params.get("remote_inputs") or {}
    if isinstance(remote, dict):
        approval = _runtime_json_value(remote.get("stage_approval"))
        if isinstance(approval, dict):
            approved = _normalize_stage(approval.get("selected_stage") or approval.get("stage"))
            if approved in STAGE_SKILLS:
                return approved, "stage_approval"
    runtime_stage = _explicit_stage_from_text(params.get("user_input"))
    if runtime_stage:
        return runtime_stage, "original runtime request"
    goal_stage = _explicit_stage_from_text(product_goal)
    return (goal_stage, "product_goal") if goal_stage else ("", "")


def _should_default_initial_direction() -> bool:
    """Return true only for a clean post-clarification project entrance.

    Ask-user answers establish the project goal, but they do not authorize skipping product
    direction. Existing project state, an approval event, or a bound business artifact keeps the
    normal Router active so users can resume or enter any explicitly selected stage.
    """

    try:
        params = getattr(require_context(), "params", {}) or {}
    except RuntimeError:
        params = {}
    remote = params.get("remote_inputs") or {}
    if not isinstance(remote, dict):
        return True
    for slot in ("workspace_seed", "stage_approval"):
        value = _runtime_json_value(remote.get(slot))
        if value not in (None, "", [], {}):
            return False
    material_slots = (
        "product_materials", "reference_sample",
        "upstream_direction", "upstream_competitive", "upstream_design",
        "upstream_prd", "upstream_prototype", "upstream_review", "upstream_handoff",
    )
    return not any(
        _bound_artifact_descriptor(remote.get(slot))["present"]
        for slot in material_slots
    )


def _normalize_route_source(raw: Any) -> str:
    value = re.sub(r"[\s_-]+", " ", str(raw or "").strip().lower())
    if value in {"explicit", "deterministic", "model", "fallback"}:
        return value
    if "explicit" in value or "user selection" in value or "显式" in value:
        return "explicit"
    if "deterministic" in value or "rule" in value or "规则" in value:
        return "deterministic"
    if "model" in value or "recommend" in value or "模型" in value:
        return "model"
    if "fallback" in value or "回退" in value:
        return "fallback"
    return value


def _normalize_route_alternatives(value: Any, selected: str) -> list[Any]:
    raw = value if isinstance(value, list) else _parse_stage_chain(value) if value else []
    normalized: list[Any] = []
    seen = {selected}
    for alternative in raw:
        item = dict(alternative) if isinstance(alternative, dict) else alternative
        stage = _normalize_stage(
            item.get("stage") or item.get("stage_id") if isinstance(item, dict) else item
        )
        if stage not in STAGE_SKILLS or stage in seen:
            continue
        seen.add(stage)
        if isinstance(item, dict):
            item["stage"] = stage
            item.pop("stage_id", None)
            normalized.append(item)
        else:
            normalized.append(stage)
        if len(normalized) == 2:
            break
    return normalized


def _normalize_route_chain(value: Any, selected: str, authorized: bool) -> list[str]:
    raw = _parse_stage_chain(value) if isinstance(value, str) else value or []
    if not isinstance(raw, list) or not authorized:
        return []
    stages: list[str] = []
    for item in raw:
        stage = _normalize_stage(item)
        if stage in STAGE_SKILLS and stage not in stages:
            stages.append(stage)
    if selected in stages:
        stages = stages[stages.index(selected):]
    elif stages:
        stages.insert(0, selected)
    else:
        return []
    valid = [selected]
    for following in stages[1:]:
        if following not in STAGE_RELAYS[valid[-1]]:
            break
        valid.append(following)
    return valid if len(valid) > 1 else []


def _normalize_execution_depth(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "auto": "auto", "由当前阶段判断": "auto", "自动判断": "auto",
        "light": "light", "轻量": "light", "轻量模式": "light", "精简": "light",
        "复用现有": "light", "minimum-fill": "minimum-fill", "最小补齐": "minimum-fill",
        "最小补齐模式": "minimum-fill", "补齐": "minimum-fill", "full": "full",
        "完整": "full", "完整模式": "full", "完整执行": "full",
    }
    normalized = aliases.get(value)
    if not normalized:
        raise ValueError("execution_depth must be auto, light, minimum-fill, or full")
    return normalized


def _normalize_reference_sample(raw: Any, *, text_stage: bool) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "provided": "provided", "已提供": "provided", "有样例": "provided",
        "none-confirmed": "none-confirmed", "无样例": "none-confirmed",
        "默认结构": "none-confirmed", "使用默认结构": "none-confirmed",
        "不使用参考样例": "none-confirmed", "不提供参考样例": "none-confirmed",
        "不使用样例": "none-confirmed", "not-required": "not-required",
        "不需要": "not-required", "不适用": "not-required",
    }
    status = aliases.get(value)
    if status is None:
        raise ValueError("reference_sample_choice must be provided, none-confirmed, or not-required")
    if text_stage and status not in {"provided", "none-confirmed"}:
        raise ValueError(
            "reference_sample_choice must be provided or none-confirmed for text stages"
        )
    return status or "not-required"


def _normalize_word_target(raw: Any, *, text_stage: bool) -> int | None:
    value = str(raw or "").replace(",", "").strip().lower()
    match = re.search(r"\d+", value)
    if text_stage and not match:
        raise ValueError("word_target is required when the selected stage produces text")
    target = int(match.group()) if match else None
    if text_stage and target is not None and target < 300:
        raise ValueError("word_target must be at least 300 Chinese characters")
    return target


def validate_product_route(
    value: dict[str, Any],
    product_goal: str,
    execution_depth: str = "",
    word_target: str = "",
    reference_sample_choice: str = "",
    requested_stage: str = "",
) -> dict[str, Any]:
    """Normalize and validate one parent Router record.

    ``route_source`` is published as exactly explicit/deterministic/model/fallback and
    ``alternatives`` contains at most two canonical stages. The Host always restores a clearly
    explicit stage from ``requested_stage``, ``stage_approval`` or the original runtime request.
    """

    if not isinstance(value, dict):
        raise ValueError("routing record must be an object")
    if "selected_stage" not in value and isinstance(value.get("routing_record"), dict):
        # Some small models mirror the public result envelope inside the
        # schema's ``value`` argument. Accept that harmless wrapper so the
        # user's full stage chain is not dropped during normalization.
        value = dict(value["routing_record"])
    # The immutable user choice outranks model wording. Recover it before
    # validating the model field so a non-canonical alias such as
    # ``product_scheme`` cannot reject an otherwise explicit design route.
    explicit_request, explicit_origin = _effective_explicit_stage(requested_stage, product_goal)
    initial_direction_default = not explicit_request and _should_default_initial_direction()
    selected = explicit_request or (
        "direction" if initial_direction_default else _normalize_stage(value.get("selected_stage"))
    )
    if selected not in STAGE_SKILLS:
        raise ValueError(f"Unsupported selected_stage: {selected or '<empty>'}")

    source = _normalize_route_source(value.get("route_source"))
    if explicit_request:
        source = "explicit"
    elif initial_direction_default:
        source = "deterministic"
    if source not in {"explicit", "deterministic", "model", "fallback"}:
        raise ValueError("route_source must be explicit, deterministic, model, or fallback")
    confidence = str(value.get("confidence") or "").strip().lower()
    if explicit_request:
        confidence = "explicit"
    elif initial_direction_default:
        confidence = "high"
    elif source == "deterministic":
        confidence = "high"
    elif confidence not in {"explicit", "high", "low"} and source in {"model", "fallback"}:
        confidence = "low"
    if confidence not in {"explicit", "high", "low"}:
        raise ValueError("confidence must be explicit, high, or low")
    if source == "explicit" and confidence != "explicit":
        raise ValueError("an explicit route must use confidence=explicit")
    if source == "deterministic" and confidence != "high":
        raise ValueError("a deterministic route must use confidence=high")
    origin_labels = {
        "requested_stage": "已绑定的阶段选择",
        "stage_approval": "人工阶段确认",
        "original runtime request": "用户原始请求",
        "product_goal": "产品目标",
    }
    reason = (
        f"系统已根据{origin_labels.get(explicit_origin, '用户输入')}保留用户明确选择的"
        f"「{STAGE_DISPLAY_LABELS.get(selected, selected)}」阶段。"
        if explicit_request else
        "首次进入项目且尚未指定阶段，先明确产品方向；方向确认后再进入竞品与生态位。"
        if initial_direction_default else str(value.get("route_reason") or "").strip()
    )
    if not reason:
        raise ValueError("route_reason is required")

    normalized_alternatives = (
        [] if explicit_request or initial_direction_default
        else _normalize_route_alternatives(value.get("alternatives"), selected)
    )
    chain = _normalize_route_chain(
        [] if initial_direction_default else value.get("stage_chain"), selected,
        False if initial_direction_default else value.get("stage_chain_authorized") is True,
    )
    plan_result = validate_product_execution_plan({
        "selected_stage": selected,
        "stage_chain": chain,
        "stage_chain_authorized": bool(len(chain) > 1),
    })
    if not plan_result["valid"]:
        raise ValueError("; ".join(plan_result["errors"]))

    goal = str(product_goal or "").strip()
    if not goal:
        raise ValueError("product_goal is required before starting the Workflow")
    defaults = {"direction": 1400, "design": 3500, "prd": 4500, "review": 1800, "handoff": 3500}
    blank_depth = execution_depth is None or not str(execution_depth).strip()
    blank_target = word_target is None or not str(word_target).strip()
    blank_sample = reference_sample_choice is None or not str(reference_sample_choice).strip()
    depth = _normalize_execution_depth("auto" if blank_depth else execution_depth)
    text_stage = selected in TEXT_STAGES
    target = _normalize_word_target(
        defaults.get(selected) if text_stage and blank_target else word_target, text_stage=text_stage,
    ) if text_stage else None
    remote = getattr(require_context(), "params", {}).get("remote_inputs") or {}
    has_sample = _bound_artifact_descriptor(remote.get("reference_sample"))["present"] if isinstance(remote, dict) else False
    sample_choice = reference_sample_choice
    if blank_sample:
        sample_choice = "provided" if text_stage and has_sample else "none-confirmed" if text_stage else "not-required"
    sample_status = _normalize_reference_sample(
        sample_choice, text_stage=text_stage,
    )
    if not text_stage:
        sample_status = "not-required"

    routing_record = dict(value)
    routing_record.update({
        "selected_stage": selected,
        "route_source": source,
        "route_reason": reason,
        "confidence": confidence,
        "alternatives": normalized_alternatives,
        "stage_chain": chain,
        "stage_chain_authorized": bool(len(chain) > 1),
    })
    execution_plan = dict(plan_result["execution_plan"])
    execution_plan.update({
        "product_goal": goal,
        "execution_depth": depth,
        "word_target": target,
        "reference_sample_status": sample_status,
        "preference_sources": {
            "execution_depth": "project-default" if blank_depth else "explicit-input",
            "word_target": ("not-applicable" if not text_stage else
                            "project-default" if blank_target else "explicit-input"),
            "reference_sample": ("not-required" if not text_stage else "bound-reference-sample" if blank_sample and has_sample else
                                 "project-default" if blank_sample else "explicit-input"),
        },
        "default_policy": "Reuse project inputs and stage defaults without additional setup; defaults are not fabricated user confirmations.",
    })
    planned = " → ".join(
        STAGE_DISPLAY_LABELS.get(item, item)
        for item in execution_plan["planned_stage_chain"]
    )
    stage_label = STAGE_DISPLAY_LABELS.get(selected, selected)
    stage_outcome = STAGE_USER_OUTCOMES.get(selected, "这一阶段需要确认的结果")
    if source == "explicit":
        selection_note = "已根据你的要求，从这里开始。"
    elif initial_direction_default:
        selection_note = "已完成初始信息确认，先从产品方向开始。"
    elif confidence == "low":
        selection_note = "根据目前的信息，建议从这里开始；如果与你的预期不一致，可以调整。"
    else:
        selection_note = "根据你描述的目标，从这里开始最合适。"
    if initial_direction_default:
        continuation_note = "本阶段完成后会先停下来；你确认继续后，再进入竞品与生态位。"
    elif len(execution_plan["planned_stage_chain"]) > 1:
        continuation_note = (
            f"接下来计划：{planned}。每一步完成后都会停下来，请你确认是否继续。"
        )
    else:
        continuation_note = "完成后会停下来，请你确认是否继续。"
    summary = (
        f"## {stage_label}\n\n{selection_note}\n\n"
        f"**本阶段会明确**\n\n{stage_outcome}\n\n{continuation_note}"
    )
    hide_flags = {
        f"hide_{stage}": f"本轮父 Router 选择了 {selected}，不展示 {stage} 阶段。"
        for stage in STAGE_ORDER if stage != selected
    }
    return {
        "routing_record": routing_record,
        "execution_plan": execution_plan,
        "routing_summary": summary,
        "ui_hide_flags": hide_flags,
        **hide_flags,
    }


def _router_profile_summary(resource_profiles_path: str) -> tuple[str, str, str]:
    context = require_context()
    workspace = Path(str(getattr(context, "workspace_path", "") or "")).resolve()
    path = Path(str(resource_profiles_path or "")).expanduser().resolve(strict=True)
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("resource_profiles_path must stay inside the active Workflow workspace") from exc
    parsed = json.loads(path.read_text(encoding="utf-8"))
    profiles = parsed if isinstance(parsed, list) else []
    lines: list[str] = []
    display_names: list[str] = []
    for index, profile in enumerate(profiles[:12], 1):
        if not isinstance(profile, dict):
            lines.append(f"- 材料 {index}：{str(profile)[:320]}")
            display_names.append(f"资料 {index}")
            continue
        name = next((
            str(profile.get(key) or "").strip()
            for key in ("filename", "name", "title", "resource_name", "id")
            if str(profile.get(key) or "").strip()
        ), f"材料 {index}")
        detail = next((
            profile.get(key) for key in (
                "summary", "description", "content_summary", "key_points", "facts", "outline",
            ) if profile.get(key) not in (None, "", [])
        ), "已完成资料画像；未明确的信息保持未知。")
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False, default=str)
        lines.append(f"- **{name}**：{detail[:600]}")
        if name == f"材料 {index}":
            kind = next((
                label for keyword, label in (
                    ("评审", "方案评审"), ("原型", "交互原型"),
                    ("PRD", "需求文档"), ("产品方案", "产品方案"),
                    ("产品方向", "产品方向"), ("竞品", "竞品资料"),
                ) if keyword in detail
            ), f"资料 {index}")
            display_names.append(kind)
        else:
            display_names.append(name)
    inherited = (
        "\n".join(lines)
        if lines else "- 本次没有绑定可读取的产品材料；后续阶段只能基于产品目标并标注事实缺口。"
    )
    if display_names:
        visible_materials = (
            "- 你的产品目标\n"
            + "\n".join(f"- {name}" for name in display_names)
        )
        context_note = "这些资料会直接沿用；需要你确认的内容会单独标出。"
    else:
        visible_materials = "- 你的产品目标"
        context_note = "暂未附加其他资料，可以先继续；需要补充或验证的内容会在方案中标出。"
    evidence = (
        "## 已收到的内容\n\n"
        f"{visible_materials}\n\n{context_note}"
    )
    digest = "## 输入材料摘要\n\n" + inherited
    research_log = (
        "## 资料检索记录\n\n"
        "父 Router 未执行外部检索。需要的公开证据将在选定业务阶段内按其证据规则获取。"
    )
    return evidence, digest, research_log


_ROUTER_FILE_MATERIAL_SLOTS = {
    "product_materials", "reference_sample", "upstream_direction", "upstream_competitive",
    "upstream_design", "upstream_prd", "upstream_prototype", "upstream_review",
    "upstream_handoff",
}


def _resolved_router_profiles_path(resource_profiles_path: str, remote_inputs: Any) -> str:
    """Accept a real profiler output, or create an honest empty inventory when no files exist."""

    context = require_context()
    workspace_value = str(getattr(context, "workspace_path", "") or "").strip()
    if not workspace_value:
        raise ValueError("active Workflow workspace is required for resource profiles")
    workspace = Path(workspace_value).resolve()

    def valid_profiles(path: Path) -> bool:
        try:
            path.relative_to(workspace)
            return isinstance(json.loads(path.read_text(encoding="utf-8")), list)
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    candidate = str(resource_profiles_path or "").strip()
    if candidate and not candidate.startswith("embedded:"):
        try:
            path = Path(candidate).expanduser().resolve(strict=True)
            if valid_profiles(path):
                return str(path)
        except (OSError, ValueError):
            pass

    # Recover only this product profiler's actual output. A broad workspace scan
    # could pick a later Writer profile from an unrelated stage or requirement.
    recovered: list[Path] = []
    try:
        recovered = sorted(
            (path.resolve() for path in workspace.glob("product-writer/resource-profiles-*/resource_profiles.json")
             if path.is_file() and valid_profiles(path.resolve())),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    except OSError:
        recovered = []
    if recovered:
        return str(recovered[0])

    bound_files = []
    if isinstance(remote_inputs, dict):
        bound_files = [
            slot for slot in _ROUTER_FILE_MATERIAL_SLOTS
            if _bound_artifact_descriptor(remote_inputs.get(slot))["present"]
        ]
    if bound_files:
        raise ValueError(
            "profile_product_materials must run for the bound file slots: "
            + ", ".join(sorted(bound_files))
        )
    path = workspace / "router-empty-resource-profiles.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]\n", encoding="utf-8")
    return str(path)


def publish_product_route(
    value: dict[str, Any],
    product_goal: str = "",
    resource_profiles_path: str = "",
    execution_depth: str = "",
    word_target: str = "",
    reference_sample_choice: str = "",
    requested_stage: str = "",
) -> dict[str, Any]:
    """Validate and atomically publish the parent Router outputs, then end the Router step.

    Use the exact ``resource_profiles`` path returned by ``profile_product_materials``. Common
    model wording drift is normalized, while an explicit user stage is restored by the Host.
    """

    # During Workflow execution, only material bindings supplied by the Host are
    # authoritative. Small models sometimes invent placeholder strings such as
    # ``stage-specific``, ``default`` or ``由 Router 判断`` for optional scalar
    # inputs. Treating those placeholders as user choices makes otherwise valid
    # defaulted runs fail (for example, ``stage-specific`` has no numeric word
    # target). Ignore every unbound optional scalar here; explicit stage intent is
    # still recovered from the immutable original runtime request below.
    try:
        remote_inputs = (require_context().params or {}).get("remote_inputs") or {}
    except RuntimeError:
        remote_inputs = {}
    if isinstance(remote_inputs, dict) and "product_goal" in remote_inputs:
        product_goal = _runtime_json_value(remote_inputs.get("product_goal")) or ""
        execution_depth = _runtime_json_value(remote_inputs.get("execution_depth")) \
            if "execution_depth" in remote_inputs else ""
        word_target = _runtime_json_value(remote_inputs.get("word_target")) \
            if "word_target" in remote_inputs else ""
        reference_sample_choice = _runtime_json_value(remote_inputs.get("reference_sample_choice")) \
            if "reference_sample_choice" in remote_inputs else ""
        requested_stage = _runtime_json_value(remote_inputs.get("requested_stage")) \
            if "requested_stage" in remote_inputs else ""

    route = validate_product_route(
        value,
        product_goal,
        execution_depth,
        word_target,
        reference_sample_choice,
        requested_stage,
    )
    resource_profiles_path = _resolved_router_profiles_path(
        resource_profiles_path, remote_inputs,
    )
    research_evidence, material_digest, research_log = _router_profile_summary(resource_profiles_path)
    artifacts: list[tuple[str, Any, str]] = [
        ("routing_record", route["routing_record"], "json"),
        ("execution_plan", route["execution_plan"], "json"),
        ("routing_summary", route["routing_summary"], "text"),
        ("research_evidence", research_evidence, "text"),
        ("research_log", research_log, "text"),
        ("material_digest", material_digest, "text"),
        ("resource_profiles", resource_profiles_path, "file"),
    ]
    artifacts.extend(
        (key, content, "text")
        for key, content in route["ui_hide_flags"].items()
    )
    saved: list[str] = []
    for key, content, content_type in artifacts:
        _save_artifact(
            key=key,
            value=content,
            content_type=content_type,
            source_tool="publish_product_route",
            internal_publish=True,
        )
        saved.append(key)
    return {
        "status": "published",
        "selected_stage": route["routing_record"]["selected_stage"],
        "route_source": route["routing_record"]["route_source"],
        "saved_slots": saved,
        "message": "Parent Router outputs were validated and saved; stop this step now.",
    }


def validate_design_route(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the design child Router's six-domain scope and per-decision effort."""

    if not isinstance(value, dict):
        raise ValueError("design routing record must be an object")
    primary = list(dict.fromkeys(value.get("primary_domains") or []))
    linked = list(dict.fromkeys(value.get("linked_domains") or []))
    unknown = [item for item in [*primary, *linked] if item not in DESIGN_DOMAINS]
    if unknown:
        raise ValueError("unsupported design domains: " + ", ".join(unknown))
    if not primary:
        raise ValueError("primary_domains must contain at least one of the six design domains")
    if set(primary) & set(linked):
        raise ValueError("a design domain cannot be both primary and linked")

    decisions = value.get("decisions") or value.get("subdecisions") or []
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("decisions must contain at least one scoped design decision")
    normalized_decisions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(decisions, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"decision {index} must be an object")
        item = dict(raw)
        decision_id = str(item.get("decision_id") or f"DES-{index:03d}").strip()
        if decision_id in seen_ids:
            raise ValueError(f"duplicate decision_id: {decision_id}")
        seen_ids.add(decision_id)
        domain = str(item.get("primary_domain") or "").strip()
        if domain not in primary:
            raise ValueError(f"decision {decision_id} primary_domain must be a primary domain")
        decision_linked = list(dict.fromkeys(item.get("linked_domains") or []))
        invalid_linked = [
            linked_domain for linked_domain in decision_linked
            if linked_domain not in {*primary, *linked} or linked_domain == domain
        ]
        if invalid_linked:
            raise ValueError(
                f"decision {decision_id} has inactive or self-linked domains: "
                + ", ".join(invalid_linked)
            )
        effort = str(item.get("effort") or "").strip().lower()
        if effort not in {"light", "heavy"}:
            raise ValueError(f"decision {decision_id} effort must be light or heavy")
        reasons = item.get("effort_reasons") or []
        if not isinstance(reasons, list) or not reasons:
            raise ValueError(f"decision {decision_id} needs effort_reasons")
        hard_gates = list(dict.fromkeys(item.get("hard_gates") or []))
        invalid_gates = [gate for gate in hard_gates if gate not in DESIGN_HARD_GATES]
        if invalid_gates:
            raise ValueError("unsupported hard gates: " + ", ".join(invalid_gates))
        if hard_gates and effort != "heavy":
            raise ValueError(f"decision {decision_id} has a hard gate and must be heavy")
        item.update({
            "decision_id": decision_id,
            "primary_domain": domain,
            "linked_domains": decision_linked,
            "effort": effort,
            "hard_gates": hard_gates,
        })
        normalized_decisions.append(item)

    overall = "heavy" if any(item["effort"] == "heavy" for item in normalized_decisions) else "light"
    requested_overall = str(value.get("overall_effort") or overall).strip().lower()
    if requested_overall != overall:
        raise ValueError(f"overall_effort must be {overall} for the declared decisions")
    triggers = value.get("escalation_triggers") or []
    if not isinstance(triggers, list) or set(triggers) != DESIGN_ESCALATION_TRIGGERS:
        raise ValueError(
            "escalation_triggers must be sustained_counterexamples, practice_divergence, "
            "and trust_risk"
        )

    normalized = dict(value)
    normalized.update({
        "primary_domains": primary,
        "linked_domains": linked,
        "decisions": normalized_decisions,
        "overall_effort": overall,
        "escalation_triggers": triggers,
    })
    primary_labels = "、".join(DESIGN_DOMAINS[item] for item in primary)
    linked_labels = "、".join(DESIGN_DOMAINS[item] for item in linked) or "无"
    heavy_count = sum(item["effort"] == "heavy" for item in normalized_decisions)
    effort_label = "需要深入核验" if overall == "heavy" else "可直接整理"
    hard_gates = sorted({
        gate for item in normalized_decisions for gate in item["hard_gates"]
    })
    gate_labels = "、".join(DESIGN_HARD_GATE_LABELS[gate] for gate in hard_gates) or "未触发"
    summary = (
        f"## 本阶段需要关注什么\n\n- 重点设计：{primary_labels}\n- 同时需要考虑：{linked_labels}\n"
        f"- 分析方式：{effort_label}\n- 需要确认：{len(normalized_decisions)} 项"
        f"（其中 {heavy_count} 项需要重点核验）\n"
        f"- 需要特别注意：{gate_labels}\n\n"
        "范围已经整理完成。请确认这些重点是否合适，确认后继续完善方案。"
    )
    return {
        "design_routing_record": normalized,
        "design_effort_route": overall,
        "design_routing_summary": summary,
    }


def publish_design_route(value: dict[str, Any]) -> dict[str, Any]:
    """Validate and atomically publish the second-layer Router in deterministic Chinese UI form."""

    route = validate_design_route(value)
    return _publish_design_route(route, source_tool="publish_design_route")


def _publish_design_route(route: dict[str, Any], *, source_tool: str) -> dict[str, Any]:
    """Persist one already-normalized child route as an atomic Host-owned result."""

    for key, content_type in (
        ("design_routing_record", "json"),
        ("design_effort_route", "text"),
        ("design_routing_summary", "text"),
    ):
        _save_artifact(
            key=key,
            value=route[key],
            content_type=content_type,
            source_tool=source_tool,
            internal_publish=True,
        )
    return {
        "status": "published",
        "overall_effort": route["design_effort_route"],
        "saved_slots": [
            "design_routing_record", "design_effort_route", "design_routing_summary",
        ],
        "message": "方案范围和研究路径已使用中文摘要保存；请立即结束当前步骤。",
    }


_DESIGN_DOMAIN_ALIASES = {
    "domain_state": {"domain_state", "domain state", "领域对象", "数据语义", "状态", "数据模型"},
    "behavior_policy_trust": {
        "behavior_policy_trust", "behavior policy trust", "行为规则权限信任", "行为", "规则",
        "权限", "信任", "安全",
    },
    "ia_semantics": {"ia_semantics", "ia semantics", "信息架构", "语义", "导航", "分类"},
    "journey_interaction_service": {
        "journey_interaction_service", "journey interaction service", "用户旅程", "交互",
        "服务流程", "流程",
    },
    "ui_visual_system": {"ui_visual_system", "ui visual system", "界面", "视觉", "设计系统", "ui"},
    "content_communication": {
        "content_communication", "content communication", "内容", "沟通", "文案", "通知",
    },
}
_DESIGN_GATE_ALIASES = {
    "privacy": {"privacy", "隐私", "敏感内容", "敏感数据"},
    "identity": {"identity", "身份", "实名认证", "账号归属"},
    "permission": {"permission", "权限", "授权", "访问控制", "角色控制"},
    "silent_write": {"silent_write", "silent write", "静默写入", "自动写入"},
    "cross_tenant": {"cross_tenant", "cross tenant", "跨租户", "租户隔离"},
    "high_loss_irreversible": {
        "high_loss_irreversible", "high loss irreversible", "高损失且不可逆", "不可逆高损失",
    },
}


def _compact_tokens(raw: Any) -> list[str]:
    """Parse a short comma/pipe separated Router argument without accepting nested JSON."""

    return list(dict.fromkeys(
        token.strip().lower().replace("-", "_")
        for token in re.split(r"\s*(?:,|，|、|\||;|；|\n)\s*", str(raw or ""))
        if token.strip()
    ))


def _canonical_compact_values(raw: Any, aliases: dict[str, set[str]]) -> list[str]:
    result: list[str] = []
    for token in _compact_tokens(raw):
        normalized = token.replace("_", " ")
        match = next((
            canonical for canonical, values in aliases.items()
            if token == canonical or normalized in {value.lower().replace("_", " ") for value in values}
            or token in {value.lower().replace("-", "_") for value in values}
        ), "")
        if match and match not in result:
            result.append(match)
    return result


def _design_product_goal() -> str:
    """Read the immutable project goal inherited from the first Router."""

    try:
        remote_inputs = (require_context().params or {}).get("remote_inputs") or {}
    except RuntimeError:
        return ""
    if not isinstance(remote_inputs, dict):
        return ""
    plan = _runtime_json_value(remote_inputs.get("execution_plan"))
    if isinstance(plan, dict):
        return str(plan.get("product_goal") or "").strip()
    return ""


def _design_stage_request() -> str:
    """Include the latest user-authorized stage change, not just the original project goal."""

    try:
        remote_inputs = (require_context().params or {}).get("remote_inputs") or {}
    except RuntimeError:
        return ""
    if not isinstance(remote_inputs, dict):
        return ""
    approval = _runtime_json_value(remote_inputs.get("stage_approval"))
    if not isinstance(approval, dict):
        return ""
    return str(approval.get("request_context") or "").strip()[:8000]


def _infer_design_domains(text: str) -> list[str]:
    """Conservatively recover a usable scope when a small model omits compact fields."""

    lowered = str(text or "").lower()
    keyword_groups = {
        "domain_state": ("数据", "状态", "对象", "字段", "模型", "schema", "state", "entity"),
        "behavior_policy_trust": (
            "隐私", "身份", "权限", "授权", "角色", "信任", "安全", "租户", "privacy",
            "identity", "permission", "tenant", "policy", "auth",
        ),
        "ia_semantics": ("信息架构", "导航", "分类", "检索", "语义", "taxonomy", "navigation"),
        "journey_interaction_service": (
            "流程", "旅程", "交互", "同步", "操作", "反馈", "workflow", "journey", "interaction",
        ),
        "ui_visual_system": ("界面", "视觉", "布局", "组件", "设计系统", " ui", "visual"),
        "content_communication": ("内容", "文案", "通知", "消息", "沟通", "copy", "content"),
    }
    return [domain for domain, keywords in keyword_groups.items() if any(key in lowered for key in keywords)]


def _infer_design_hard_gates(text: str) -> list[str]:
    lowered = str(text or "").lower()
    return [
        gate for gate, aliases in _DESIGN_GATE_ALIASES.items()
        if any(alias.lower().replace("_", " ") in lowered.replace("_", " ") for alias in aliases)
    ]


def publish_design_route_compact(
    primary_domains: str = "",
    linked_domains: str = "",
    heavy_domains: str = "",
    hard_gates: str = "",
    decision_summary: str = "",
) -> dict[str, Any]:
    """Publish the second Router from five short scalar fields; never pass a nested JSON object.

    Use comma-separated canonical IDs for domain and gate fields. The Host checks the project goal
    and latest stage request, retains explicitly declared risks, and creates decision objects.
    """

    product_goal = _design_product_goal()
    stage_request = _design_stage_request()
    routing_context = "\n".join((product_goal, stage_request))
    short_summary = re.sub(r"\s+", " ", str(decision_summary or "").strip())[:240]
    primary = _canonical_compact_values(primary_domains, _DESIGN_DOMAIN_ALIASES)
    linked = _canonical_compact_values(linked_domains, _DESIGN_DOMAIN_ALIASES)
    heavy = _canonical_compact_values(heavy_domains, _DESIGN_DOMAIN_ALIASES)
    declared_gates = _canonical_compact_values(hard_gates, _DESIGN_GATE_ALIASES)
    supported_gates = _infer_design_hard_gates("\n".join((routing_context, short_summary)))
    # An explicitly declared risk must not be silently downgraded merely because
    # keyword matching misses a paraphrase. The one recognizable copy-the-entire-
    # contract failure is filtered when the request supports a narrower set.
    gates = (supported_gates if len(declared_gates) == len(DESIGN_HARD_GATES) and supported_gates
             else list(dict.fromkeys([*supported_gates, *declared_gates])))

    inferred = _infer_design_domains(routing_context)
    if not primary:
        primary = inferred[:2] or ["journey_interaction_service"]
        linked = list(dict.fromkeys([*linked, *inferred[2:]]))
    elif len(primary) == len(DESIGN_DOMAINS) and inferred and len(inferred) < len(DESIGN_DOMAINS):
        # Selecting all six domains usually means the model copied the option
        # list instead of classifying changed product objects. Preserve a
        # focused three-domain primary scope and keep the remaining supported
        # domains linked.
        primary = inferred[:3]
        linked = list(dict.fromkeys([*inferred[3:], *linked]))
    if gates and "behavior_policy_trust" not in primary:
        primary.insert(0, "behavior_policy_trust")
    linked = [item for item in linked if item not in primary]
    heavy = [item for item in heavy if item in primary]
    if gates and "behavior_policy_trust" not in heavy:
        heavy.append("behavior_policy_trust")

    decisions: list[dict[str, Any]] = []
    active = [*primary, *linked]
    for index, domain in enumerate(primary, 1):
        decision_gates = gates if domain == "behavior_policy_trust" else []
        effort = "heavy" if domain in heavy or decision_gates else "light"
        reason = (
            f"触发不可补偿风险门槛：{'、'.join(DESIGN_HARD_GATE_LABELS[item] for item in decision_gates)}"
            if decision_gates else
            (short_summary or "影响或不确定性需要重型取证")
            if effort == "heavy" else
            "该主责范围当前未触发硬门槛，先按局部、可逆、低成本方式验证"
        )
        decisions.append({
            "decision_id": f"DES-{index:03d}",
            "decision_question": f"{DESIGN_DOMAINS[domain]}应如何满足当前产品目标并保持可验证？",
            "primary_domain": domain,
            "linked_domains": [item for item in active if item != domain],
            "effort": effort,
            "effort_reasons": [reason],
            "hard_gates": decision_gates,
        })

    route = validate_design_route({
        "primary_domains": primary,
        "linked_domains": linked,
        "decisions": decisions,
        "overall_effort": "heavy" if any(item["effort"] == "heavy" for item in decisions) else "light",
        "escalation_triggers": sorted(DESIGN_ESCALATION_TRIGGERS),
        "routing_basis": short_summary,
    })
    return _publish_design_route(route, source_tool="publish_design_route_compact")


def _bounded_evidence_text(value: Any, *, limit: int = 600) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _current_attempt_sources() -> list[dict[str, Any]]:
    """Read sources from the live citation registry, falling back to the task snapshot."""

    sources: Any = []
    try:
        import lazyllm
        from lazymind.chat.service.utils.citations import materialize_source_views

        agentic_config = lazyllm.globals.get("agentic_config") or {}
        citation_state = agentic_config.get("citation_state")
        if isinstance(citation_state, dict):
            sources = materialize_source_views(citation_state)
    except Exception:
        sources = []

    if not sources:
        context = require_context()
        database = getattr(context, "db", None)
        if database is not None and hasattr(database, "load_task"):
            try:
                task = database.load_task(str(getattr(context, "task_id", "") or "")) or {}
                sources = task.get("sources") or []
            except Exception:
                sources = []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for position, source in enumerate(sources if isinstance(sources, list) else [], 1):
        if not isinstance(source, dict):
            continue
        source_id = _bounded_evidence_text(
            source.get("index") or source.get("citation_id") or source.get("source_id")
            or f"SRC-{position:03d}",
            limit=80,
        )
        url = _bounded_evidence_text(source.get("url"), limit=1000)
        identity = (source_id, url)
        if identity in seen:
            continue
        seen.add(identity)
        keys = {
            _bounded_evidence_text(source.get(key), limit=1000)
            for key in ("url", "doi", "doc_id", "document_id")
        }
        keys.discard("")
        if url:
            keys.add(url.rstrip("/"))
        normalized.append({
            "source_id": source_id,
            "title": _bounded_evidence_text(source.get("title") or "未命名来源", limit=160),
            "url": url,
            "keys": keys,
        })
    return normalized


def _resolve_submitted_sources(
    refs: Any,
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    source_by_key: dict[str, dict[str, Any]] = {}
    for source in sources:
        for key in source.get("keys") or []:
            source_by_key[str(key)] = source
    resolved: list[dict[str, Any]] = []
    rejected: list[str] = []
    seen_ids: set[str] = set()
    for raw_ref in refs if isinstance(refs, list) else []:
        ref = _bounded_evidence_text(raw_ref, limit=1000)
        source = source_by_key.get(ref) or source_by_key.get(ref.rstrip("/"))
        if source is None:
            if ref:
                rejected.append(ref)
            continue
        source_id = str(source["source_id"])
        if source_id not in seen_ids:
            seen_ids.add(source_id)
            resolved.append(source)
    return resolved, rejected


def _current_task_source_labels() -> list[str]:
    """Compatibility formatter used only by the legacy conservative renderer below."""

    labels: list[str] = []
    for source in _current_attempt_sources():
        label = f"{source['source_id']} · {source['title']}"
        if source["url"]:
            label += f" · {source['url']}"
        labels.append(label)
    return labels


def _publish_design_heavy_evidence_e0_legacy() -> dict[str, Any]:
    """Publish a fail-closed Chinese E0 packet from the approved design route.

    Call this exactly once after any permitted retrieval. The Host reads the immutable routing
    record and registered Task sources itself; model-authored source IDs cannot raise the evidence
    ceiling. Sources that were collected but not bound to a specific decision remain task-level
    candidates and every affected conclusion stays unknown at E0.
    """

    context = require_context()
    remote_inputs = (getattr(context, "params", {}) or {}).get("remote_inputs") or {}
    if not isinstance(remote_inputs, dict):
        raise ValueError("design evidence publisher requires Workflow material bindings")
    raw_route = _runtime_json_value(remote_inputs.get("design_routing_record"))
    if not isinstance(raw_route, dict):
        raise ValueError("design evidence publisher requires the bound design_routing_record")
    route = validate_design_route(raw_route)["design_routing_record"]
    if route.get("overall_effort") != "heavy":
        raise ValueError("design heavy evidence publisher requires a heavy routing record")

    source_labels = _current_task_source_labels()
    source_summary = "、".join(item.split(" · ", 1)[0] for item in source_labels) or "无"
    decisions = route.get("decisions") or []
    lines = [
        "# 产品方案重型取证包（保守基线）",
        "",
        "> 结论：当前没有任何来源被确定性地逐项绑定到设计决定。所有决定均为未知或待验证假设，证据强度上限为 E0；不得据此批准默认行为。",
        "",
        "## 来源覆盖",
        "",
        f"- 已注册任务级候选来源 ID：{source_summary}",
        "- 逐决策可核验来源绑定：无",
        "- 限制：任务级候选来源不能自动证明任一决定；未形成逐项绑定前不提升证据等级。",
        "",
        "## 逐决策证据与缺口",
    ]
    for decision in decisions:
        decision_id = str(decision.get("decision_id") or "未编号")
        question = str(decision.get("decision_question") or "未提供决定问题")
        domain = str(decision.get("primary_domain") or "")
        gates = [
            gate for gate in (decision.get("hard_gates") or [])
            if gate in DESIGN_HARD_GATE_LABELS
        ]
        gate_text = "、".join(DESIGN_HARD_GATE_LABELS[gate] for gate in gates) or "无"
        owner = "产品负责人、数据/安全责任人及权限责任人" if gates else "产品负责人"
        gap_focus = DESIGN_DOMAIN_EVIDENCE_GAPS.get(
            domain,
            "现状事实、触发条件、作用范围、失败恢复和责任边界",
        )
        gate_gap = (
            "；并缺少对"
            + "、".join(DESIGN_HARD_GATE_LABELS[gate] for gate in gates)
            + "风险的责任人、人工复核及回滚证据"
            if gates else ""
        )
        lines.extend([
            "",
            f"### {decision_id} · {question}",
            "",
            f"- 主责领域：`{domain}`",
            f"- 触发硬门：{gate_text}",
            "- 实际逐决策来源 ID：无",
            "- 证据状态：未知；待验证假设",
            "- 证据强度上限：E0",
            f"- 证据缺口：尚不能回答“{question}”；缺少可定位、可复核的{gap_focus}证据、外部对照及反方样本{gate_gap}。",
            f"- 需要确认的人：{owner}",
            "- 需要确认的事项：允许的行为、触发条件、作用范围、责任归属、失败恢复和回滚边界。",
            "- 确认前禁止采用：任何自动执行、静默写入、跨身份或跨租户共享，以及不可逆默认值。",
        ])

    active_gates = sorted({
        gate
        for decision in decisions
        for gate in (decision.get("hard_gates") or [])
        if gate in DESIGN_HARD_GATE_LABELS
    })
    lines.extend(["", "## 硬门确认矩阵", ""])
    for gate in sorted(DESIGN_HARD_GATE_LABELS):
        affected = "、".join(
            str(decision.get("decision_id") or "未编号")
            for decision in decisions
            if gate in (decision.get("hard_gates") or [])
        )
        if affected:
            lines.append(
                f"- `{gate}`（{DESIGN_HARD_GATE_LABELS[gate]}）：已触发且未决；影响 {affected}；"
                "必须经明确人审，保留可撤销/回滚路径并指定责任人。"
            )
        else:
            lines.append(
                f"- `{gate}`（{DESIGN_HARD_GATE_LABELS[gate]}）：当前路由未触发；"
                "若补充事实显示存在该风险，必须回退重路由，不得沿用未触发结论。"
            )

    lines.extend([
        "",
        "## 不同情况与适用条件",
        "",
        "- 分歧/负向样本：未知；尚无逐决策绑定来源，不能声称未发现反例。",
        "- 差异条件：未知；需补充产品形态、角色、数据敏感度、权限模型和失败损失条件后判断。",
        "- 可替换结论的条件：只有新增可定位来源并完成逐决策绑定、反方复查和责任人确认后，才可高于 E0。",
        "",
        "## 用户确认清单",
        "",
        "- 是否接受先以 E0 草稿继续，仅用于讨论结构，不作为上线或默认行为依据。",
        "- 是否补充当前产品事实、真实界面/流程、权限模型和可核验外部来源后重新取证。",
        "- 六类风险存在时，是否逐项指定隐私、身份、权限、静默写入、跨租户及高损失不可逆风险的责任人与回滚方案。",
    ])
    if source_labels:
        lines.extend(["", "## 已注册但尚未逐决策绑定的候选来源", ""])
        lines.extend(f"- {label}" for label in source_labels)

    packet = "\n".join(lines).strip() + "\n"
    _save_artifact(
        key="design_heavy_evidence",
        value=packet,
        content_type="text",
        source_tool="publish_design_heavy_evidence",
        internal_publish=True,
    )
    return {
        "status": "published",
        "evidence_ceiling": "E0",
        "decision_count": len(decisions),
        "hard_gates": active_gates,
        "registered_source_count": len(source_labels),
        "message": "保守证据包已确定性发布；请立即结束当前步骤并等待人审。",
    }


def publish_design_heavy_evidence(value: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate registered sources and publish one fail-closed Chinese evidence packet.

    The model may submit compact candidate findings and exact source locators returned by search
    tools. The Host resolves only URLs, DOI values, and knowledge-document IDs against the live
    citation registry, renders the Markdown itself, and never lets guessed citation indices or
    model-authored source IDs raise the evidence ceiling.
    Validated source bindings remain provisional (E1) until human semantic review; unbound claims
    remain hypotheses at E0.
    """

    context = require_context()
    remote_inputs = (getattr(context, "params", {}) or {}).get("remote_inputs") or {}
    if not isinstance(remote_inputs, dict):
        raise ValueError("design evidence publisher requires Workflow material bindings")
    raw_route = _runtime_json_value(remote_inputs.get("design_routing_record"))
    if not isinstance(raw_route, dict):
        raise ValueError("design evidence publisher requires the bound design_routing_record")
    route = validate_design_route(raw_route)["design_routing_record"]
    if route.get("overall_effort") != "heavy":
        raise ValueError("design heavy evidence publisher requires a heavy routing record")

    sources = _current_attempt_sources()
    source_summary = "、".join(str(item["title"]) for item in sources) or "本轮未使用外部资料"
    payload = value if isinstance(value, dict) else {}
    submitted_decisions: dict[str, dict[str, Any]] = {}
    submission_warnings: list[str] = []
    raw_decisions = payload.get("decisions")
    for raw in raw_decisions if isinstance(raw_decisions, list) else []:
        if not isinstance(raw, dict):
            submission_warnings.append("忽略了非对象形式的决定记录")
            continue
        decision_id = _bounded_evidence_text(raw.get("decision_id"), limit=80)
        if not decision_id or decision_id in submitted_decisions:
            submission_warnings.append("忽略了缺少 ID 或重复的决定记录")
            continue
        submitted_decisions[decision_id] = raw

    allowed_tool_states = {"succeeded", "partial", "failed", "unavailable", "not_used"}
    raw_tool_statuses = payload.get("tool_statuses")
    raw_tool_statuses = raw_tool_statuses if isinstance(raw_tool_statuses, dict) else {}
    tool_statuses: dict[str, tuple[str, str]] = {}
    for tool in ("web_search", "url_fetch", "kb"):
        raw_status = raw_tool_statuses.get(tool)
        if isinstance(raw_status, dict):
            status = _bounded_evidence_text(raw_status.get("status"), limit=40).lower()
            note = _bounded_evidence_text(raw_status.get("note"), limit=240)
        else:
            status = _bounded_evidence_text(raw_status, limit=40).lower()
            note = ""
        if status not in allowed_tool_states:
            status = "not_used"
        tool_statuses[tool] = (status, note)

    requested_retrieval_status = _bounded_evidence_text(
        payload.get("retrieval_status"), limit=40,
    ).lower()
    if requested_retrieval_status not in {"completed", "limited", "unavailable"}:
        requested_retrieval_status = "limited"

    decisions = route.get("decisions") or []
    decision_rows: list[dict[str, Any]] = []
    matched_source_ids: set[str] = set()
    used_source_ids: set[str] = set()
    rejected_refs: list[str] = []
    for decision in decisions:
        decision_id = str(decision.get("decision_id") or "未编号")
        submitted = submitted_decisions.get(decision_id) or {}
        bound_sources, rejected = _resolve_submitted_sources(
            submitted.get("source_refs"), sources,
        )
        rejected_refs.extend(rejected)
        finding = _bounded_evidence_text(submitted.get("finding"))
        matched_source_ids.update(
            str(source["source_id"]) for source in bound_sources
        )
        if finding:
            used_source_ids.update(str(source["source_id"]) for source in bound_sources)
        counterevidence = _bounded_evidence_text(submitted.get("counterevidence"))
        raw_conditions = submitted.get("conditions")
        conditions = [
            text for text in (
                _bounded_evidence_text(item, limit=300)
                for item in (raw_conditions if isinstance(raw_conditions, list) else [])
            ) if text
        ][:8]
        raw_remaining_gaps = submitted.get("remaining_gaps")
        remaining_gaps = [
            text for text in (
                _bounded_evidence_text(item, limit=300)
                for item in (
                    raw_remaining_gaps if isinstance(raw_remaining_gaps, list) else []
                )
            ) if text
        ][:8]
        decision_rows.append({
            "route": decision,
            "finding": finding,
            "counterevidence": counterevidence,
            "conditions": conditions,
            "remaining_gaps": remaining_gaps,
            "bound_sources": bound_sources,
            "evidence_ceiling": "E1" if bound_sources and finding else "E0",
        })

    routed_ids = {
        str(decision.get("decision_id") or "未编号") for decision in decisions
    }
    missing_submissions = sorted(routed_ids - set(submitted_decisions))
    unknown_submissions = sorted(set(submitted_decisions) - routed_ids)
    if missing_submissions:
        submission_warnings.append(
            "以下路由决定没有执行者记录，已按未知补齐：" + "、".join(missing_submissions)
        )
    if unknown_submissions:
        submission_warnings.append(
            "忽略了不属于已批准路由的决定：" + "、".join(unknown_submissions)
        )

    tool_report_has_result = any(
        status in {"succeeded", "partial"} for status, _note in tool_statuses.values()
    )
    mechanical_coverage = bool(decision_rows) and all(
        row["bound_sources"] and row["finding"] and row["counterevidence"]
        and row["conditions"]
        for row in decision_rows
    )
    retrieval_status = (
        "unavailable"
        if requested_retrieval_status == "unavailable" and not sources
        else "limited"
    )
    if requested_retrieval_status == "completed":
        downgrade_reasons = []
        if not sources:
            downgrade_reasons.append("运行时没有登记可用来源")
        if not tool_report_has_result:
            downgrade_reasons.append("没有工具被报告为成功或部分成功")
        if missing_submissions:
            downgrade_reasons.append("存在漏交决定")
        if rejected_refs:
            downgrade_reasons.append("存在被拒绝的来源定位符")
        if not mechanical_coverage:
            downgrade_reasons.append("逐决定来源、发现、反方或差异条件覆盖不完整")
        downgrade_reasons.append("领域最低要求和来源语义绑定仍待人审")
        submission_warnings.append(
            "执行者报告 completed，但" + "；".join(downgrade_reasons)
            + "，受控状态保持 limited"
        )
    elif requested_retrieval_status == "unavailable" and sources:
        submission_warnings.append(
            "执行者报告 unavailable，但运行时存在登记来源；受控状态记为 limited 并等待人审"
        )

    overall_ceiling = "E1" if used_source_ids else "E0"
    conclusion = (
        "> 已找到可参考的资料，但资料与具体产品决定之间仍需人工核对。下面的建议不会自动变成正式规则。"
        if used_source_ids else
        "> 本轮未使用外部资料。下面列出的是需要补充信息和确认的事项，不会自动变成正式规则。"
    )
    lines = [
        "# 产品方案：调研与决策依据",
        "",
        "## 先看结论",
        "",
        conclusion,
        "",
        "## 本次参考资料",
        "",
        f"- 资料：{source_summary}",
        "- 使用说明：资料只能帮助判断，是否采用仍由负责人结合当前产品情况确认。",
        "",
        "<details>",
        "<summary>查看本次资料检查记录</summary>",
        "",
    ]
    status_labels = {
        "succeeded": "成功", "partial": "部分成功", "failed": "失败",
        "unavailable": "不可用", "not_used": "未使用/未报告",
    }
    for tool, (status, note) in tool_statuses.items():
        suffix = f"；{note}" if note else ""
        tool_labels = {"web_search": "公开资料检索", "url_fetch": "资料页面读取", "kb": "项目知识库"}
        lines.append(f"- {tool_labels[tool]}：{status_labels[status]}{suffix}")
    if submission_warnings or rejected_refs:
        lines.extend(["", "### 需要留意的检查结果"])
        lines.extend(f"- {warning}" for warning in submission_warnings)
        if rejected_refs:
            lines.append(
                "- 拒绝未在本次运行来源登记表中出现的定位符："
                + "、".join(dict.fromkeys(rejected_refs))
            )

    lines.extend(["", f"- 资料检查结果：{'有资料可供核对' if used_source_ids else '本轮没有可用的外部资料'}", "", "</details>"])
    lines.extend(["", "## 需要确认的决定"])
    for row in decision_rows:
        decision = row["route"]
        decision_id = str(decision.get("decision_id") or "未编号")
        question = str(decision.get("decision_question") or "未提供决定问题")
        domain = str(decision.get("primary_domain") or "未知领域")
        gates = [
            gate for gate in (decision.get("hard_gates") or [])
            if gate in DESIGN_HARD_GATE_LABELS
        ]
        gate_text = "、".join(
            f"{gate}（{DESIGN_HARD_GATE_LABELS[gate]}）" for gate in gates
        ) or "无"
        owner = "产品负责人、数据/安全责任人及权限责任人" if gates else "产品负责人"
        gap_focus = DESIGN_DOMAIN_EVIDENCE_GAPS.get(
            domain,
            "现状事实、触发条件、作用范围、失败恢复和责任边界",
        )
        gate_gap = (
            "；并缺少对"
            + "、".join(DESIGN_HARD_GATE_LABELS[gate] for gate in gates)
            + "风险的责任人、人工复核及回滚证据"
            if gates else ""
        )
        source_names = "、".join(
            str(source["title"]) for source in row["bound_sources"]
        ) or "本轮没有可用资料"
        lines.extend([
            "",
            f"### {question}",
            "",
            f"- 相关方面：{DESIGN_DOMAINS.get(domain, '产品整体')}",
            f"- 需要重点把关的风险：{gate_text}",
            f"- 可参考资料：{source_names}",
            "- 当前判断：" + (
                row["finding"] or "信息不足，暂不做决定。"
            ) + ("（仍需验证）" if not row["bound_sources"] and row["finding"] else ""),
            "- 可能的不同情况：" + (
                row["counterevidence"] or "尚未取得反例，不能据此认为没有例外。"
            ) + (
                "（仍需验证）"
                if row["counterevidence"] and not row["bound_sources"] else ""
            ),
            "- 适用条件：" + (
                "；".join(row["conditions"])
                or "需补充产品形态、角色、数据敏感度、权限模型和失败损失后再判断。"
            ) + (
                "（仍需验证）"
                if row["conditions"] and not row["bound_sources"] else ""
            ),
            f"- 还缺少：可核对的{gap_focus}信息、外部对照和反例{gate_gap}。",
            "- 其他待补充：" + (
                "；".join(row["remaining_gaps"]) or "暂无补充，但仍需由负责人复核。"
            ),
            f"- 建议确认人：{owner}",
            "- 确认内容：允许做什么、何时触发、影响范围、谁负责，以及失败后如何恢复。",
            "- 确认前不会启用：自动执行、后台自动写入、跨身份或跨租户共享，以及不可逆默认值。",
        ])

    active_heavy_domains = list(dict.fromkeys([
        domain
        for row in decision_rows
        if row["route"].get("effort") == "heavy"
        for domain in [
            str(row["route"].get("primary_domain") or ""),
            *[str(item) for item in (row["route"].get("linked_domains") or [])],
        ]
        if domain in DESIGN_DOMAINS
    ] + [
        str(domain) for domain in (route.get("linked_domains") or [])
        if str(domain) in DESIGN_DOMAINS
    ]))
    lines.extend(["", "## 进入正式方案前还要补齐", ""])
    for domain in active_heavy_domains:
        lines.append(f"### {DESIGN_DOMAINS.get(domain, domain)}")
        for requirement in DESIGN_DOMAIN_HEAVY_REQUIREMENTS.get(domain, []):
            lines.append(f"- [ ] {requirement}")
        lines.append("- 当前状态：以上内容尚未确认，确认前不会写入正式方案。")

    active_gates = sorted({
        gate
        for decision in decisions
        for gate in (decision.get("hard_gates") or [])
        if gate in DESIGN_HARD_GATE_LABELS
    })
    lines.extend(["", "## 上线前需要确认的风险", ""])
    for gate in sorted(DESIGN_HARD_GATE_LABELS):
        affected = "、".join(
            str(decision.get("decision_id") or "未编号")
            for decision in decisions
            if gate in (decision.get("hard_gates") or [])
        )
        if affected:
            lines.append(
                f"- {DESIGN_HARD_GATE_LABELS[gate]}：需要确认；"
                "确认时要指定负责人，并保留撤销或恢复方案。"
            )
        else:
            lines.append(
                f"- {DESIGN_HARD_GATE_LABELS[gate]}：当前信息未显示有此风险；"
                "如果后续出现相关情况，需要新增安全确认。"
            )

    lines.extend([
        "",
        "## 分歧、反例与适用条件",
        "",
        "- 每个事项已分别列出可能的不同情况；没有记录不代表没有例外。",
        "- 更新判断的条件：补充可核对的资料、检查相反案例，并由负责人确认。",
        "",
        "## 下一步确认清单",
        "",
        "- 是否先按草稿继续讨论；草稿不会作为上线或默认行为依据。",
        "- 是否补充当前产品事实、真实界面、实际流程、权限规则和可核对的外部资料。",
        "- 出现隐私、身份、权限、后台自动写入、跨租户或不可逆风险时，是否已经指定负责人和恢复方案。",
    ])
    if sources:
        lines.extend(["", "## 参考资料明细", ""])
        for source in sources:
            label = str(source['title'])
            if source["url"]:
                label += f" · {source['url']}"
            binding = (
                "已关联到上面的待确认事项，仍需负责人核对"
                if source["source_id"] in matched_source_ids else "暂未关联到具体事项"
            )
            lines.append(f"- {label} · {binding}")

    packet = "\n".join(lines).strip() + "\n"
    _save_artifact(
        key="design_heavy_evidence",
        value=packet,
        content_type="text",
        source_tool="publish_design_heavy_evidence",
        internal_publish=True,
    )
    return {
        "status": "published",
        "evidence_ceiling": overall_ceiling,
        "decision_count": len(decisions),
        "hard_gates": active_gates,
        "registered_source_count": len(sources),
        "bound_source_count": len(matched_source_ids),
        "e1_source_count": len(used_source_ids),
        "rejected_source_ref_count": len(rejected_refs),
        "retrieval_status": retrieval_status,
        "message": "调研与待确认事项已整理，请等待负责人确认。",
        "_agent_control": {
            "stop": True,
            "reason": "workflow_publisher_completed",
            "final_text": "调研与待确认事项已整理，等待确认。",
        },
    }


def publish_design_heavy_unavailable(
    value: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the deterministic E0 packet when retrieval yielded no usable source.

    The intended call has no arguments.  An empty ``value`` object is accepted as a
    compatibility shape because small local models sometimes wrap every tool call
    in ``{"value": {}}``.  Non-empty values remain invalid so this fallback cannot
    smuggle unverified findings into the Host-owned evidence packet.
    """

    if value not in (None, {}):
        raise ValueError("value must be omitted or an empty object")

    return publish_design_heavy_evidence({"retrieval_status": "unavailable"})


def _parse_stage_chain(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    lowered = text.lower()
    if any(marker in lowered for marker in ("all", "full-pipeline", "全流程", "七阶段")):
        return list(STAGE_ORDER)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        parsed = parsed.get("stage_chain") or parsed.get("stages")
    if isinstance(parsed, list):
        values = [str(item or "").strip().lower() for item in parsed]
    else:
        values = [
            item.strip().lower()
            for item in re.split(r"\s*(?:->|→|,|，|、|\||/|;|；)\s*", text)
            if item.strip()
        ]
    stages: list[str] = []
    for value in values:
        stage = next((key for key, aliases in STAGE_ALIASES.items() if value in aliases), "")
        if not stage:
            raise ValueError(f"Unsupported product stage: {value}")
        stages.append(stage)
    return stages


def validate_design_escalation(value: dict[str, Any]) -> dict[str, Any]:
    """Upgrade scoped design decisions in-place without adding another Router."""
    if not isinstance(value, dict):
        raise ValueError("design escalation must be an object")
    remote = getattr(require_context(), "params", {}).get("remote_inputs") or {}
    _assert_current_stage("design", remote)
    original = _mapping(remote.get("design_routing_record"))
    if not original:
        raise ValueError("design escalation requires the bound design_routing_record")
    baseline = validate_design_route(original)["design_routing_record"]
    trigger = value.get("trigger")
    if trigger not in DESIGN_ESCALATION_TRIGGERS:
        raise ValueError("escalation needs a registered trigger")
    if not value.get("reason") or not value.get("evidence"):
        raise ValueError("escalation requires reason and locatable evidence")
    updates = value.get("decisions") or []
    if not isinstance(updates, list) or not updates:
        raise ValueError("escalation must identify affected decisions")
    decisions = {item["decision_id"]: copy.deepcopy(item) for item in baseline["decisions"]}
    for change in updates:
        if not isinstance(change, dict) or change.get("decision_id") not in decisions:
            raise ValueError("escalation cannot create or change decision scope")
        item = decisions[change["decision_id"]]
        if change.get("effort", "heavy") != "heavy":
            raise ValueError("escalation must be monotonic to heavy")
        for key in ("primary_domain", "linked_domains", "decision_question"):
            if key in change and change[key] != item.get(key):
                raise ValueError("escalation cannot change approved decision scope")
        item["effort"] = "heavy"
        item["hard_gates"] = sorted(set(item.get("hard_gates") or []) | set(change.get("hard_gates") or []))
        item["effort_reasons"] = [*item.get("effort_reasons", []), str(value["reason"])]
    baseline["decisions"] = list(decisions.values())
    baseline["overall_effort"] = "heavy"
    effective = validate_design_route(baseline)["design_routing_record"]
    return {"design_escalation": {
        "trigger": trigger, "reason": value["reason"], "evidence": value["evidence"],
        "effective_route": effective, "scope_unchanged": True,
        "risk_confirmation_required": any(item["hard_gates"] for item in effective["decisions"]),
    }}


def normalize_product_parameters(
    product_goal: str,
    stage_chain: str,
    execution_depth: str,
    word_target: str,
    reference_sample_choice: str,
) -> dict[str, Any]:
    """Compatibility adapter for callers that already supply one explicit stage."""

    goal = str(product_goal or "").strip()
    if not goal:
        raise ValueError("product_goal is required before starting the Workflow")
    stages = _parse_stage_chain(stage_chain)
    if len(stages) != 1:
        raise ValueError(
            "stage_chain must contain exactly one stage; multi-stage plans are routed "
            "one stage per Workflow session"
        )
    plan_result = validate_product_execution_plan({
        "selected_stage": stages[0],
        "stage_chain": [],
    })
    if not plan_result["valid"]:
        raise ValueError("; ".join(plan_result["errors"]))
    depth = _normalize_execution_depth(execution_depth)
    has_text_stage = stages[0] in TEXT_STAGES
    target = _normalize_word_target(word_target, text_stage=has_text_stage)
    sample_status = _normalize_reference_sample(
        reference_sample_choice, text_stage=has_text_stage,
    )

    execution_plan = dict(plan_result["execution_plan"])
    execution_plan.update({
        "product_goal": goal,
        "execution_depth": depth,
        "word_target": target,
        "reference_sample_status": sample_status,
    })
    return {
        "execution_plan": execution_plan,
    }


def load_product_skill_contract(
    stage_id: str,
    reference_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Load one compact packaged router or stage contract without calling a model.

    Args:
        stage_id: Parent Router id or one of the seven canonical product-stage ids.
        reference_paths: Optional exact ``references/*.md`` resources selected from a prior
            call's ``available_resources``. Absolute paths, Workflow input/output paths and
            Writer-returned artifact paths are ignored and reported; traversal is rejected.
            Omit this argument on the first design-stage call because bound Router domains are
            loaded automatically.
    """

    raw_stage = str(stage_id or "").strip().lower().replace("_", "-")
    normalized = next((
        key for key, aliases in STAGE_ALIASES.items() if raw_stage in aliases
    ), raw_stage)
    if normalized not in {"router", *STAGE_SKILLS}:
        raise ValueError(f"Unsupported stage_id: {stage_id!r}")
    if normalized != "router":
        current_context = require_context()
        bound = getattr(current_context, "params", {}).get("remote_inputs") or {}
        _assert_current_stage(normalized, bound)

    resources = _resource_files()
    available_resources: list[str] = []
    ignored_reference_paths: list[str] = []
    requested_paths = (
        [reference_paths]
        if isinstance(reference_paths, str)
        else (reference_paths or [])
    )
    normalized_requested_paths: list[str] = []
    for requested in requested_paths:
        relative = str(requested).strip().replace("\\", "/")
        if ".." in Path(relative).parts:
            raise ValueError("reference_paths must stay inside the selected child Skill")
        normalized_requested_paths.append(relative)
    skill_name = "product-solution-delivery"
    if normalized == "router":
        paths = ["SKILL.md", *ROUTER_REFERENCES]
        ignored_reference_paths.extend(normalized_requested_paths)
    else:
        skill_name = STAGE_SKILLS[normalized]
        child_prefix = f"children/{skill_name}"
        available_resources = sorted(
            path for path in resources if path.startswith(f"{child_prefix}/")
        )
        allowed_reference_resources = {
            path for path in available_resources
            if path.startswith(f"{child_prefix}/references/") and path.endswith(".md")
        }
        paths = [
            f"{child_prefix}/SKILL.md",
            "references/rich-text-presentation.md",
        ]
        # The design Skill deliberately loads domain methods only after its second
        # Router selects relevant decisions. Other children have one mandatory contract.
        mandatory = {
            "direction": ["direction-brief.md"],
            "competitive": ["artifact-contract.md", "research-and-evidence.md", "visualization-rules.md"],
            "design": [
                "human-in-the-loop.md", "multi-source-research.md",
                "boundary-and-routing.md", "evidence-and-effort.md",
            ],
            "prd": ["prd-contract.md"],
            "prototype": ["prototype-contract.md"],
            "review": ["review-contract.md"],
            "handoff": ["handoff-contract.md"],
        }
        for name in mandatory[normalized]:
            path = f"{child_prefix}/references/{name}"
            if path in resources:
                paths.append(path)
        if normalized == "design":
            route = _bound_artifact_payload(bound.get("design_routing_record"))
            if isinstance(route, dict):
                domains = set(route.get("primary_domains") or []) | set(route.get("linked_domains") or [])
                for decision in route.get("decisions") or []:
                    if isinstance(decision, dict):
                        domains.add(decision.get("primary_domain"))
                        domains.update(decision.get("linked_domains") or [])
                for domain, names in DESIGN_DOMAIN_REFERENCES.items():
                    if domain in domains:
                        paths.extend(f"{child_prefix}/references/{name}" for name in names)
        for relative in normalized_requested_paths:
            if Path(relative).is_absolute() or re.match(r"^[A-Za-z]:/", relative):
                ignored_reference_paths.append(relative)
                continue
            path = (
                relative
                if relative.startswith(child_prefix + "/")
                else f"{child_prefix}/{relative}"
            )
            if path not in allowed_reference_resources:
                ignored_reference_paths.append(relative)
                continue
            paths.append(path)

    unique_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    sections = []
    if normalized == "router":
        sections.append(ROUTER_RUNTIME_CONTRACT)
    else:
        for path in unique_paths:
            sections.append(f"\n\n--- BEGIN {path} ---\n{_safe_read(path)}\n--- END {path} ---")

    trace = {
        "package_release": PACKAGE_RELEASE,
        "host_profile": "lazymind",
        "parent_skill": "product-solution-delivery",
        "selected_stage": normalized if normalized != "router" else None,
        "selected_child_skill": skill_name if normalized != "router" else None,
        "selected_child_loaded": normalized != "router",
        "loaded_resources": unique_paths,
        "ignored_reference_paths": ignored_reference_paths,
        "contract_sha256": _digest(unique_paths),
        "capabilities": {"resource_read": True, "child_invoke": False},
        "capability_evidence": {"resource_read": "embedded bundle decoded and resources read"},
    }
    try:
        context = require_context()
        if isinstance(getattr(context, "params", None), dict):
            context.params.setdefault("product_skill_loads", {})[normalized] = trace
    except RuntimeError:
        pass
    presentation_override = (
        "- Every business stage publishes one semantic artifact in two synchronized "
        "representations: self-contained interactive HTML as the default view and Markdown as "
        "the editable/downloadable view. They must share the same facts, version and status; "
        "never ask a second model to independently rewrite the companion format.\n"
        "- Preserve the existing artifact structure and enrich only the relevant existing "
        "sections with compact tables, Mermaid relationship diagrams, factual timelines, "
        "defined-axis quadrant/distribution charts or actual project images. Never invent dates, "
        "metrics, coordinates or screenshots merely to make the artifact visual.\n"
        "- For design, render only the selected light or heavy branch and never create an empty "
        "panel for the unselected branch.\n"
        if normalized in STAGE_SKILLS
        else ""
    )
    adapter_override = (
        "\n\n--- BEGIN LAZYMIND HOST ADAPTER OVERRIDES ---\n"
        "These runtime rules are authoritative where the portable parent contract differs:\n"
        "- The user has authorized one shared project in one window and the default artifact "
        "structure when no reference sample is bound. Do not ask the separate reference-sample "
        "question and do not enter awaiting-reference-sample. Record none-confirmed instead.\n"
        "- A Router only selects scope and prepares bound context. It never performs external "
        "retrieval; evidence work belongs to the selected business-stage evidence step.\n"
        "- Host execution limits for rounds, deadlines, repeated calls and per-tool counts are "
        "hard ceilings and cannot be relaxed by contract prose.\n"
        + presentation_override
        + "--- END LAZYMIND HOST ADAPTER OVERRIDES ---"
    )
    warning = (
        "Ignored reference_paths that were not exact packaged references/*.md entries in "
        f"available_resources: {ignored_reference_paths}"
        if ignored_reference_paths
        else ""
    )
    return {
        "package_release": PACKAGE_RELEASE,
        "stage_id": normalized,
        "skill_name": skill_name,
        "contract_sha256": _digest(unique_paths),
        "resource_root": (
            f"embedded://product-solution-delivery/children/{skill_name}"
            if normalized != "router"
            else "embedded://product-solution-delivery"
        ),
        "contract_text": "".join(sections).lstrip() + adapter_override,
        "runtime_trace": trace,
        "available_resources": available_resources,
        "ignored_reference_paths": ignored_reference_paths,
        "warning": warning,
    }


SHARED_UPSTREAM_SLOTS = (
    "upstream_direction", "upstream_competitive", "upstream_design",
    "upstream_prd", "upstream_prototype", "upstream_review", "upstream_handoff",
)

PRODUCT_STAGE_INPUT_SLOTS = {
    "competitive": (
        "execution_plan", "research_evidence", "material_digest", "direction_document",
        "workspace_seed", "stage_approval",
    ) + SHARED_UPSTREAM_SLOTS,
    "prototype": (
        "execution_plan", "material_digest", "design_document", "prd_document",
        "workspace_seed", "stage_approval",
    ) + SHARED_UPSTREAM_SLOTS,
    "delivery": (
        "routing_record", "execution_plan", "design_routing_record", "direction_document",
        "competitive_analysis", "design_document", "prd_document", "prototype",
        "review_document", "handoff_document",
        "workspace_seed", "stage_approval",
    ) + SHARED_UPSTREAM_SLOTS,
}

STAGE_ARTIFACTS = {
    "direction": ("direction_document", "direction-brief", "产品方向说明"),
    "competitive": ("competitive_analysis", "competitive-analysis", "竞品与生态位报告"),
    "design": ("design_document", "product-design-spec", "产品方案"),
    "prd": ("prd_document", "prd", "产品需求文档"),
    "prototype": ("prototype", "prototype", "交互原型"),
    "review": ("review_document", "review-report", "产品方案评审报告"),
    "handoff": ("handoff_document", "development-handoff", "研发交付文档"),
}
STAGE_REPRESENTATIONS = {
    "direction": {"html": "direction_document_html", "markdown": "direction_document"},
    "competitive": {"html": "competitive_analysis", "markdown": "competitive_analysis_markdown"},
    "design": {"html": "design_document_html", "markdown": "design_document"},
    "prd": {"html": "prd_document_html", "markdown": "prd_document"},
    "prototype": {"html": "prototype", "markdown": "prototype_markdown"},
    "review": {"html": "review_document_html", "markdown": "review_document"},
    "handoff": {"html": "handoff_document_html", "markdown": "handoff_document"},
}
ELIGIBLE_NEXT_STAGES = {
    "direction": ["competitive", "design", "review"],
    "competitive": ["design", "review"],
    "design": ["prd", "prototype", "review", "handoff"],
    "prd": ["prototype", "review", "handoff"],
    "prototype": ["review", "handoff"],
    "review": ["direction", "design", "prd", "prototype", "handoff"],
    "handoff": ["review"],
}


def _bound_artifact_payload(value: Any) -> Any:
    current = value
    for _ in range(5):
        if isinstance(current, dict):
            nested = next((
                current[key] for key in ("path", "value", "data", "text") if key in current
            ), current)
            if nested is current:
                return current
            current = nested
            continue
        if isinstance(current, list):
            return current
        text = str(current or "").strip()
        if not text:
            return ""
        try:
            candidate = Path(text).expanduser().resolve()
            if candidate.is_file():
                current = candidate.read_text(encoding="utf-8")
                continue
        except OSError:
            pass
        try:
            current = json.loads(text)
        except json.JSONDecodeError:
            return text
    return current


def _bound_artifact_descriptor(value: Any) -> dict[str, Any]:
    """Check real content, not merely a truthy path or a transport metadata envelope."""
    current = value
    descriptor: dict[str, Any] = {"present": False}
    path_expected = False
    for _ in range(6):
        if isinstance(current, dict):
            for key in (
                "filename", "content_type", "seq", "revision", "version",
                "revision_id", "artifact_id", "resource_id", "content_hash",
            ):
                if current.get(key) not in (None, ""):
                    descriptor[key] = current[key]
            if current.get("path"):
                current = current["path"]
                path_expected = True
                continue
            nested = next((
                current[key] for key in ("value", "data", "text") if key in current
            ), None)
            if nested is None:
                descriptor.setdefault("content_type", "json")
                descriptor["reason"] = "No readable document body in transport metadata"
                return descriptor
            current = nested
            continue
        if isinstance(current, list):
            descriptor.setdefault("content_type", "list")
            descriptor["item_count"] = len(current)
            entries = [_bound_artifact_descriptor(item) for item in current]
            descriptor["present"] = any(item["present"] for item in entries)
            descriptor["items"] = entries
            return descriptor
        text = str(current or "").strip()
        if not text:
            descriptor["reason"] = "Empty artifact content"
            return descriptor
        try:
            candidate = Path(text).expanduser().resolve()
            if candidate.is_file():
                content = candidate.read_bytes()
                descriptor.setdefault("filename", candidate.name)
                descriptor.setdefault("content_type", candidate.suffix.lstrip(".") or "file")
                descriptor["size_bytes"] = len(content)
                descriptor["present"] = bool(content.strip())
                descriptor["content_sha256"] = hashlib.sha256(content).hexdigest()
                if not descriptor["present"]:
                    descriptor["reason"] = "Empty artifact file"
                return descriptor
        except OSError:
            pass
        if path_expected or text.startswith(("/", "~/", "file://")):
            descriptor["reason"] = "Artifact file is missing or unreadable"
            return descriptor
        descriptor.setdefault("content_type", "text")
        raw_text = str(current or "")
        descriptor["size_bytes"] = len(raw_text.encode("utf-8"))
        descriptor["present"] = True
        descriptor["content_sha256"] = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        return descriptor
    descriptor.setdefault("content_type", "unknown")
    return descriptor


def _assert_current_stage(stage: str, remote: dict[str, Any]) -> None:
    plan = _bound_artifact_payload(remote.get("execution_plan"))
    if not isinstance(plan, dict) or not plan:
        return  # Direct standalone callers do not have a Workflow execution plan.
    selected = plan.get("selected_stage")
    if not selected:
        chain = plan.get("stage_chain") or []
        selected = chain[0] if isinstance(chain, list) and len(chain) == 1 else None
    if _normalize_stage(selected) != stage:
        raise ValueError("stage_id must match execution_plan.selected_stage for this session")


def _mapping(value: Any) -> dict[str, Any]:
    result = _bound_artifact_payload(value)
    return result if isinstance(result, dict) else {}


def _upstream_value(remote: dict[str, Any], stage: str) -> Any:
    slot = STAGE_ARTIFACTS[stage][0]
    value = remote.get(slot)
    return value if _bound_artifact_descriptor(value)["present"] else remote.get("upstream_" + stage)


def _plain_assessment_value(value: Any) -> Any:
    """Convert model-validated tool arguments into ordinary immutable containers."""
    if isinstance(value, BaseModel):
        # Do not let schema defaults become substantive decision fields. The runtime
        # validator reapplies control defaults after converting the explicitly supplied data.
        return value.model_dump(exclude_none=True, exclude_defaults=True)
    if isinstance(value, list):
        return [_plain_assessment_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain_assessment_value(item) for key, item in value.items()}
    return value


def _assessment_error(errors: list[str]) -> ValueError:
    return ValueError(
        "stage assessment has invalid fields; repair every listed field in one retry: "
        + "; ".join(errors)
    )


def validate_product_stage_assessment(
    value: ProductStageAssessmentInput,
    stage: Literal[
        "direction", "competitive", "design", "prd", "prototype", "review", "handoff"
    ] | None = None,
) -> dict[str, Any]:
    """Normalize and validate one child assessment against a stage-aware JSON schema.

    The tool schema supplies safe defaults for optional collections, valid enum values, nested
    check shapes, and the stricter non-handoff readiness contract. Runtime validation reports all
    remaining semantic errors together so an Agent never repairs one field per tool round. ``stage``
    is a compatibility-only redundant hint for older prompts; new callers put it inside ``value``.
    """
    stage_hint = _normalize_stage(stage) if stage else ""
    raw = _plain_assessment_value(value)
    if not isinstance(raw, dict):
        raise ValueError("stage assessment must be an object")
    result = copy.deepcopy(raw)
    errors: list[str] = []
    notes: list[str] = []

    stage = _normalize_stage(result.get("stage") or result.get("stage_id"))
    if stage not in STAGE_SKILLS:
        errors.append("stage: expected direction, competitive, design, prd, prototype, review, or handoff")
    else:
        if stage_hint and stage_hint != stage:
            errors.append(
                f"stage: redundant tool argument {stage_hint!r} must match value.stage {stage!r}"
            )
        context = require_context()
        remote = getattr(context, "params", {}).get("remote_inputs") or {}
        _assert_current_stage(stage, remote)
        result["stage"] = stage

    status = result.get("status", "draft")
    if not isinstance(status, str) or status not in {"draft", "reviewable"}:
        errors.append("status: expected draft or reviewable; acceptance is a separate user event")
        status = "draft"
    result["status"] = status

    if result.get("execution_depth"):
        try:
            depth = _normalize_execution_depth(result["execution_depth"])
            if depth == "auto":
                errors.append("execution_depth: child must resolve auto to light, minimum-fill, or full")
            else:
                result["execution_depth"] = depth
        except (TypeError, ValueError):
            errors.append("execution_depth: expected light, minimum-fill, or full")

    for key in ("decisions", "dependencies", "open_questions", "quality_notes"):
        current = result.get(key, [])
        if current is None:
            current = []
        if not isinstance(current, list):
            errors.append(f"{key}: expected an array")
            current = []
        result[key] = current

    for index, item in enumerate(result["dependencies"]):
        if not isinstance(item, dict):
            errors.append(f"dependencies[{index}]: expected an object")

    normalized_decisions: list[dict[str, Any]] = []
    for index, item in enumerate(result["decisions"], 1):
        if not isinstance(item, dict):
            errors.append(f"decisions[{index - 1}]: expected an object")
            continue
        decision = copy.deepcopy(item)
        # Deferral is a server-recorded human action, never a child assessment claim.
        decision.pop("deferred", None)
        decision.pop("deferral_ref", None)
        if not str(decision.get("decision_id") or "").strip():
            decision["decision_id"] = f"{stage.upper() if stage else 'STAGE'}-DEC-{index:03d}"
            notes.append(
                f"Allocated stable decision_id {decision['decision_id']} for an unlabelled proposed decision."
            )
        decision_status = decision.get("status", "proposed")
        if not isinstance(decision_status, str) or decision_status not in {
            "proposed", "accepted", "reopened", "superseded",
        }:
            errors.append(
                f"decisions[{index - 1}].status: expected proposed, accepted, reopened, or superseded"
            )
            decision_status = "proposed"
        decision["status"] = decision_status
        if decision_status == "accepted":
            if not decision.get("accepted_by") or not decision.get("acceptance_ref"):
                # Missing evidence cannot establish acceptance. Downgrading is safer and faster
                # than asking the model to fabricate an approval reference in a retry.
                decision["status"] = "proposed"
                decision.pop("accepted_by", None)
                decision.pop("acceptance_ref", None)
                notes.append(
                    f"Decision {decision['decision_id']} stayed proposed because no sourced acceptance event was bound."
                )
            else:
                risk = decision.get("risk")
                risky = bool(decision.get("hard_gates")) or (
                    isinstance(risk, str) and risk in {"high", "irreversible"}
                )
                if risky and decision.get("accepted_by") == "delegated-ai":
                    errors.append(
                        f"decisions[{index - 1}]: high-risk or irreversible decisions cannot be accepted by delegated-ai"
                    )
        normalized_decisions.append(decision)
    result["decisions"] = normalized_decisions

    checks = result.get("checks") or {}
    if not isinstance(checks, dict):
        errors.append("checks: expected an object mapping check names to {status, evidence}")
        checks = {}
    normalized_checks: dict[str, dict[str, Any]] = {}
    status_aliases = {
        "pass": "passed", "success": "passed", "ok": "passed",
        "fail": "failed", "error": "failed", "pending": "not-checked",
        "unchecked": "not-checked", "not_checked": "not-checked", "not checked": "not-checked",
    }
    for name, check in checks.items():
        if not isinstance(check, dict):
            errors.append(f"checks.{name}: expected {{status, evidence}}")
            continue
        normalized = copy.deepcopy(check)
        raw_check_status = normalized.get("status", "not-checked")
        check_status = status_aliases.get(
            str(raw_check_status or "not-checked").strip().lower(), raw_check_status or "not-checked",
        )
        if not isinstance(check_status, str) or check_status not in {
            "passed", "failed", "not-checked",
        }:
            errors.append(f"checks.{name}.status: expected passed, failed, or not-checked")
            continue
        if check_status == "passed" and not str(normalized.get("evidence") or "").strip():
            check_status = "not-checked"
            notes.append(f"Check {name} stayed not-checked because it had no locatable evidence.")
        normalized["status"] = check_status
        normalized_checks[str(name)] = normalized
    result["checks"] = normalized_checks

    readiness = result.get("implementation_readiness", "not-assessed")
    if isinstance(readiness, dict):
        readiness = readiness.get("status") or readiness.get("value") or readiness.get("readiness")
    readiness_aliases = {
        "not_assessed": "not-assessed", "not assessed": "not-assessed",
        "ready_with_open_items": "ready-with-open-items",
    }
    readiness = readiness_aliases.get(
        str(readiness or "not-assessed").strip().lower(), readiness or "not-assessed",
    )
    if not isinstance(readiness, str) or readiness not in {
        "not-assessed", "blocked", "ready-with-open-items", "ready",
    }:
        errors.append(
            "implementation_readiness: expected not-assessed, blocked, ready-with-open-items, or ready"
        )
        readiness = "not-assessed"
    if stage and stage != "handoff" and readiness not in {"not-assessed", "blocked"}:
        errors.append("implementation_readiness: only the handoff child may report ready states")
        readiness = "not-assessed"
    result["implementation_readiness"] = readiness

    result["quality_notes"].extend(note for note in notes if note not in result["quality_notes"])
    if errors:
        raise _assessment_error(errors)
    return result


def load_product_stage_inputs(stage_id: str) -> dict[str, Any]:
    """Read only the immutable materials bound to one non-Writer product stage."""
    raw = str(stage_id or "").strip().lower().replace("_", "-")
    normalized = next((
        key for key, aliases in STAGE_ALIASES.items() if raw in aliases
    ), raw)
    if normalized not in PRODUCT_STAGE_INPUT_SLOTS:
        raise ValueError(
            "stage_id must be competitive, prototype, or delivery for bound material loading"
        )
    context = require_context()
    remote = (context.params or {}).get("remote_inputs") or {}
    if not isinstance(remote, dict):
        remote = {}
    if normalized != "delivery":
        _assert_current_stage(normalized, remote)
    materials = {
        slot: (
            _bound_artifact_descriptor(remote[slot])
            if normalized == "delivery" and slot in {
                artifact_slot for artifact_slot, _, _ in STAGE_ARTIFACTS.values()
            }
            else _bound_artifact_payload(remote[slot])
        )
        for slot in PRODUCT_STAGE_INPUT_SLOTS[normalized]
        if remote.get(slot) not in (None, "", [])
    }
    return {
        "stage_id": normalized,
        "materials": materials,
        "available_slots": list(materials),
        "missing_optional_slots": [
            slot for slot in PRODUCT_STAGE_INPUT_SLOTS[normalized] if slot not in materials
        ],
    }


def _valid_approval(event: Any) -> bool:
    return bool(
        isinstance(event, dict)
        and all(event.get(key) for key in ("approval_id", "action", "stage", "source", "reference"))
        and event["source"] in {"user-interface", "user-message"}
    )


def _version_key(artifact: dict[str, Any]) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)", str(artifact.get("version") or ""))
    if not match:
        raise ValueError("workspace artifact version must use MAJOR.MINOR")
    return int(match[1]), int(match[2])


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _decision_content(decision: dict[str, Any]) -> dict[str, Any]:
    """Compare a decision without confusing acceptance metadata with its substance."""
    return {key: value for key, value in decision.items() if key not in {
        "status", "accepted_by", "acceptance_ref", "reopens", "pending_revisions", "deferred", "deferral_ref",
    }}


def _decision_approval_matches(
    event: dict[str, Any], decision: dict[str, Any], *, stage: str, workspace_id: str,
    descriptor: dict[str, Any], artifacts: list[dict[str, Any]],
) -> bool:
    """Match the exact server-snapshotted decision and its reviewed artifact baseline."""
    snapshot = event.get("decision_snapshot_json")
    digest = event.get("decision_hash") or event.get("expected_decision_hash")
    if not isinstance(snapshot, str) or digest != "sha256:" + hashlib.sha256(snapshot.encode()).hexdigest():
        return False
    try:
        if json.loads(snapshot) != _decision_content(decision):
            return False
    except (TypeError, ValueError):
        return False
    if event.get("stage") != stage or event.get("workspace_id") != workspace_id:
        return False
    if not descriptor.get("present") or event.get("content_sha256") != descriptor.get("content_sha256"):
        return False
    return any(
        artifact.get("artifact_id") == event.get("artifact_id")
        and artifact.get("artifact_type") == STAGE_ARTIFACTS[stage][1]
        and artifact.get("version") == event.get("version")
        and artifact.get("host_artifact", {}).get("content_sha256") == event.get("content_sha256")
        for artifact in artifacts
    )


def _hard_stop_questions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        candidates = [decision, *decision.get("pending_revisions", [])]
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("status") in {"accepted", "superseded"}:
                continue
            if not candidate.get("hard_gates") and candidate.get("risk") not in {"high", "irreversible"}:
                continue
            decision_id = str(candidate.get("decision_id") or decision.get("decision_id") or "unknown")
            label = str(candidate.get("decision_question") or candidate.get("question") or
                        candidate.get("value") or decision_id)[:200]
            questions[decision_id] = {
                "question_id": "HITL-" + decision_id, "decision_id": decision_id,
                "question": f"高风险决定“{label}”尚未得到明确确认；可先保留草稿或暂缓，不能作为实施就绪的已确认基线。",
                "blocking": True, "confirmation": "hard-stop",
            }
    return list(questions.values())


def _merge_workspace_decisions(
    previous: list[dict[str, Any]], current: list[dict[str, Any]], history: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one baseline per decision ID; proposals cannot replace accepted decisions."""
    merged: dict[str, dict[str, Any]] = {}
    history = copy.deepcopy(history)
    for item in [*previous, *current]:
        if not isinstance(item, dict) or not item.get("decision_id"):
            continue
        item = copy.deepcopy(item)
        key = item["decision_id"]
        old = merged.get(key)
        if old is None:
            merged[key] = item
        elif old == item:
            continue
        elif old.get("status") == "accepted" and item.get("status") != "accepted":
            if _decision_content(old) != _decision_content(item):
                proposals = old.setdefault("pending_revisions", [])
                if item not in proposals:
                    proposals.append(item)
        else:
            if old not in history:
                history.append(copy.deepcopy(old))
            merged[key] = item
    return list(merged.values()), history


def _assessment_record(
    manifest: dict[str, Any], *, source: str, execution_depth: Any,
) -> dict[str, Any]:
    """Bind reported assessment results to real content, without claiming they ran."""
    result = {
        "source": source,
        "content_sha256": manifest["host_artifact"].get("content_sha256"),
        "dependencies_sha256": _stable_digest(manifest.get("dependencies", [])),
        "status": "reviewable" if manifest["status"] == "accepted" else manifest["status"],
        "execution_depth": execution_depth,
        **{key: copy.deepcopy(manifest.get(key)) for key in (
            "decisions", "open_questions", "quality_notes", "checks", "implementation_readiness",
        )},
    }
    result["fingerprint"] = _stable_digest(result)
    return result


def _dependencies_for_stage(
    stage: str, remote: dict[str, Any], workspace: dict[str, Any], assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind selected upstream revisions; one alternative satisfies a required group."""
    required_groups = {
        "direction": [], "competitive": [("direction",)], "design": [("direction",)],
        "prd": [("design",)], "prototype": [("design", "prd")],
        "review": [tuple(key for key in STAGE_SKILLS if key != "review")],
        "handoff": [("design",)],
    }
    dependencies: list[dict[str, Any]] = []
    artifacts = workspace.get("artifacts") or []
    bindings = workspace.get("host_artifact_bindings") or []
    for group in required_groups[stage]:
        resolved: list[dict[str, Any]] = []
        for upstream in group:
            slot, kind, _ = STAGE_ARTIFACTS[upstream]
            descriptor = _bound_artifact_descriptor(_upstream_value(remote, upstream))
            if not descriptor["present"]:
                continue
            binding = next((item for item in reversed(bindings) if isinstance(item, dict) and (
                item.get("slot_id") == slot or item.get("material_id") == "upstream_" + upstream
            )), {})
            candidates = [item for item in artifacts if isinstance(item, dict) and item.get("artifact_type") == kind]
            matched = next((item for item in reversed(candidates) if (
                (binding.get("revision_id") and item.get("host_artifact", {}).get("revision_id") == binding["revision_id"])
                or item.get("host_artifact", {}).get("content_sha256") == descriptor.get("content_sha256")
            )), None)
            state = "available"
            if matched and matched.get("status") in {"needs-update", "superseded"}:
                state = "outdated"
            if stage == "handoff" and (not matched or matched.get("status") != "accepted"):
                state = "conflict"
            resolved.append({
                "kind": "required", "artifact_type": kind,
                "artifact_id": matched["artifact_id"] if matched else (
                    "external-" + str(descriptor.get("content_sha256") or "unknown")[:24]
                ),
                "version": matched["version"] if matched else str(binding.get("revision") or descriptor.get("revision") or "unversioned"),
                "status": state,
                "source_slot": "upstream_" + upstream if remote.get("upstream_" + upstream) else slot,
                "host_revision": binding,
                "handling": "Use only this bound revision; request user baseline selection for conflicts.",
            })
        # An attached equivalent input is valid only after the child identifies the
        # actual bound material and records what part supplies the necessary contract.
        if not resolved:
            for item in assessment.get("dependencies", []):
                if not isinstance(item, dict) or not item.get("evidence"):
                    continue
                if item.get("artifact_type") not in {STAGE_ARTIFACTS[key][1] for key in group}:
                    continue
                source_slot = str(item.get("source_slot") or "")
                source_value = remote.get(source_slot)
                if source_slot == "product_goal":
                    source_value = _mapping(remote.get("execution_plan")).get("product_goal")
                source = _bound_artifact_descriptor(source_value)
                if not source["present"] or source_slot in {"research_evidence", "material_digest"}:
                    continue
                resolved.append({
                    "kind": "required", "artifact_type": item["artifact_type"],
                    "artifact_id": "external-" + str(source.get("content_sha256") or source_slot)[:24],
                    "version": str(item.get("version") or "unversioned"),
                    "status": "available" if stage != "handoff" else "conflict",
                    "source_slot": source_slot, "evidence": item["evidence"],
                    "handling": "Equivalent input supplied by user; acceptance requires a separate sourced user event.",
                })
                break
        if resolved:
            dependencies.extend(resolved)
        else:
            dependencies.append({
                "kind": "required", "artifact_type": "|".join(STAGE_ARTIFACTS[key][1] for key in group),
                "artifact_id": None, "version": None, "status": "missing",
                "handling": "补充所需材料、转入上游阶段，或保留明确标注缺口的草稿。",
            })
    # Additional selected upstream materials stay version-bound even when supplemental.
    already = {item["source_slot"] for item in dependencies if item.get("source_slot")}
    for upstream, (slot, kind, _) in STAGE_ARTIFACTS.items():
        if upstream == stage or slot in already or "upstream_" + upstream in already:
            continue
        descriptor = _bound_artifact_descriptor(_upstream_value(remote, upstream))
        if not descriptor["present"]:
            continue
        matched = next((item for item in reversed(artifacts) if isinstance(item, dict)
                        and item.get("artifact_type") == kind
                        and item.get("host_artifact", {}).get("content_sha256") == descriptor.get("content_sha256")), None)
        dependencies.append({
            "kind": "supplemental", "artifact_type": kind,
            "artifact_id": matched["artifact_id"] if matched else "external-" + str(descriptor.get("content_sha256"))[:24],
            "version": matched["version"] if matched else "unversioned",
            "status": "outdated" if matched and matched.get("status") in {"needs-update", "superseded"} else "available",
            "source_slot": slot, "handling": "Keep selected upstream content and its acceptance labels.",
        })
    return dependencies


def build_product_handoff_state(assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the internal Manifest/Workspace handoff for one completed stage."""

    context = require_context()
    remote = (context.params or {}).get("remote_inputs") or {}
    if not isinstance(remote, dict):
        remote = {}
    routing = _bound_artifact_payload(remote.get("routing_record"))
    plan = _bound_artifact_payload(remote.get("execution_plan"))
    if not isinstance(routing, dict):
        routing = {}
    if not isinstance(plan, dict):
        plan = {}
    selected = _normalize_stage(plan.get("selected_stage") or routing.get("selected_stage"))
    if selected not in STAGE_ARTIFACTS:
        raise ValueError("A valid single selected_stage is required for finalization")

    session_id = str((context.params or {}).get("session_id") or "temporary-session")
    slot, artifact_type, title = STAGE_ARTIFACTS[selected]
    descriptor = _bound_artifact_descriptor(remote.get(slot))
    representations = {
        kind: {"slot": representation_slot, "source_session_id": session_id,
               **_bound_artifact_descriptor(remote.get(representation_slot))}
        for kind, representation_slot in STAGE_REPRESENTATIONS[selected].items()
    }
    missing_representations = [
        kind for kind, representation in representations.items()
        if not representation["present"]
    ]
    present = descriptor["present"] and not missing_representations
    raw_assessment = _mapping(remote.get(selected + "_assessment")) or assessment
    assessed = validate_product_stage_assessment(raw_assessment or {
        "stage": selected, "status": "draft",
        "quality_notes": ["尚未收到当前原子 Skill 的质量评估，不因文件存在而推断可评审。"],
    })
    if assessed["stage"] != selected:
        raise ValueError("assessment stage must match the selected stage")
    workspace = copy.deepcopy(_mapping(remote.get("workspace_seed")))
    if workspace and (workspace.get("visibility") != "agent-internal" or not workspace.get("workspace_id")):
        raise ValueError("workspace_seed must be an internal Workspace with workspace_id")
    workspace_id = workspace.get("workspace_id") or f"workspace-{uuid.uuid5(uuid.NAMESPACE_URL, session_id).hex}"
    artifacts = workspace.setdefault("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("workspace artifacts must be an array")
    approvals = [item for item in workspace.get("approvals", []) if _valid_approval(item)]
    for event in [*workspace.get("approval_events", []), _mapping(remote.get("stage_approval"))]:
        if _valid_approval(event) and not any(old["approval_id"] == event["approval_id"] for old in approvals):
            approvals.append(event)
    old_decisions, decision_history = _merge_workspace_decisions(
        workspace.get("decisions") or [], [], workspace.get("decision_history") or [],
    )
    decisions = assessed["decisions"]
    for index, decision in enumerate(decisions):
        decision.setdefault("status", "proposed")
        previous = next((old for old in old_decisions if old.get("decision_id") == decision["decision_id"]), None)
        if previous:
            # A downstream rewrite cannot erase a known hard-stop classification.
            if previous.get("hard_gates"):
                decision["hard_gates"] = list(dict.fromkeys([*previous["hard_gates"], *(decision.get("hard_gates") or [])]))
            if previous.get("risk") in {"high", "irreversible"}:
                decision["risk"] = previous["risk"]
        unchanged_accepted = previous and previous.get("status") == "accepted" and all(
            previous.get(key) == decision.get(key) for key in ("value", "accepted_by", "acceptance_ref")
        ) and _decision_content(previous) == _decision_content(decision)
        if previous and previous.get("status") == "accepted" and (
            _decision_content(previous) == _decision_content(decision)
        ) and decision.get("status") in {"proposed", "accepted"}:
            # Reusing an existing accepted baseline needs no new acceptance event.
            # The child cannot rewrite its accepted_by/reference while doing so.
            decisions[index] = decision = copy.deepcopy(previous)
            unchanged_accepted = True
        evidence = None
        if decision.get("status") == "accepted" and not unchanged_accepted:
            evidence = next((event for event in approvals if event["reference"] == decision.get("acceptance_ref")
                             and event["action"] in {"accept-decision", "decision-acceptance", "delegate-decision"}
                             and event.get("decision_id") == decision["decision_id"]
                             and _decision_approval_matches(event, decision, stage=selected,
                                 workspace_id=workspace_id, descriptor=descriptor, artifacts=artifacts)), None)
            if evidence and decision.get("accepted_by") == "delegated-ai":
                if (evidence["action"] != "delegate-decision" or evidence.get("reversible") is not True
                        or decision.get("hard_gates") or decision.get("risk") in {"high", "irreversible"}):
                    evidence = None
            elif evidence and evidence.get("approved_by") != decision.get("accepted_by"):
                evidence = None
            if not evidence:
                decision["status"] = "proposed"
                decision.pop("accepted_by", None)
                decision.pop("acceptance_ref", None)
                assessed["quality_notes"].append("A proposed decision was not promoted without a sourced user acceptance event.")
        if previous and previous.get("status") == "accepted" and not unchanged_accepted and not evidence:
            decision["status"] = "proposed"
            decision["reopens"] = previous["decision_id"]
    dependencies = _dependencies_for_stage(selected, remote, workspace, assessed)
    missing = [item for item in dependencies if item["kind"] == "required" and item["status"] != "available"]
    # Host-owned HITL gates are derived from the current decision baseline. A child
    # may copy an older assessment, but that must not resurrect a resolved gate.
    # All independently reported business blockers remain untouched.
    open_questions = [copy.deepcopy(item) for item in assessed["open_questions"] if not (
        isinstance(item, dict) and item.get("confirmation") == "hard-stop"
        and isinstance(item.get("decision_id"), str) and bool(item["decision_id"])
        and item.get("question_id") == "HITL-" + item["decision_id"]
    )]
    combined_decisions, _ = _merge_workspace_decisions(old_decisions, decisions, [])
    if selected == "design":
        design_route = _mapping(remote.get("design_escalation")).get("effective_route") or _mapping(remote.get("design_routing_record"))
        # The child assessment must not hide a hard gate already found by Router 2.
        for routed in design_route.get("decisions", []):
            if not isinstance(routed, dict) or not routed.get("hard_gates"):
                continue
            existing = next((item for item in combined_decisions if item.get("decision_id") == routed.get("decision_id")), None)
            if existing is None:
                pending = {**copy.deepcopy(routed), "status": "proposed"}
                combined_decisions.append(pending)
                decisions.append(copy.deepcopy(pending))
            else:
                known_gates = set(existing.get("hard_gates") or [])
                if existing.get("status") == "accepted" and not set(routed["hard_gates"]).issubset(known_gates):
                    pending = {**_decision_content(existing), "status": "proposed", "reopens": existing["decision_id"],
                               "hard_gates": sorted(known_gates | set(routed["hard_gates"]))}
                    existing.setdefault("pending_revisions", []).append(pending)
                    decisions = [item for item in decisions if item.get("decision_id") != existing["decision_id"]]
                    decisions.append(pending)
                else:
                    existing["hard_gates"] = sorted(known_gates | set(routed["hard_gates"]))
    open_questions.extend(_hard_stop_questions(combined_decisions))
    if not present:
        detail = "、".join(missing_representations) or "主产物"
        open_questions.append({"question_id": "ARTIFACT-MISSING", "question": f"{title} 尚未形成完整的 HTML 与 Markdown 双格式产物（缺少：{detail}）。", "blocking": True})
    for index, dependency in enumerate(missing, 1):
        open_questions.append({
            "question_id": f"DEP-{index:03d}", "blocking": True,
            "question": f"必要输入 {dependency['artifact_type']} 当前为 {dependency['status']}。",
        })
    checks = assessed["checks"]
    for check in checks.values():
        # This describes who supplied the assertion, not whether a browser/tool
        # actually executed it. A digest binds it to content but is not evidence.
        check["evidence_source"] = "child-assessment"
        claimed_digest = check.get("artifact_sha256")
        if claimed_digest and claimed_digest != descriptor.get("content_sha256"):
            check["reported_status"] = check["status"]
            check["status"] = "not-checked"
            check["binding_status"] = "mismatch"
            open_questions.append({
                "question_id": "CHECK-CONTENT-MISMATCH", "blocking": True,
                "question": "核验依据绑定了其他产物内容，需要针对当前版本重新核验。",
            })
        else:
            check["artifact_sha256"] = descriptor.get("content_sha256")
            check["binding_status"] = "current-content"
    if present and selected in {"prototype", "competitive"}:
        body = _bound_artifact_payload(remote.get(slot))
        errors = (_validate_prototype(str(body)) if selected == "prototype"
                  else _validate_competitive_report(str(body)))
        for index, error in enumerate(errors, 1):
            open_questions.append({"question_id": f"HTML-{index:03d}", "question": error, "blocking": True})
        checks["host_static_validation"] = {
            "status": "failed" if errors else "passed",
            "evidence": "; ".join(errors) if errors else "Embedded HTML structure validation passed; interactions were not executed.",
            "evidence_source": "workflow-finalizer",
            "validator": "_validate_" + ("prototype" if selected == "prototype" else "competitive_report"),
            "artifact_sha256": descriptor.get("content_sha256"),
            "binding_status": "current-content",
        }
    if selected == "prototype" and assessed["status"] == "reviewable":
        for check in ("interaction_desktop", "interaction_mobile"):
            if checks.get(check, {}).get("status") != "passed":
                open_questions.append({"question_id": check, "question": "原型尚缺真实桌面或移动视口交互走查。", "blocking": True})
    blocking = not present or bool(missing) or any(
        isinstance(item, dict) and item.get("blocking") is True for item in open_questions
    ) or any(item["status"] == "failed" for item in checks.values())
    status = "draft" if blocking else assessed["status"]
    readiness = "blocked" if blocking else assessed["implementation_readiness"]
    if selected == "handoff" and readiness in {"ready", "ready-with-open-items"}:
        required_checks = ("rules", "acceptance", "traceability", "risks", "resources")
        verified = all(checks.get(key, {}).get("status") == "passed" for key in required_checks)
        assigned = all(isinstance(item, dict) and item.get("owner") and item.get("handling") for item in open_questions)
        if not verified:
            readiness = "not-assessed"
            assessed["quality_notes"].append("研发就绪门禁未全部记录可定位的核验依据。")
        elif open_questions:
            readiness = "ready-with-open-items" if assigned else "blocked"
    previous_versions = [item for item in artifacts if item.get("artifact_type") == artifact_type]
    previous = max(previous_versions, key=_version_key) if previous_versions else None
    representation_digest = _stable_digest({
        kind: value.get("content_sha256") for kind, value in representations.items()
    })
    identical = (
        previous and present
        and previous.get("host_artifact", {}).get("content_sha256") == descriptor.get("content_sha256")
        and previous.get("representation_digest", representation_digest) == representation_digest
        and previous.get("dependencies") == dependencies
    )
    version = previous["version"] if identical else (
        f"{_version_key(previous)[0]}.{_version_key(previous)[1] + 1}" if previous else "1.0"
    )
    artifact_id = previous["artifact_id"] if identical else (
        "artifact-" + uuid.uuid5(uuid.NAMESPACE_URL, ":".join((
            workspace_id, selected, version, session_id, str(descriptor.get("content_sha256")),
            representation_digest,
            hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest(),
        ))).hex
    )
    manifest = {
        "schema_version": "1.1",
        "visibility": "agent-internal",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "title": title,
        "version": version,
        "status": status,
        "source_skill": STAGE_SKILLS[selected],
        "workspace_id": workspace_id,
        "supersedes": previous.get("supersedes") if identical else previous.get("artifact_id") if previous else None,
        "decisions": decisions,
        "dependencies": dependencies,
        "open_questions": open_questions,
        "quality_notes": [
            "Registered the readable content digest; host revision is recorded only when supplied by the host.",
            *assessed["quality_notes"],
        ],
        "checks": checks,
        "implementation_readiness": readiness,
        "eligible_next_stages": ELIGIBLE_NEXT_STAGES[selected],
        "host_artifact": {"slot": slot, "source_session_id": session_id, **descriptor},
        "representations": representations,
        "representation_digest": representation_digest,
    }
    record = _assessment_record(
        manifest, source="child-assessment" if raw_assessment else "missing-child-assessment",
        execution_depth=assessed.get("execution_depth") or plan.get("execution_depth"),
    )
    prior_record = copy.deepcopy(previous.get("assessment_record")) if identical else None
    history = copy.deepcopy(previous.get("assessment_history", [])) if identical else []
    if identical and not prior_record:
        prior_record = _assessment_record(previous, source="legacy-registration", execution_depth=None)
        prior_record.update({"revision": 1, "assessment_id": "assessment-" + _stable_digest({
            "artifact_id": artifact_id, "revision": 1, "fingerprint": prior_record["fingerprint"],
        })[:32]})
    assessment_changed = not prior_record or prior_record.get("fingerprint") != record["fingerprint"]
    if assessment_changed:
        record["revision"] = int(prior_record.get("revision", 0)) + 1 if prior_record else 1
        record["assessment_id"] = "assessment-" + _stable_digest({
            "artifact_id": artifact_id, "revision": record["revision"], "fingerprint": record["fingerprint"],
        })[:32]
        if prior_record:
            history.append({
                **prior_record, "artifact_status": previous["status"],
                "accepted_by": previous.get("accepted_by"), "acceptance_ref": previous.get("acceptance_ref"),
            })
    else:
        record = prior_record
    manifest["assessment_record"] = record
    manifest["assessment_history"] = history
    if identical and previous.get("status") == "accepted":
        if status == "reviewable":
            manifest["status"] = "accepted"
            for key in ("accepted_by", "acceptance_ref"):
                if previous.get(key):
                    manifest[key] = previous[key]
        else:
            manifest["acceptance_recheck_required"] = True
    elif identical and previous.get("acceptance_recheck_required"):
        # Passing a later recheck cannot silently reapply the historical approval.
        manifest["acceptance_recheck_required"] = True
    if identical:
        # Content and assessment have separate lifecycles: unchanged content keeps
        # its logical version while fresh quality results replace only its view.
        artifacts[artifacts.index(previous)] = manifest
        if assessment_changed and status == "draft":
            # The content revision is unchanged, but consumers must not continue
            # treating an invalidated quality baseline as ready for implementation.
            changed_ids = {artifact_id}
            invalidated: set[str] = set()
            while changed_ids:
                invalidated.update(changed_ids)
                next_changed: set[str] = set()
                for existing in artifacts:
                    if existing["artifact_id"] in changed_ids or existing.get("status") == "superseded":
                        continue
                    for dependency in existing.get("dependencies", []):
                        if dependency.get("artifact_id") in changed_ids:
                            dependency["status"] = "conflict"
                            dependency["handling"] = "Upstream assessment changed; resolve its quality findings before confirming this baseline."
                            existing["status"] = "needs-update"
                            existing["implementation_readiness"] = "blocked"
                            next_changed.add(existing["artifact_id"])
                changed_ids = next_changed - invalidated
    elif present:
        changed_ids = {previous["artifact_id"]} if previous else set()
        invalidated: set[str] = set()
        if previous:
            previous["status"] = "superseded"
        while changed_ids:
            invalidated.update(changed_ids)
            next_changed: set[str] = set()
            for existing in artifacts:
                if existing.get("status") == "superseded":
                    continue
                for dependency in existing.get("dependencies", []):
                    if dependency.get("artifact_id") in changed_ids:
                        dependency["status"] = "outdated"
                        existing["status"] = "needs-update"
                        existing["implementation_readiness"] = "blocked"
                        next_changed.add(existing["artifact_id"])
            changed_ids = next_changed - invalidated
        artifacts.append(manifest)
    design_route = _bound_artifact_payload(remote.get("design_routing_record"))
    escalation = _mapping(remote.get("design_escalation"))
    if selected == "design" and isinstance(escalation.get("effective_route"), dict):
        design_route = escalation["effective_route"]
    trace = load_product_skill_contract(selected)["runtime_trace"]
    trace.update({
        "execution_mode": "workflow-native" if session_id != "temporary-session" else "skill-only",
        "state_backend": "workflow-artifact-slots" if session_id != "temporary-session" else "in-context",
        "loaded_at": "finalization-contract-validation",
    })
    recommended_next = ELIGIBLE_NEXT_STAGES[selected][0] if ELIGIBLE_NEXT_STAGES[selected] else None
    # This loader confirms contract availability now, not that an earlier model obeyed it.
    merged_decisions, decision_history = _merge_workspace_decisions(old_decisions, decisions, decision_history)
    workspace.update({
        "schema_version": "1.1",
        "visibility": "agent-internal",
        "workspace_id": workspace_id,
        "workspace_mode": workspace.get("workspace_mode", "shared-project"),
        "name": workspace.get("name") or str(plan.get("product_goal") or title)[:80],
        "project_overview": workspace.get("project_overview") or {
            "user_goal": str(plan.get("product_goal") or ""),
            "target_users": [],
            "business_context": "",
            "scope": [],
            "non_goals": [],
            "constraints": [],
        },
        "decisions": merged_decisions,
        "decision_history": decision_history,
        "materials": workspace.get("materials") or [],
        "artifacts": artifacts,
        "version_dependencies": [
            {"artifact_id": item["artifact_id"], "version": item["version"], "dependencies": item.get("dependencies", [])}
            for item in artifacts
        ],
        "approvals": approvals,
        "approval_events": approvals,
        "current_run": {
            "skill_trace": trace,
            "hard_stop_policy": "explicit-decision",
            "run_status": "awaiting-stage-confirmation" if present else "blocked",
            "selected_stage": selected,
            "route_source": routing.get("route_source"),
            "route_reason": routing.get("route_reason", ""),
            "confidence": routing.get("confidence"),
            "execution_depth": assessed.get("execution_depth") or plan.get("execution_depth"),
            "stage_chain": plan.get("planned_stage_chain") or [selected],
            "stage_cursor": 0,
            "active_artifact_id": artifact_id if present else None,
            "reference_sample": {
                "status": plan.get("reference_sample_status", "not-required"),
                "artifact_type": artifact_type,
                "material_ids": [],
                "inherit": [],
            },
            "design_router": design_route if selected == "design" else None,
            "pending_transition": None,
            "recommended_next_stage": recommended_next,
            "available_actions": ["continue", "switch-stage", "export", "finish"] if present else (
                ["switch-stage", "export", "finish"] if artifacts else ["switch-stage", "finish"]
            ),
        },
    })
    completion = {"draft": "草稿，仍有待确认或补充项", "reviewable": "可以评审", "accepted": "已经确认"}.get(manifest["status"], "需要更新") if present else "尚未形成有效产物"
    readiness = {
        "not-ready": "还需补充后才能交给研发",
        "partially-ready": "部分内容已经具备实施条件",
        "ready": "已经具备实施条件",
    }.get(manifest["implementation_readiness"], "需要进一步确认")
    stage_label = STAGE_DISPLAY_LABELS.get(selected, selected)
    next_stages = "、".join(STAGE_DISPLAY_LABELS.get(item, item) for item in ELIGIBLE_NEXT_STAGES[selected])
    recommendation_line = (
        f"- 建议下一步：{STAGE_DISPLAY_LABELS.get(recommended_next, recommended_next)}\n"
        if recommended_next else ""
    )
    summary = (
        f"## {stage_label}已完成\n\n- 当前版本：{title} v{version}（{completion}）\n"
        f"- 当前状态：{readiness}\n"
        f"{recommendation_line}"
        f"- 接下来可以进入：{next_stages}\n\n"
        "内容已经保存到当前项目。你可以继续下一阶段、调整当前内容，或者先停在这里；"
        "已有材料和产物都会保留。"
    )
    if open_questions:
        readable_questions: list[str] = []
        for item in open_questions:
            if isinstance(item, dict):
                question = str(item.get("question") or "").strip()
                readable_questions.append(question or "有一项待确认问题尚未补充说明")
            else:
                readable_questions.append(str(item).strip() or "有一项待确认问题尚未补充说明")
        summary += "\n\n待处理：" + "；".join(readable_questions)
    return {
        "stage_manifest": manifest,
        "workspace_state": workspace,
        "delivery_summary": summary,
    }


def publish_product_handoff_state() -> str:
    """Build and publish the deterministic one-stage handoff as one terminal operation."""

    handoff = build_product_handoff_state()
    for key, content_type in (
        ("stage_manifest", "json"),
        ("workspace_state", "json"),
        ("delivery_summary", "text"),
    ):
        _save_artifact(
            key=key,
            value=handoff[key],
            content_type=content_type,
            source_tool="publish_product_handoff_state",
            internal_publish=True,
        )
    return handoff["delivery_summary"]


class _PrototypeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_title = False
        self.has_viewport = False
        self.has_h1 = False
        self.interactive_controls = 0
        self.images_without_alt: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.has_title = True
        elif tag == "meta" and (values.get("name") or "").lower() == "viewport":
            self.has_viewport = True
        elif tag == "h1":
            self.has_h1 = True
        elif tag in {"button", "input", "select", "textarea"}:
            self.interactive_controls += 1
        elif tag == "a" and values.get("href"):
            self.interactive_controls += 1
        elif tag == "img" and not (values.get("alt") or "").strip():
            self.images_without_alt.append(self.getpos()[0])


def _validate_prototype(content: str) -> list[str]:
    parser = _PrototypeParser()
    parser.feed(content)
    errors: list[str] = []
    if not parser.has_title:
        errors.append("missing <title>")
    if not parser.has_viewport:
        errors.append("missing viewport meta")
    if not parser.has_h1 and not re.search(r"<h1\b", content, flags=re.I):
        errors.append("missing <h1>")
    if parser.interactive_controls == 0:
        errors.append("prototype has no interactive controls or navigable links")
    if parser.images_without_alt:
        errors.append("images missing alt at lines: " + ", ".join(map(str, parser.images_without_alt)))
    if re.search(r"__+[A-Z0-9_]+__+|\bTODO\b|【[^】]+】", content):
        errors.append("prototype contains unresolved placeholders")
    return errors


def _validate_competitive_report(content: str) -> list[str]:
    errors: list[str] = []
    lowered = content.lower()
    for marker in ("<!doctype html", "<title", 'name="viewport"', "<table", "<svg", "<details"):
        if marker not in lowered:
            errors.append(f"competitive report missing {marker}")
    semantic_sections = {
        "竞品对比": ("我与竞品", "竞品对比", "竞争对比", "能力对比", "对比矩阵"),
        "生态位": ("生态位", "生态地图", "生态定位"),
        "定位": ("定位", "差异化", "位置图"),
        "产品启示": ("产品方案", "产品启示", "方案启示", "产品策略", "设计启示"),
    }
    for label, alternatives in semantic_sections.items():
        if not any(marker in content for marker in alternatives):
            errors.append(f"competitive report missing semantic section: {label}")
    # Source links are evidence-dependent. Requiring arbitrary href values when retrieval
    # returned no sources encourages the model to invent URLs merely to satisfy validation.
    if re.search(r"__+[A-Z0-9_]+__+|\bTODO\b|【[^】]+】", content):
        errors.append("competitive report contains unresolved placeholders")
    return errors


def write_product_artifact(
    filename: str,
    content: str,
    validate_as: str = "none",
) -> dict[str, Any]:
    """Write one generated file and optionally run an embedded HTML validator."""

    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("filename must contain a safe file name")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content must be a non-empty string")
    if validate_as not in {"none", "prototype", "competitive"}:
        raise ValueError("validate_as must be 'none', 'prototype', or 'competitive'")

    context = require_context()
    remote = getattr(context, "params", {}).get("remote_inputs") or {}
    if remote.get("execution_plan"):
        selected = _mapping(remote.get("execution_plan")).get("selected_stage")
        if validate_as == "none":
            validate_as = _normalize_stage(selected)
        if validate_as not in {"prototype", "competitive"}:
            raise ValueError("file artifact generation is only available for the selected HTML stage")
        _assert_current_stage(validate_as, remote)
    if not context.workspace_path:
        raise RuntimeError("The active Workflow workspace is unavailable")
    output_root = Path(context.workspace_path) / "product-solution-delivery" / "artifacts"
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{uuid.uuid4().hex}-{safe_name}"
    output_path.write_text(content, encoding="utf-8")

    validation = {"valid": True, "output": "validation not requested"}
    if validate_as == "prototype":
        errors = _validate_prototype(content)
        validation = {
            "valid": not errors,
            "output": "PASS" if not errors else "FAIL: " + "; ".join(errors),
        }
    elif validate_as == "competitive":
        errors = _validate_competitive_report(content)
        validation = {
            "valid": not errors,
            "output": "PASS" if not errors else "FAIL: " + "; ".join(errors),
        }

    return {
        "path": str(output_path.resolve()),
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "validation": validation,
    }


def write_product_artifact_file(
    filename: str,
    content: str,
    validate_as: str = "none",
) -> str:
    """Write a product HTML artifact and return only its exact saveable file path.

    Lightweight validation remains diagnostic and non-blocking. Human approval is the quality
    gate; a semantic wording variation must not force full-document regeneration or hide the file.
    """
    result = write_product_artifact(filename, content, validate_as)
    return str(result["path"])


def write_product_artifact_bundle(
    html_filename: str,
    html_content: str,
    markdown_filename: str,
    markdown_content: str,
    validate_as: str,
) -> dict[str, str]:
    """Atomically publish the two reader representations of one stage artifact.

    The model supplies both bodies in one bounded call. The HTML receives the existing
    stage validator; Markdown stays the editable/exportable semantic companion. Returning
    only exact paths prevents a later save call from accidentally treating either body as
    a path, which was the source of earlier long retry loops.
    """
    if validate_as not in {"prototype", "competitive"}:
        raise ValueError("validate_as must be 'prototype' or 'competitive'")
    markdown_name = Path(str(markdown_filename or "")).name
    if not markdown_name or markdown_name in {".", ".."}:
        raise ValueError("markdown_filename must contain a safe file name")
    if Path(markdown_name).suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("markdown_filename must end in .md or .markdown")
    if not isinstance(markdown_content, str) or not markdown_content.strip():
        raise ValueError("markdown_content must be a non-empty string")
    if not re.search(r"^#\s+\S", markdown_content, flags=re.M):
        raise ValueError("markdown_content must contain one document title")

    html = write_product_artifact(html_filename, html_content, validate_as)
    output_root = Path(html["path"]).parent
    markdown_path = output_root / f"{uuid.uuid4().hex}-{markdown_name}"
    try:
        markdown_path.write_text(markdown_content.strip() + "\n", encoding="utf-8")
    except Exception:
        # The HTML file is not published to a Workflow slot until this tool returns;
        # remove the orphan so callers cannot observe a partial logical artifact.
        Path(html["path"]).unlink(missing_ok=True)
        raise
    return {
        "html_path": str(Path(html["path"]).resolve()),
        "markdown_path": str(markdown_path.resolve()),
    }
