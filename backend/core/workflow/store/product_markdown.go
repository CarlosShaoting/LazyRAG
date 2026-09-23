package store

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/extension"
	"github.com/yuin/goldmark/parser"
	"gorm.io/gorm"
	"lazymind/core/common/orm"
)

type ProductMarkdownUpdateRequest struct {
	BaseRevisionID string `json:"base_revision_id"`
	BaseRevision   int    `json:"base_revision"`
	Markdown       string `json:"markdown"`
	IdempotencyKey string `json:"idempotency_key"`
}

var remoteProductImage = regexp.MustCompile(`(?i)<img\s+src="https?://[^"]+"[^>]*>`)

func productMarkdownHTML(stage productStageDefinition, markdown string) (string, error) {
	var body bytes.Buffer
	renderer := goldmark.New(
		goldmark.WithExtensions(extension.GFM),
		goldmark.WithParserOptions(parser.WithAutoHeadingID()),
	)
	if err := renderer.Convert([]byte(markdown), &body); err != nil {
		return "", err
	}
	document := remoteProductImage.ReplaceAllString(body.String(), `<span class="remote-image">[外部图片未自动加载]</span>`)
	return fmt.Sprintf(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>
:root{--ink:#172033;--muted:#64748b;--line:#dbe3ef;--soft:#f5f8fc;--brand:#2563eb;--accent:#0f766e}*{box-sizing:border-box}
body{margin:0;background:#eef3f8;color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}.shell{max-width:1320px;margin:auto;background:#fff;min-height:100vh;box-shadow:0 18px 60px #1e293b14}
.hero{padding:44px clamp(24px,4vw,54px) 28px;background:linear-gradient(135deg,#eff6ff,#f0fdfa);border-bottom:1px solid var(--line)}.eyebrow{color:var(--brand);font-weight:700}.hero h1{font-size:36px;line-height:1.25;margin:.35rem 0}.hero p{color:var(--muted);margin:0}
.toolbar{position:sticky;top:0;z-index:3;display:flex;gap:10px;padding:12px clamp(24px,4vw,54px);background:#ffffffee;border-bottom:1px solid var(--line)}button{border:1px solid #b8c5d8;background:white;border-radius:9px;padding:8px 14px;cursor:pointer}
.layout{display:grid;grid-template-columns:minmax(180px,220px) minmax(0,1fr);gap:28px;padding:32px clamp(24px,4vw,54px) 70px}nav{position:sticky;top:70px;align-self:start;max-height:calc(100vh - 90px);overflow:auto}nav a{display:block;padding:7px 10px;color:#475569;text-decoration:none;border-left:2px solid var(--line)}
article{min-width:0;overflow-wrap:anywhere}article>h1:first-child{display:none}h2{font-size:25px;margin:2.2rem 0 1rem;padding-bottom:.45rem;border-bottom:2px solid var(--ink)}h3{font-size:19px;margin-top:1.8rem}p,li{color:#334155}blockquote{padding:.7rem 1rem;border-left:4px solid var(--brand);background:#eff6ff}
table{width:100%%;border-collapse:collapse;margin:1.2rem 0;display:block;overflow-x:auto}th,td{border:1px solid var(--line);padding:10px 12px;min-width:120px;vertical-align:top}th{background:#eef4fb;text-align:left}code{background:#eff3f8;padding:.12em .35em;border-radius:4px}pre{overflow:auto;background:#111827;color:#e5e7eb;padding:18px;border-radius:10px}
.diagram{margin:1.5rem 0;border:1px solid var(--line);border-radius:14px;background:var(--soft);overflow:hidden}.diagram figcaption{display:flex;justify-content:space-between;padding:11px 16px;background:#eaf1fb;font-weight:700}.diagram-body{padding:20px;overflow-x:auto}.timeline{position:relative;display:grid;gap:14px;padding-left:28px}.timeline:before{content:"";position:absolute;left:8px;top:6px;bottom:6px;width:2px;background:#8eb1e8}.timeline-item{position:relative;background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 14px}.timeline-item:before{content:"";position:absolute;left:-26px;top:17px;width:10px;height:10px;border-radius:50%%;background:var(--brand)}
.quadrant{position:relative;width:720px;height:420px;max-width:100%%;border-left:2px solid #64748b;border-bottom:2px solid #64748b;background:linear-gradient(90deg,#f0fdfa 0 50%%,#eff6ff 50%%),linear-gradient(#eff6ff 0 50%%,#fff 50%%)}.quadrant:before{content:"";position:absolute;left:50%%;top:0;bottom:0;border-left:1px solid #94a3b8}.quadrant:after{content:"";position:absolute;left:0;right:0;top:50%%;border-top:1px solid #94a3b8}.point{position:absolute;transform:translate(-50%%,50%%);z-index:1}.point i{display:block;width:14px;height:14px;border-radius:50%%;background:var(--brand);margin:auto}.point span{display:block;white-space:nowrap;font-size:13px;font-weight:650}.axis-x,.axis-y{color:#475569;font-size:13px}.axis-y{margin-bottom:8px}.axis-x{text-align:center;margin-top:8px}.relation-list{display:grid;gap:10px}.relation-list div{padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:#fff}.remote-image{display:block;padding:14px;border:1px dashed #cbd5e1;color:var(--muted)}
@media(max-width:900px){.layout{display:block}nav{position:static;margin-bottom:24px}}@media print{body{background:#fff}.shell{box-shadow:none}.toolbar,nav{display:none}.layout{display:block;padding:10px}}
</style></head><body><main class="shell"><header class="hero"><span class="eyebrow">共享产品产物 · HTML 交互视图</span><h1>%s</h1><p>与可编辑 Markdown 同源；保存后生成新的项目版本。</p></header>
<div class="toolbar"><button type="button" data-expand>展开全部</button><button type="button" data-collapse>收起图表源码</button><button type="button" onclick="window.print()">打印 / 导出 PDF</button></div>
<div class="layout"><nav id="toc" aria-label="文档目录"></nav><article id="document">%s</article></div></main>
<script>(()=>{const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const lines=s=>s.split(/\n/).map(x=>x.trim()).filter(Boolean);document.querySelectorAll('#document h2').forEach((h,i)=>{h.id=h.id||'section-'+(i+1);const a=document.createElement('a');a.href='#'+h.id;a.textContent=h.textContent;toc.appendChild(a)});document.querySelectorAll('a').forEach(a=>{if(/^https?:/i.test(a.href)){a.target='_blank';a.rel='noopener noreferrer'}});document.querySelectorAll('pre code.language-mermaid').forEach(code=>{const src=code.textContent.trim(),first=(lines(src)[0]||'').toLowerCase();let title='关系图',inner='';if(first.startsWith('timeline')){title='时间轴';inner='<div class="timeline">'+lines(src).filter(x=>!(/^(timeline|title\b)/i.test(x))).map(x=>{const p=x.split(/\s*:\s*/);return '<div class="timeline-item"><b>'+esc(p.shift())+'</b><div>'+esc(p.join('：'))+'</div></div>'}).join('')+'</div>'}else if(first.startsWith('quadrantchart')){title='象限坐标图';const x=(src.match(/x-axis\s+([^\n]+)/i)||[])[1]||'横轴：低 → 高',y=(src.match(/y-axis\s+([^\n]+)/i)||[])[1]||'纵轴：低 → 高';const pts=[];lines(src).forEach(line=>{const m=line.match(/^\s*([^:]+):\s*\[\s*([.\d]+)\s*,\s*([.\d]+)\s*\]/);if(m)pts.push([m[1],Math.max(0,Math.min(1,+m[2])),Math.max(0,Math.min(1,+m[3]))])});inner='<div class="axis-y">'+esc(y)+'</div><div class="quadrant">'+pts.map(p=>'<div class="point" style="left:'+p[1]*100+'%%;bottom:'+p[2]*100+'%%"><i></i><span>'+esc(p[0])+'</span></div>').join('')+'</div><div class="axis-x">'+esc(x)+'</div>'}else{inner='<div class="relation-list">'+lines(src).filter(x=>!(/^(flowchart|graph|sequenceDiagram|stateDiagram)/i.test(x))).map(x=>'<div>'+esc(x)+'</div>').join('')+'</div>'}const f=document.createElement('figure');f.className='diagram';f.innerHTML='<figcaption><span>'+title+'</span><span>可视化</span></figcaption><div class="diagram-body">'+inner+'</div><details><summary>查看图表源码</summary><pre>'+esc(src)+'</pre></details>';code.parentElement.replaceWith(f)});document.querySelector('[data-expand]').onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=true);document.querySelector('[data-collapse]').onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=false)})()</script></body></html>`, html.EscapeString(stage.Label), html.EscapeString(stage.Label), document), nil
}

func createProductHumanRevision(tx *gorm.DB, sessionID, slot, contentType, text string, now time.Time) (orm.WorkflowSlotRevision, error) {
	var current orm.WorkflowSlotRevision
	currentResult := tx.Where("session_id = ? AND slot_id = ? AND selected = true", sessionID, slot).First(&current)
	hasCurrent := currentResult.Error == nil
	if currentResult.Error != nil && !errors.Is(currentResult.Error, gorm.ErrRecordNotFound) {
		return orm.WorkflowSlotRevision{}, currentResult.Error
	}
	var maxRevision int
	if err := tx.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ? AND slot_id = ?", sessionID, slot).Select("COALESCE(MAX(revision), 0)").Scan(&maxRevision).Error; err != nil {
		return orm.WorkflowSlotRevision{}, err
	}
	if hasCurrent {
		if result := tx.Model(&orm.WorkflowSlotRevision{}).Where("id = ? AND selected = true", current.ID).Update("selected", false); result.Error != nil || result.RowsAffected != 1 {
			if result.Error != nil {
				return orm.WorkflowSlotRevision{}, result.Error
			}
			return orm.WorkflowSlotRevision{}, ErrIdempotencyConflict
		}
	}
	value, _ := json.Marshal(map[string]string{"text": text})
	humanID := uuid.NewString()
	caption := "Product project Markdown edit"
	if err := tx.Create(&orm.WorkflowHumanArtifact{ID: humanID, SessionID: sessionID, Slot: slot, ContentType: contentType, Value: value, Caption: &caption, CreatedAt: now}).Error; err != nil {
		return orm.WorkflowSlotRevision{}, err
	}
	stepID, attempt := "product_project_editor", 0
	if hasCurrent {
		stepID, attempt = current.StepID, current.Attempt
	}
	created := orm.WorkflowSlotRevision{ID: uuid.NewString(), SessionID: sessionID, SlotID: slot, Slot: slot, Revision: maxRevision + 1, Selected: true, HumanArtifactID: &humanID, ChangeSource: "human", StepID: stepID, Attempt: attempt, Validity: "effective", CreatedAt: now}
	return created, tx.Create(&created).Error
}

func (r *Repository) UpdateProductProjectMarkdown(ctx context.Context, owner, sessionID, stageID string, req ProductMarkdownUpdateRequest) (json.RawMessage, error) {
	if !productStageValid(stageID) {
		return nil, repositoryError("INVALID_PRODUCT_STAGE")
	}
	if req.IdempotencyKey == "" || len(req.IdempotencyKey) > 128 || req.BaseRevisionID == "" || req.BaseRevision < 1 || len(req.Markdown) > 8<<20 || !utf8.ValidString(req.Markdown) || strings.TrimSpace(req.Markdown) == "" {
		return nil, repositoryError("INVALID_PRODUCT_MARKDOWN")
	}
	if err := r.AuthorizeSession(ctx, sessionID, owner); err != nil {
		return nil, err
	}
	body, _ := json.Marshal(map[string]any{"session_id": sessionID, "stage": stageID, "request": req})
	r.commandMu.Lock()
	defer r.commandMu.Unlock()
	command, _, err := r.commandTransactional(ctx, owner, sessionID, req.IdempotencyKey, "workflow.v1", body, func(tx *gorm.DB) (int, json.RawMessage, error) {
		txRepo := New(tx)
		session, workspace, _, err := txRepo.productRelayState(ctx, owner, sessionID)
		if err != nil {
			return 0, nil, err
		}
		if workspace == nil || session.Dismissed {
			return 0, nil, repositoryError("PRODUCT_STAGE_NOT_READY")
		}
		run, _ := workspace["current_run"].(map[string]any)
		if session.Status == "active" && productString(run["selected_stage"]) == stageID {
			return 0, nil, repositoryError("PRODUCT_STAGE_NOT_READY")
		}
		if err := txRepo.AuthorizeConversation(ctx, session.ConversationID, owner); err != nil {
			return 0, nil, err
		}
		current, err := txRepo.ProductProjectArtifact(ctx, owner, sessionID, stageID, "markdown")
		if err != nil {
			return 0, nil, err
		}
		if productString(current["revision_id"]) != req.BaseRevisionID || current["revision"] != req.BaseRevision || current["content_format"] != "markdown" {
			return 0, nil, ErrIdempotencyConflict
		}
		var stage productStageDefinition
		for _, candidate := range productStages {
			if candidate.ID == stageID {
				stage = candidate
				break
			}
		}
		now := time.Now().UTC()
		markdownRevision, err := createProductHumanRevision(tx, session.ID, stage.MarkdownSlot, "text/markdown", req.Markdown, now)
		if err != nil {
			return 0, nil, err
		}
		htmlSynced := stage.ID != "prototype"
		var htmlRevision orm.WorkflowSlotRevision
		if htmlSynced {
			rendered, renderErr := productMarkdownHTML(stage, req.Markdown)
			if renderErr != nil {
				return 0, nil, renderErr
			}
			htmlRevision, err = createProductHumanRevision(tx, session.ID, stage.HTMLSlot, "text/html", rendered, now)
			if err != nil {
				return 0, nil, err
			}
		}
		if err := tx.Model(&orm.WorkflowSession{}).Where("id = ?", session.ID).Updates(map[string]any{"state_version": gorm.Expr("state_version + 1"), "updated_at": now}).Error; err != nil {
			return 0, nil, err
		}
		var updated orm.WorkflowSession
		if err := tx.Where("id = ?", session.ID).First(&updated).Error; err != nil {
			return 0, nil, err
		}
		result := map[string]any{"session_id": session.ID, "stage": stage.ID, "state_version": updated.StateVersion, "markdown": req.Markdown,
			"revision_id": markdownRevision.ID, "revision": markdownRevision.Revision, "slot_id": markdownRevision.SlotID,
			"html_synced": htmlSynced, "html_sync_required": !htmlSynced}
		if htmlSynced {
			result["html_revision_id"], result["html_revision"] = htmlRevision.ID, htmlRevision.Revision
		}
		encoded, _ := json.Marshal(result)
		return 200, encoded, nil
	})
	if err != nil {
		return nil, err
	}
	return command.ResponseJSON, nil
}
